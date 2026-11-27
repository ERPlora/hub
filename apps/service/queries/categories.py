"""The categories of the catalog: a category by how a person names it, its rows and its reads."""

from uuid import UUID

from django.db.models import Count, Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.context import OperationContext
from live.operations import operation

from apps.service.models.catalog import Category
from apps.service.queries.reads import _page, _resolve
from apps.service.schemas.categories import CategoryListIn, CategoryOut, CategoryPage
from apps.service.schemas.fields import CategoryRefIn
from base.ordering import list_order_for
from base.text_search import contains_text

CATEGORY_NOT_FOUND = _("That category does not exist in this business.")
# Its own context: said as its siblings are («vale para varios»), not as Inventory says it (hub#662).
CATEGORY_AMBIGUOUS = pgettext_lazy(
    "service", "“%(said)s” matches several categories: %(names)s. Say which one."
)

CATEGORY_ORDER = {
    "sort_order": ("sort_order",),
    "name": ("name",),
    "parent_name": ("parent__name",),
    "service_count": ("service_count",),
}


def find_category(
    category_id: UUID | None,
    said: str | None,
    *,
    lock: bool = False,
    hold: bool = False,
    rows=None,
) -> Category:
    """A live category, by id or by name; from ``rows`` when given, in one read (as ``find_service``)."""
    categories = Category.objects.all()
    found_in = categories if rows is None else rows
    return _resolve(
        found_in.filter(is_deleted=False),
        category_id,
        said,
        lock=lock,
        hold=hold,
        missing=CATEGORY_NOT_FOUND,
        missing_code="service.category_not_found",
        ambiguous=CATEGORY_AMBIGUOUS,
        ambiguous_code="service.category_ambiguous",
        named=categories.filter(is_deleted=False),
    )


def _categories():
    return (
        Category.objects.filter(is_deleted=False)
        .select_related("parent")
        .annotate(service_count=Count("services", filter=Q(services__is_active=True)))
    )


def _category_row(category: Category) -> dict:
    fields = (
        "id",
        "name",
        "description",
        "parent_id",
        "icon",
        "color",
        "sort_order",
        "service_count",
        "created_at",
        "updated_at",
    )
    return {
        **{field: getattr(category, field) for field in fields},
        "parent_name": category.parent.name if category.parent else None,
    }


def load_category(category_id: UUID) -> dict:
    return _category_row(_categories().get(pk=category_id))


@operation(
    "service.category.list",
    kind="query",
    permission="service.view_category",
    input=CategoryListIn,
    output=CategoryPage,
    expose_api=True,
    ai={
        "description": "List the service categories by their order, with their parent and how many offered services "
        "each has.",
        "asks": {
            "en": ("what service categories do we have?", "how are the services split into categories?"),
            "es": ("¿qué categorías de servicios hay?", "enséñame las familias de servicios"),
        },
    },
)
def list_categories(ctx: OperationContext, params: CategoryListIn) -> dict:
    categories = _categories()
    if params.search:
        categories = categories.filter(contains_text(params.search, "name"))
    if params.parent_id:
        categories = categories.filter(parent_id=params.parent_id)
    return _page(
        categories.order_by(
            *list_order_for(params.sort, "sort_order", "name", columns=CATEGORY_ORDER, nulls_last=True)
        ),
        params,
        _category_row,
    )


@operation(
    "service.category.get",
    kind="query",
    permission="service.view_category",
    input=CategoryRefIn,
    output=CategoryOut,
    expose_api=True,
    ai={
        "description": "Get one service category, named by its id or its name.",
        "asks": {
            "en": ("get me the colour category with its services", "which category is the nails one under?"),
            "es": ("dame la categoría de color con sus servicios", "¿de qué categoría cuelga la de uñas?"),
        },
    },
)
def get_category(ctx: OperationContext, data: CategoryRefIn) -> dict:
    return _category_row(find_category(data.id, data.category, rows=_categories()))
