"""Whether a product shows on the business's website (INVENTORY-F36): on unless the business turns it off, changed by
the product's own create and update, read by the website through the sale list, and never a reason for the till not to
sell it."""

from live.errors import PermissionDenied

from apps.inventory import events
from apps.inventory.models import Product
from apps.inventory.schemas.products import ForSaleListIn
from apps.inventory.tests.test_services import clear_outbox, create, general, outbox, refused, run, sold_out, update

from .conftest import HUB_DB

#: The general tax category every product of these tests takes, created before each test.
__all__ = ["general"]

pytestmark = HUB_DB


def for_sale(**params) -> dict[str, bool]:
    return {row.sku: row.show_on_website for row in run("inventory.product.list_for_sale", ForSaleListIn(**params)).rows}


def test_a_product_shows_on_the_website_unless_it_is_created_hidden():
    shown, hidden = create("Coffee", "CAF-1"), create("Staff meal", "STAFF", show_on_website=False)

    assert (shown.show_on_website, hidden.show_on_website) == (True, False)
    assert dict(Product.objects.values_list("sku", "show_on_website")) == {"CAF-1": True, "STAFF": False}


def test_turning_it_off_and_on_is_an_edit_of_the_product_announced_once():
    product = create("Coffee", "CAF-1")
    clear_outbox()

    assert update(product.id, show_on_website=False).show_on_website is False
    update(product.id, show_on_website=False)
    assert update(product.id, show_on_website=True).show_on_website is True

    assert [payload["show_on_website"] for _, payload in outbox(events.PRODUCT_UPDATED)] == [False, True]


def test_whoever_cannot_change_products_cannot_hide_one():
    product = create("Coffee", "CAF-1")

    refused(PermissionDenied, lambda: update(product.id, role="hub_employee", show_on_website=False))
    assert Product.objects.get().show_on_website is True


def test_the_till_still_sells_a_product_hidden_from_the_website_and_the_sale_list_says_so():
    create("Coffee", "CAF-1")
    create("Staff meal", "STAFF", show_on_website=False)

    assert for_sale() == {"CAF-1": True, "STAFF": False}


def test_the_sale_list_asked_for_the_website_leaves_the_hidden_ones_out():
    create("Coffee", "CAF-1")
    create("Staff meal", "STAFF", show_on_website=False)
    sold_out(create("Tea", "TEA-1").id)

    assert for_sale(show_on_website=True) == {"CAF-1": True}
    assert for_sale(show_on_website=False) == {"STAFF": False}
