"""What Price Lists gives back from a separate copy of the business (BASE-F114, PRICING-F14).

The copy is no business, so it has no alias and the ORM never reaches it: the platform reads it through a direct,
read-only connection, and Price Lists answers with its own SQL over its models' names. Its prices: each one of a live
product or of a service that the business no longer has is put back by ``pricing.price_item.add``, the list detail's
own, unless the business has a price in that place again (the same list, article and from quantity). Price Lists goes
after Inventory (its ``requires``), so a deleted product is back, the same, before its prices are put.

Then, end to end on real databases (``hubs.CopiedHubs``): the business's own and its copy, a clone of it.
"""

import uuid
from decimal import Decimal

import pytest
from django.apps import apps
from django.db import connection
from live.models import OutboxEvent

from apps.inventory.tests.test_recovery import CATEGORIES, LINKS, PRODUCTS, a_tax_key
from apps.pricing import queries
from apps.pricing.models import PriceItem
from base.recovery import actor_of
from base.tenancy.context import use_hub
from base.tenancy.tests.test_recovery import Recoveries, fresh, run, run_in

from .conftest import make_item, make_list, make_product, make_service


def direct():
    """The raw connection of the tests' database, as the platform's direct one reads the copy."""
    connection.ensure_connection()
    return connection.connection


@pytest.mark.django_db
def test_the_copy_gives_each_price_of_a_live_product_or_of_a_service_with_what_its_add_takes():
    vip = make_list("VIP")
    shampoo = make_product("Shampoo", "SH-1")
    haircut = make_service("Haircut")
    one = make_item(vip, shampoo, price=900)
    ten = make_item(vip, shampoo, price=800, min_quantity="10")
    cut = make_item(vip, None, price=1500, service_id=haircut.id, service_name="Haircut")
    # A deleted product's prices do not count (Inventory's deletion takes them away): none is read.
    make_item(vip, make_product("Old", "OLD-1", is_deleted=True), price=100)

    read = queries.prices_in_copy(direct())

    assert sorted(read, key=lambda one: one["id"]) == [
        {"id": one.id, "price_list_id": vip.id, "product_id": shampoo.id, "service_id": None, "price": 900,
         "min_quantity": Decimal("1.000")},
        {"id": ten.id, "price_list_id": vip.id, "product_id": shampoo.id, "service_id": None, "price": 800,
         "min_quantity": Decimal("10.000")},
        {"id": cut.id, "price_list_id": vip.id, "product_id": None, "service_id": haircut.id, "price": 1500,
         "min_quantity": Decimal("1.000")},
    ]


@pytest.mark.django_db
def test_a_copy_without_the_apps_table_gives_nothing():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE pricing_priceitem CASCADE")

    assert queries.prices_in_copy(direct()) == []


def a_price_of_the_copy(price_list, *, product=None, service=None, price=1000, min_quantity="1") -> dict:
    return {
        "id": uuid.uuid7(),
        "price_list_id": price_list.id,
        "product_id": product.id if product else None,
        "service_id": service.id if service else None,
        "price": price,
        "min_quantity": Decimal(min_quantity),
    }


@pytest.mark.django_db
def test_lacking_is_a_price_the_business_no_longer_has_in_a_place_it_left_free():
    vip, bulk = make_list("VIP"), make_list("BULK")
    shampoo = make_product("Shampoo", "SH-1")
    haircut = make_service("Haircut")
    # Still in the business, from another quantity since: it is the business's, nothing lacks.
    held = make_item(vip, shampoo, price=900, min_quantity="3")
    still = a_price_of_the_copy(vip, product=shampoo, price=900) | {"id": held.id}
    # Its place taken again by the business, at another price: the business's stays, never a second one.
    make_item(bulk, shampoo, price=850, min_quantity="10.000")
    put_back = a_price_of_the_copy(bulk, product=shampoo, price=800, min_quantity="10")
    # Lacking: the same product from another quantity, and a service's.
    from_five = a_price_of_the_copy(bulk, product=shampoo, price=820, min_quantity="5")
    cut = a_price_of_the_copy(vip, service=haircut, price=1500)

    lacking = queries.prices_not_in_business([still, put_back, from_five, cut])

    # As the list detail's add takes each, with its id in the copy: its list, its one article, price and quantity.
    assert lacking == [
        {"id": from_five["id"], "price_list_id": bulk.id, "product_id": shampoo.id, "price": 820,
         "min_quantity": Decimal("5")},
        {"id": cut["id"], "price_list_id": vip.id, "service_id": haircut.id, "price": 1500,
         "min_quantity": Decimal("1")},
    ]


def test_with_nothing_read_nothing_is_lacking():
    assert queries.prices_not_in_business([]) == []


def test_the_app_declares_its_prices_put_back_by_the_list_details_add():
    [prices] = apps.get_app_config("pricing").recoverable_from_copy()

    assert (prices.read, prices.missing, prices.create, prices.deleted, prices.restore) == (
        queries.prices_in_copy,
        queries.prices_not_in_business,
        "pricing.price_item.add",
        None,
        "",
    )
    assert (str(prices.label), prices.reads_since) == ("Price list prices", "0001_initial")


