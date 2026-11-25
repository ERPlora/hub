"""The tax categories: their list with today's rate (TAX-F01), one category by its key, name or alias with how a
person names it, and the categories a write of another app holds while it names them."""

from collections.abc import Iterable

from django.db.models import Case, CharField, F, Q, Value, When
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.tax.models import SYSTEM_CATEGORY_LABELS, TaxCategory
from apps.tax.queries.jurisdiction import asked_jurisdiction, business_jurisdiction, business_today
from apps.tax.queries.naming import category_by_reference
from apps.tax.queries.resolution import current_rates
from apps.tax.schemas.categories import CategoryGetIn, CategoryListIn, CategoryNamedOut, CategoryPage
from base.business import percent_text
from base.ordering import list_order

CATEGORY_NOT_FOUND = _("This tax category does not exist.")


def _translated(field_name: str, attribute: str) -> Case:
    """``display_name`` / ``display_description`` in SQL, in the active language, so that a filter or
    a sort reads what the column shows. A factory category reads its label; an own one, its text."""
    whens = [
        When(is_system=True, key=key, then=Value(str(getattr(label, attribute))))
        for key, label in SYSTEM_CATEGORY_LABELS.items()
        if str(getattr(label, attribute))
    ]
    return Case(*whens, default=F(field_name), output_field=CharField())


def category_row(category: TaxCategory) -> dict:
    """A ``CategoryOut`` (its texts in the active language)."""
    return {
        "id": category.id,
        "key": category.key,
        "name": category.name,
        "description": category.description,
        "display_name": category.display_name,
        "display_description": category.display_description,
        "is_system": category.is_system,
        "is_active": category.is_active,
    }


def category_label(category: TaxCategory) -> str:
    """How a person names ``category`` with what it charges today in the business's country and region, in the active
    language, as the Sections screen tells it («Producto — general · 21 %»); without a rule in force, its name alone."""
    resolution = current_rates([category], *business_jurisdiction(), business_today())[category.id]
    if resolution is None:
        return category.display_name
    return f"{category.display_name} · {percent_text(resolution.rate_pct)}"


@operation(
    "tax.category.list",
    kind="query",
    permission="tax.view",
    input=CategoryListIn,
    output=CategoryPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "list the tax categories",
                "which VAT categories can a product have?",
                "show me the tax categories with their rate today",
            ),
            "es": (
                "lista las categorías de impuestos",
                "¿qué categorías fiscales hay y qué tipo tiene cada una?",
                "muéstrame las categorías de IVA con su porcentaje",
            ),
        },
        "description": "List the active tax categories (the key products and services link to), with the "
        "rate each one has today in a country and region (the business's unless a country is named); search by "
        "key, name or description."
    },
)
def list_categories(ctx: OperationContext, params: CategoryListIn) -> dict:
    """Sorted by the column asked, ``key`` and ``id`` as the tie-break; each row with today's rate."""
    with translation.override(ctx.language):
        categories = TaxCategory.objects.filter(is_active=True).annotate(
            shown_name=_translated("name", "name"), shown_description=_translated("description", "description")
        )
        if params.search:
            categories = categories.filter(
                Q(key__icontains=params.search)
                | Q(name__icontains=params.search)
                | Q(description__icontains=params.search)
                | Q(shown_name__icontains=params.search)
                | Q(shown_description__icontains=params.search)
            )
        for column, value in (
            ("key", params.key),
            ("name", params.name),
            ("shown_name", params.display_name),
            ("shown_description", params.display_description),
        ):
            if value:
                categories = categories.filter(**{f"{column}__icontains": value})
        if params.is_system is not None:
            categories = categories.filter(is_system=params.is_system)
        column = {"display_name": "shown_name", "display_description": "shown_description"}.get(params.sort, params.sort)
        ordered = categories.order_by(*list_order(column, "key", descending=params.dir == "desc", nulls_last=True))
        page = list(ordered[params.offset : params.offset + params.limit])
        country_code, region_code = asked_jurisdiction(params.country_code, params.region_code)
        rates = current_rates(page, country_code, region_code, business_today())
        rows = [
            {
                **category_row(category),
                "rate_pct": rates[category.id].rate_pct if rates[category.id] else None,
                "operation_class": rates[category.id].operation_class if rates[category.id] else None,
            }
            for category in page
        ]
        return {"rows": rows, "total": categories.count(), "limit": params.limit, "offset": params.offset}


@operation(
    "tax.category.get",
    kind="query",
    permission="tax.view",
    input=CategoryGetIn,
    output=CategoryNamedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "does the tax category for books exist?",
                "check that the tax category product.books exists",
                "what is the Spanish name of the VAT category for food?",
            ),
            "es": (
                "¿existe la categoría fiscal de libros?",
                "¿cómo se llama en español la categoría de impuestos product.books?",
                "dame la categoría fiscal de los medicamentos",
            ),
        },
        "description": "Get one tax category by its key, its name or an alias, with its name in the reader's "
        "language (to check that a category exists before linking a product or a service to it)."
    },
)
def get_category(ctx: OperationContext, params: CategoryGetIn) -> dict:
    category = category_by_reference(params.key)
    if category is None:
        raise NotFound(CATEGORY_NOT_FOUND)
    with translation.override(ctx.language):
        return {**category_row(category), "label": category_label(category)}


# ── A tax category another app's write names ───────────────────────────────────────────────────




def held_categories(keys: Iterable[str]) -> dict[str, TaxCategory]:
    """The active tax categories of ``keys`` (key → category), each held until the caller's transaction ends
    with a key-share lock taken in the same read, in key order, for a write of another app that names them (a
    service, its settings): deleting one in the Hub admin waits for that write, while another write that names
    it or deactivates it goes on, so two writes never wait for each other in a circle. One deleted meanwhile is
    read once the deletion ends: gone, as one deleted before. The ORM has no ``FOR KEY SHARE``: it is appended
    to the SQL the ORM wrote, and the rows still come from the hub's database by the router."""
    keys = sorted(set(keys))
    if not keys:
        return {}
    rows = TaxCategory.objects.filter(key__in=keys, is_active=True).order_by("key")
    sql, params = rows.query.sql_with_params()
    return {category.key: category for category in TaxCategory.objects.raw(f"{sql} FOR KEY SHARE", params)}
