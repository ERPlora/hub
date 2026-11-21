"""The product categories: their list with how many active products each has, one category, and which
categories each active product is in."""

from uuid import UUID

from django.db.models import Count, Q
from live.context import OperationContext
from live.errors import NotFound
from live.operations import INTERNAL, operation

from apps.inventory.models import Category, ProductCategory
from apps.inventory.queries.reads import CATEGORY_NOT_FOUND, _bounds, _page, find_category
from apps.inventory.schemas.categories import CategoryFiltersIn, CategoryListIn, CategoryOut, CategoryPage
from apps.inventory.schemas.fields import CategoryRefIn
from apps.inventory.schemas.product_categories import ProductCategoryListIn, ProductCategoryPage
from base.ordering import list_order_for


def load_category(category_id: UUID) -> dict | None:
    category = _categories().filter(pk=category_id).first()
    return None if category is None else _category_row(category)


@operation(
    "inventory.product_category.list",
    kind="query",
    permission="inventory.view_product",
    input=ProductCategoryListIn,
    output=ProductCategoryPage,
    expose_api=True,
    ai={
        "description": "Map each active product to its categories; the till filters its grid by category with it.",
        "asks": {
            "en": (
                "which category is each till item in?",
                "what family does each article belong to?",
            ),
            "es": (
                "¿en qué familia está cada artículo del TPV?",
                "¿a qué categoría pertenece cada producto?",
            ),
        },
    },
)
def list_product_categories(
    ctx: OperationContext, params: ProductCategoryListIn
) -> dict:
    links = ProductCategory.objects.filter(
        product__is_deleted=False, product__is_active=True, category__is_deleted=False
    )
    if params.search:
        links = links.filter(
            Q(product__name__icontains=params.search)
            | Q(product__sku__icontains=params.search)
            | Q(category__name__icontains=params.search)
        )
    if params.product_id:
        links = links.filter(product_id=params.product_id)
    if params.category_id:
        links = links.filter(category_id=params.category_id)
    return _page(
        links.order_by("product_id", "category_id"),
        params,
        lambda link: {"product_id": link.product_id, "category_id": link.category_id},
    )


@operation(
    "inventory.category.list",
    kind="query",
    permission="inventory.view_category",
    input=CategoryListIn,
    output=CategoryPage,
    expose_api=True,
    ai={
        "description": "List the product categories, with how many active products each one has (sold out included).",
        "asks": {
            "en": (
                "what categories do I have?",
                "list the families of the till with how many items each",
            ),
            "es": (
                "¿qué categorías tengo?",
                "lista las familias del TPV con cuántos artículos tiene cada una",
            ),
        },
    },
)
def list_categories(ctx: OperationContext, params: CategoryListIn) -> dict:
    categories = _categories()
    if params.ids is not None:
        categories = categories.filter(id__in=params.ids)
    return _page(_filter_categories(categories, params), params, _category_row)


# Not an assistant tool: what names a category on the card of a write (``schemas.A_CATEGORY``), as the screens show it;
# the model finds a category in its list.
@operation(
    "inventory.category.get",
    kind="query",
    permission="inventory.view_category",
    input=CategoryRefIn,
    output=CategoryOut,
    ai=INTERNAL,
)
def get_category(ctx: OperationContext, data: CategoryRefIn) -> dict:
    row = load_category(find_category(data.id, data.category).pk)
    if row is None:  # deleted between the two reads
        raise NotFound(str(CATEGORY_NOT_FOUND))
    return row


def _filter_categories(categories, params: CategoryFiltersIn):
    if params.search:
        categories = categories.filter(
            Q(name__icontains=params.search) | Q(slug__icontains=params.search)
        )
    categories = categories.filter(
        **_bounds(
            name__icontains=params.name,
            slug__icontains=params.slug,
            icon=params.icon,
            color=params.color,
            product_count__gte=params.product_count_min,
            product_count__lte=params.product_count_max,
        )
    )
    return categories.order_by(*list_order_for(params.sort))


def _categories():
    # What the till's strip counts is what its grid shows: the active articles, the sold-out ones greyed
    # among them (SALE-F07).
    active = Q(
        product_links__product__is_active=True,
        product_links__product__is_deleted=False,
    )
    return (
        Category.objects.filter(is_deleted=False)
        .select_related("tax_category")
        .annotate(product_count=Count("product_links", filter=active))
    )


def _category_row(category: Category) -> dict:
    fields = (
        "id",
        "name",
        "slug",
        "description",
        "icon",
        "color",
        "order",
        "tax_category_id",
        "product_count",
    )
    return {
        **{field: getattr(category, field) for field in fields},
        "tax_category_key": category.tax_category.key
        if category.tax_category
        else None,
    }
