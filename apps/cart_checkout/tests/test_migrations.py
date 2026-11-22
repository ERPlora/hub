"""Migration 0004 of the cart_checkout app, both ways, on a business's own database cloned from the template and
through the migrator's alias, as ``migrate_hubs`` runs it. Forward, whoever a cart, its lines or its order saved by their
address keeps what goes before the «@» (BASE-F119); a named person keeps their name, and the customer's email is not a
colleague's. Back, nothing changes."""

from apps.whatsapp_inbox.tests.test_migrations import database, migrate
from base.tests.colleagues import ADDRESS, SHOWN

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "cart_checkout"
BEFORE = [(APP, "0003_currency_without_default")]
AFTER = [(APP, "0004_actors_without_address")]
NAMED = "Luis García"
CUSTOMER = "carmen@example.com"


def saved(apps, database) -> dict[str, list]:
    def rows(model: str, *fields: str):
        return sorted(apps.get_model(APP, model).objects.using(database.alias).values_list(*fields))

    return {
        "carts": rows("Cart", "customer_email", "created_by", "updated_by"),
        "items": rows("CartItem", "created_by", "updated_by"),
        "orders": rows("Order", "customer_email", "created_by", "updated_by"),
    }


def test_whoever_a_cart_saved_by_their_address_keeps_only_what_goes_before_it(database):
    old = migrate(database, BEFORE)

    def rows(model: str):
        return old.get_model(APP, model).objects.using(database.alias)

    cart = rows("Cart").create(
        session_token="sess_1", customer_email=CUSTOMER, currency="EUR", created_by=ADDRESS, updated_by=NAMED
    )
    rows("CartItem").create(
        cart=cart, product_ref="p-1", product_name="Champú", quantity=1, unit_price=1200, line_total=1200,
        created_by=ADDRESS, updated_by=ADDRESS,
    )
    rows("Order").create(
        cart=cart, order_number="OS-20261122-0001", customer_email=CUSTOMER, currency="EUR", created_by="",
        updated_by=ADDRESS,
    )
    cleaned = {
        "carts": [(CUSTOMER, SHOWN, NAMED)],
        "items": [(SHOWN, SHOWN)],
        "orders": [(CUSTOMER, "", SHOWN)],
    }

    assert saved(migrate(database, AFTER), database) == cleaned
    assert saved(migrate(database, BEFORE), database) == cleaned