# ── End to end: the business's own database and its copy ────────────────────────────────────────────────────────────


@pytest.fixture
def recoveries(django_db_blocker, hub_databases):
    with django_db_blocker.unblock():
        made = Recoveries(hub_databases.template)
        yield made
        made.clean()


PRICES = {
    "app": "pricing", "label": "Price list prices", "restored": 0, "created": 0, "not_created": 0, "reasons": [],
    "refused": "",
}


def said(row) -> tuple[str, list[dict]]:
    """``row``'s status and what each thing it gave back gave, by the keys these tests read."""
    keys = ("app", "label", "restored", "created", "not_created", "reasons", "refused")
    row = fresh(row)
    return row.status, [{key: result[key] for key in keys} for result in row.results]


def prices(hub) -> list[tuple]:
    """The business's prices: list code, product id, price and from quantity, by list and quantity."""
    with use_hub(hub):
        return list(
            PriceItem.objects.order_by("price_list__code", "min_quantity").values_list(
                "price_list__code", "product_id", "price", "min_quantity"
            )
        )


def added(hub) -> int:
    with use_hub(hub):
        return OutboxEvent.objects.filter(name="pricing.price_item.added").count()


@pytest.mark.usefixtures("no_test_fallback")
class TestPricesComeBack:
    def a_business(self, recoveries, every_app_on):
        """A business with a product priced in two lists, by their screens' operations: its id."""
        hub, _ = recoveries.business(every_app_on)
        shampoo = run_in(hub, "inventory.product.create", name="Shampoo", sku="SH-1", price=1200,
                         tax_category_key=a_tax_key(hub)).id
        for code in ("VIP", "BULK"):
            run_in(hub, "pricing.price_list.create", code=code, name=f"{code} prices")
        run_in(hub, "pricing.price_item.add", price_list="VIP", product_id=shampoo, price=900)
        run_in(hub, "pricing.price_item.add", price_list="BULK", product_id=shampoo, price=800, min_quantity="10")
        return hub, shampoo

    def deleted(self, hub, product) -> None:
        """``product`` deleted in the business, and its prices taken away as the relay hands its deletion to Price
        Lists."""
        run_in(hub, "inventory.product.delete", id=product)
        run_in(hub, "pricing.catalog.forget_product", id=product)
        assert prices(hub) == []

    def test_a_deleted_product_comes_back_with_its_prices_in_the_lists_it_was_in(self, recoveries, every_app_on):
        hub, shampoo = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, shampoo)
        before = added(hub)
        row = recoveries.ask(copy, "pricing", "inventory")

        assert run() == 1

        # Inventory first, whatever the order asked: the product is back, the same, before its prices are put.
        assert said(row) == ("done", [CATEGORIES, PRODUCTS | {"restored": 1}, LINKS, PRICES | {"created": 2}])
        assert prices(hub) == [("BULK", shampoo, 800, Decimal("10.000")), ("VIP", shampoo, 900, Decimal("1.000"))]
        with use_hub(hub):
            assert set(PriceItem.objects.values_list("created_by", flat=True)) == {actor_of(row.pk)}
        assert added(hub) == before + 2
        # Asked again, nothing is put twice.
        again = recoveries.ask(copy, "inventory", "pricing")
        assert run() == 1
        assert said(again) == ("done", [CATEGORIES, PRODUCTS, LINKS, PRICES])
        assert len(prices(hub)) == 2

    def test_a_price_the_business_put_back_stays_as_it_is(self, recoveries, every_app_on):
        hub, shampoo = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, shampoo)
        recoveries.ask(copy, "inventory")
        assert run() == 1
        # The product back without its prices, the business priced it again in VIP by hand.
        run_in(hub, "pricing.price_item.add", price_list="VIP", product_id=shampoo, price=950)
        row = recoveries.ask(copy, "pricing")

        assert run() == 1

        assert said(row) == ("done", [PRICES | {"created": 1}])
        assert prices(hub) == [("BULK", shampoo, 800, Decimal("10.000")), ("VIP", shampoo, 950, Decimal("1.000"))]

    def test_a_price_that_cannot_be_put_now_does_not_come_back_and_says_why(self, recoveries, every_app_on):
        hub, shampoo = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, shampoo)
        run_in(hub, "pricing.price_list.deactivate", price_list="BULK")
        # Without Products asked, the product stays deleted: as the list detail, nothing is priced for it.
        row = recoveries.ask(copy, "pricing")

        assert run() == 1

        status, [result] = said(row)
        assert (status, result["created"], result["not_created"], result["refused"]) == ("done", 0, 2, "")
        assert sorted(reason["reason"].split(":")[0] for reason in result["reasons"]) == [
            "not_found",
            "pricing.price_list_unavailable",
        ]
        assert prices(hub) == []
