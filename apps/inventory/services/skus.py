"""The SKU of a product created without one: the next number of the catalog's own, from 10000, as Lightspeed and
Loyverse number theirs. It is the product's identity from then on, as a typed one is."""

from collections.abc import Callable

from django.db.models import IntegerField, Max
from django.db.models.functions import Cast
from live.errors import Conflict

from apps.inventory.models import Product

FIRST = 10000
#: The catalog's own numbers: 5 to 9 digits without a leading zero. A barcode used as SKU (EAN-13, UPC) is not one.
OWN_NUMBER = r"^[1-9][0-9]{4,8}$"
#: Two people creating at once may take the same number; the one who saves second takes the next.
ATTEMPTS = 3
SKU_TAKEN = "inventory.sku_taken"


def next_sku() -> str:
    """One more than the highest number of the catalog's own, deleted products included (bringing one back never
    finds its SKU taken), or 10000."""
    numbers = Product.objects.filter(sku__regex=OWN_NUMBER).annotate(number=Cast("sku", IntegerField()))
    top = numbers.aggregate(top=Max("number"))["top"]
    return str(max(FIRST, (top or 0) + 1))


def save_with_sku(product: Product, save: Callable[[Product], None]) -> None:
    """``save`` the new ``product`` (in a savepoint, its constraints said as refusals); without a SKU, numbered."""
    if product.sku:
        save(product)
        return
    for attempt in range(1, ATTEMPTS + 1):
        product.sku = next_sku()
        try:
            save(product)
        except Conflict as exc:
            if exc.code != SKU_TAKEN or attempt == ATTEMPTS:
                raise
        else:
            return
