"""The product or the category of the catalogue a person names, by its id or by its name."""

from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.errors import Conflict, NotFound

from apps.inventory.models import Category, Product
from apps.kitchen.queries.reads import MAX_CANDIDATES
from base.text_search import contains_text

PRODUCT_NOT_FOUND = _("That product does not exist in the catalogue.")
PRODUCT_AMBIGUOUS = _("“%(said)s” matches several products: %(names)s. Say which one.")
CATEGORY_NOT_FOUND = _("That category does not exist in the catalogue.")
CATEGORY_AMBIGUOUS = _(
    "“%(said)s” matches several categories: %(names)s. Say which one."
)


def _one(rows, said: str, missing, ambiguous, code: str):
    if not rows:
        raise NotFound(str(missing), code=f"kitchen.{code}_not_found")
    if len(rows) > 1:
        names = ", ".join(row.name for row in rows[:MAX_CANDIDATES])
        raise Conflict(
            str(ambiguous) % {"said": said, "names": names},
            code=f"kitchen.{code}_ambiguous",
        )
    return rows[0]


def find_product(product_id: UUID | None, said: str | None) -> Product:
    products = Product.objects.filter(is_deleted=False)
    if product_id is not None:
        return _one(
            list(products.filter(pk=product_id)),
            str(product_id),
            PRODUCT_NOT_FOUND,
            PRODUCT_AMBIGUOUS,
            "product",
        )
    exact = list(products.filter(name__iexact=said)[:2]) or list(
        products.filter(sku__iexact=said)[:2]
    )
    rows = exact or list(
        products.filter(contains_text(said, "name")).order_by("name", "id")[
            : MAX_CANDIDATES + 1
        ]
    )
    return _one(rows, said, PRODUCT_NOT_FOUND, PRODUCT_AMBIGUOUS, "product")


def find_category(category_id: UUID | None, said: str | None) -> Category:
    categories = Category.objects.filter(is_deleted=False)
    if category_id is not None:
        return _one(
            list(categories.filter(pk=category_id)),
            str(category_id),
            CATEGORY_NOT_FOUND,
            CATEGORY_AMBIGUOUS,
            "category",
        )
    exact = list(categories.filter(name__iexact=said)[:2])
    rows = exact or list(
        categories.filter(contains_text(said, "name")).order_by("name", "id")[
            : MAX_CANDIDATES + 1
        ]
    )
    return _one(rows, said, CATEGORY_NOT_FOUND, CATEGORY_AMBIGUOUS, "category")
