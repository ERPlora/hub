"""What every read of the inventory app shares, and services/ too inside the command's own transaction: how a
person names a product or a category (assistant, voice), the rows a write holds and how a list pages."""

from uuid import UUID

from django.core.exceptions import EmptyResultSet
from django.db.models import Q, QuerySet
from django.utils.translation import gettext_lazy as _
from live.errors import Conflict, NotFound

from apps.inventory.models import Category, Product
from base.text_search import contains_text

PRODUCT_NOT_FOUND = _("This product does not exist in this hub.")
CATEGORY_NOT_FOUND = _("This category no longer exists.")
PRODUCT_AMBIGUOUS = _("“%(said)s” matches several products: %(names)s. Say which one.")
CATEGORY_AMBIGUOUS = _(
    "“%(said)s” matches several categories: %(names)s. Say which one."
)


def find_product(
    product_id: UUID | None, said: str | None, *, lock: bool = False, rows=None
) -> Product:
    """The live product named by its id, or by its SKU or name as a person says it.

    By text: the SKU (ignoring case), else the exact name, else the only name that contains it.
    ``NotFound`` when none matches; 409 ``inventory.product_ambiguous`` when several do.
    The product comes from ``rows`` when given (e.g. ready for its row): one read, so a deletion committed
    meanwhile is either not seen yet or not found, never a row that vanished between two reads.
    """
    products = Product.objects.filter(is_deleted=False)
    if product_id is None:
        candidates = _first_match(
            products,
            (Q(sku__iexact=said), Q(name__iexact=said), contains_text(said, "name")),
        )
        if len(candidates) > 1:
            names = ", ".join(
                f"{product.name} ({product.sku})" for product in candidates[:5]
            )
            raise Conflict(
                str(PRODUCT_AMBIGUOUS) % {"said": said, "names": names},
                code="inventory.product_ambiguous",
            )
        product_id = candidates[0].pk if candidates else None
    found = (products if rows is None else rows).filter(pk=product_id)
    product = (found.select_for_update() if lock else found).first()
    if product is None:
        raise NotFound(str(PRODUCT_NOT_FOUND))
    return product


def find_category(
    category_id: UUID | None,
    said: str | None,
    *,
    lock: bool = False,
    hold: bool = False,
) -> Category:
    """The live category named by its id, or by its name or slug: exact first, else the only one that contains it.

    ``lock`` takes it to change it; ``hold`` takes it to name it (a product put in it, see ``held``).
    """
    categories = Category.objects.filter(is_deleted=False)
    if category_id is None:
        candidates = _first_match(
            categories,
            (Q(slug__iexact=said) | Q(name__iexact=said), contains_text(said, "name")),
        )
        if len(candidates) > 1:
            names = ", ".join(category.name for category in candidates[:5])
            raise Conflict(
                str(CATEGORY_AMBIGUOUS) % {"said": said, "names": names},
                code="inventory.category_ambiguous",
            )
        category_id = candidates[0].pk if candidates else None
    found = categories.filter(pk=category_id)
    if hold:
        category = next(iter(held(found[:1])), None)
    else:
        category = (found.select_for_update() if lock else found).first()
    if category is None:
        raise NotFound(str(CATEGORY_NOT_FOUND))
    return category


def held(rows: QuerySet) -> list:
    """``rows``, each held until this transaction ends with a key-share lock taken in the same read, for a
    write that names them (a product put in a category, a tax category chosen): a deletion, the business's
    «Delete» or the Hub admin's, waits for this write, while another write that names them goes on, so two
    writes never wait for each other in a circle. One being deleted meanwhile is read once the deletion ends:
    gone, as one deleted before. The ORM has no ``FOR KEY SHARE``: it is appended to the SQL the ORM wrote,
    and the rows still come from the hub's database by the router."""
    try:
        sql, params = rows.query.sql_with_params()
    except EmptyResultSet:  # an empty ``__in``: nothing to read nor to hold
        return []
    return list(rows.model.objects.raw(f"{sql} FOR KEY SHARE", params))


def _first_match(queryset, lookups) -> list:
    """The rows of the first lookup that matches anything (in order of preference), at most six."""
    for lookup in lookups:
        rows = list(queryset.filter(lookup).order_by("name", "id")[:6])
        if rows:
            return rows
    return []


def _bounds(**lookups) -> dict:
    """The lookups whose value was given (a filter left empty narrows nothing)."""
    return {lookup: value for lookup, value in lookups.items() if value is not None}


def _page(queryset, params, row) -> dict:
    return {
        "rows": [
            row(item) for item in queryset[params.offset : params.offset + params.limit]
        ],
        "total": queryset.count(),
        "limit": params.limit,
        "offset": params.offset,
    }
