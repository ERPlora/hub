"""What Price Lists gives back from a separate copy of the business (BASE-F114, PRICING-F14).

The copy is no business, so it has no alias and the ORM never reaches it: the platform reads it through a direct,
read-only connection, and Price Lists answers with its own SQL over its models' names. Its prices: each one of a live
product or of a service that the business no longer has is put back by ``pricing.price_item.add``, the list detail's
own, unless the business has a price in that place again (the same list, article and from quantity). Price Lists goes
after Inventory (its ``requires``), so a deleted product is back, the same, before its prices are put; one the business
no longer had at all is back as a new one, with another id, and its prices go to that one, found by its SKU.

Then, end to end on real databases (``hubs.CopiedHubs``): the business's own and its copy, a clone of it.
"""

import uuid
from decimal import Decimal

import pytest
from django.apps import apps
from django.db import connection
from live.models import OutboxEvent

from apps.inventory.models import Product
from apps.inventory.tests.test_recovery import CATEGORIES, LINKS, PRODUCTS, a_tax_key, gone_altogether
from apps.pricing import queries
from apps.pricing.models import PriceItem
from apps.service.models import Service
from apps.service.tests.test_recovery import CATEGORIES as SERVICE_CATEGORIES
from apps.service.tests.test_recovery import NO_LINKS, SERVICES
from base.models import Hub
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

    # With its product's SKU, to find the product the business made again if that one is gone (none for a service).
    assert sorted(read, key=lambda one: one["id"]) == [
        {"id": one.id, "price_list_id": vip.id, "product_id": shampoo.id, "service_id": None, "price": 900,
         "min_quantity": Decimal("1.000"), "sku": "SH-1"},
        {"id": ten.id, "price_list_id": vip.id, "product_id": shampoo.id, "service_id": None, "price": 800,
         "min_quantity": Decimal("10.000"), "sku": "SH-1"},
        {"id": cut.id, "price_list_id": vip.id, "product_id": None, "service_id": haircut.id, "price": 1500,
         "min_quantity": Decimal("1.000"), "sku": None},
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
        "sku": product.sku if product else None,
    }


@pytest.fixture
def at_work():
    """A business at work (``use_hub``), as the platform always gives back a copy in one: Price Lists asks Services in
    it which service stands for one of the copy's."""
    with use_hub(Hub(slug="a")):
        yield


@pytest.mark.django_db
@pytest.mark.usefixtures("at_work")
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
    # The same for a service's place: the business priced that service in that list again.
    colour = make_service("Colour")
    make_item(bulk, None, price=2000, service_id=colour.id, service_name="Colour")
    service_put_back = a_price_of_the_copy(bulk, service=colour, price=1900)
    # Lacking: the same product from another quantity, and a service's.
    from_five = a_price_of_the_copy(bulk, product=shampoo, price=820, min_quantity="5")
    cut = a_price_of_the_copy(vip, service=haircut, price=1500)

    lacking = queries.prices_not_in_business([still, put_back, service_put_back, from_five, cut])

    # As the list detail's add takes each, with its id in the copy: its list, its one article, price and quantity.
    assert lacking == [
        {"id": from_five["id"], "price_list_id": bulk.id, "product_id": shampoo.id, "price": 820,
         "min_quantity": Decimal("5")},
        {"id": cut["id"], "price_list_id": vip.id, "service_id": haircut.id, "price": 1500,
         "min_quantity": Decimal("1")},
    ]


def test_with_nothing_read_nothing_is_lacking():
    assert queries.prices_not_in_business([]) == []


def a_price_of_a_product_gone(price_list, sku: str, **fields) -> dict:
    """A price of the copy whose product the business no longer holds at all: only its SKU says which article it was."""
    return a_price_of_the_copy(price_list, **fields) | {"product_id": uuid.uuid7(), "sku": sku}


def made_by_a_recovery(name: str, sku: str, **fields):
    """A product a recovery from a separate copy made again, as ``inventory.product.recover`` leaves it."""
    return make_product(name, sku, created_by=actor_of(uuid.uuid7()), **fields)


@pytest.mark.django_db
def test_a_product_no_longer_held_live_is_the_one_a_recovery_made_again_with_its_sku():
    vip = make_list("VIP")
    shampoo = made_by_a_recovery("Shampoo", "SH-1")
    gone = a_price_of_a_product_gone(vip, "SH-1", price=900)
    # Still held, but deleted (another product took its SKU since, so it never comes back): the same goes for it.
    old = make_product("Conditioner", "CO-1", is_deleted=True)
    conditioner = made_by_a_recovery("Conditioner", "CO-1")
    deleted = a_price_of_the_copy(vip, product=old, price=700)

    lacking = queries.prices_not_in_business([gone, deleted])

    assert lacking == [
        {"id": gone["id"], "price_list_id": vip.id, "product_id": shampoo.id, "price": 900,
         "min_quantity": Decimal("1")},
        {"id": deleted["id"], "price_list_id": vip.id, "product_id": conditioner.id, "price": 700,
         "min_quantity": Decimal("1")},
    ]


@pytest.mark.django_db
def test_the_copys_product_is_the_business_own_by_its_id_before_any_sku():
    vip = make_list("VIP")
    shampoo = make_product("Shampoo", "SH-2")
    made_by_a_recovery("Old shampoo", "SH-1")
    # The copy knew it by another SKU: it is still live here, so its price is its own.
    price = a_price_of_the_copy(vip, product=shampoo) | {"sku": "SH-1"}

    [lacking] = queries.prices_not_in_business([price])

    assert lacking["product_id"] == shampoo.id


@pytest.mark.django_db
def test_a_product_made_again_by_hand_or_deleted_since_takes_none_of_the_copys_prices():
    vip = make_list("VIP")
    # Made again by hand with the SKU: the business's own, priced as the business chose.
    make_product("Shampoo", "SH-1", created_by="ana")
    by_hand = a_price_of_a_product_gone(vip, "SH-1")
    # Made again by a recovery, then deleted by the business: its prices went with it.
    made_by_a_recovery("Conditioner", "CO-1", is_deleted=True)
    deleted = a_price_of_a_product_gone(vip, "CO-1")

    lacking = queries.prices_not_in_business([by_hand, deleted])

    # Each stays the copy's own product, which the list detail's add refuses as not found: not created, and why.
    assert [one["product_id"] for one in lacking] == [by_hand["product_id"], deleted["product_id"]]


@pytest.mark.django_db
def test_the_place_of_a_product_made_again_the_business_priced_since_stays_as_it_is():
    vip = make_list("VIP")
    shampoo = made_by_a_recovery("Shampoo", "SH-1")
    # Priced again by the business after the recovery made the product, at another price.
    make_item(vip, shampoo, price=950)
    taken = a_price_of_a_product_gone(vip, "SH-1", price=900)
    free = a_price_of_a_product_gone(vip, "SH-1", price=800, min_quantity="10") | {"product_id": taken["product_id"]}

    lacking = queries.prices_not_in_business([taken, free])

    assert [(one["id"], one["product_id"]) for one in lacking] == [(free["id"], shampoo.id)]


def a_price_of_a_service_gone(price_list, **fields) -> dict:
    """A price of the copy whose service the business no longer holds at all: another id is all that is left of it."""
    return a_price_of_the_copy(price_list, **fields) | {"service_id": uuid.uuid7()}


def made_again_for(there: uuid.UUID, name: str = "Haircut") -> Service:
    """A service a recovery made again for the copy's ``there``, as ``service.service.recover`` leaves it."""
    return make_service(name, created_by=actor_of(uuid.uuid7()), stands_for=there)


@pytest.mark.django_db
@pytest.mark.usefixtures("at_work")
def test_a_service_no_longer_held_is_the_one_a_recovery_made_again_for_it():
    vip = make_list("VIP")
    gone = a_price_of_a_service_gone(vip, price=1500)
    haircut = made_again_for(gone["service_id"])

    lacking = queries.prices_not_in_business([gone])

    assert lacking == [
        {"id": gone["id"], "price_list_id": vip.id, "service_id": haircut.id, "price": 1500,
         "min_quantity": Decimal("1")},
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures("at_work")
def test_the_copys_service_is_the_business_own_while_it_holds_it():
    vip = make_list("VIP")
    haircut = make_service("Haircut")
    made_again_for(haircut.id)

    [lacking] = queries.prices_not_in_business([a_price_of_the_copy(vip, service=haircut)])

    assert lacking["service_id"] == haircut.id


@pytest.mark.django_db
@pytest.mark.usefixtures("at_work")
def test_a_service_made_again_by_hand_takes_none_of_the_copys_prices():
    vip = make_list("VIP")
    # Made again by hand with the name: the business's own, priced as the business chose.
    make_service("Haircut", created_by="ana")
    by_hand = a_price_of_a_service_gone(vip)

    [lacking] = queries.prices_not_in_business([by_hand])

    # It stays the copy's own service, which the list detail's add refuses as not found: not created, and why.
    assert lacking["service_id"] == by_hand["service_id"]


@pytest.mark.django_db
@pytest.mark.usefixtures("at_work")
def test_the_place_of_a_service_made_again_the_business_priced_since_stays_as_it_is():
    vip, bulk = make_list("VIP"), make_list("BULK")
    taken = a_price_of_a_service_gone(vip, price=1500)
    haircut = made_again_for(taken["service_id"])
    # Priced again by the business after the recovery made the service, at another price.
    make_item(vip, None, price=1600, service_id=haircut.id, service_name="Haircut")
    # The same service in another list, and from another quantity in the same one: free places.
    other_list = a_price_of_the_copy(bulk, price=1400) | {"service_id": taken["service_id"]}
    from_five = a_price_of_the_copy(vip, price=1300, min_quantity="5") | {"service_id": taken["service_id"]}

    lacking = queries.prices_not_in_business([taken, other_list, from_five])

    assert [(one["id"], one["service_id"]) for one in lacking] == [
        (other_list["id"], haircut.id),
        (from_five["id"], haircut.id),
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures("at_work")
def test_without_services_each_price_keeps_the_copys_service(monkeypatch):
    from live.operations import UnknownOperation

    def missing(name):
        raise UnknownOperation(name)

    vip = make_list("VIP")
    gone = a_price_of_a_service_gone(vip)
    made_again_for(gone["service_id"])
    monkeypatch.setattr(queries, "get", missing)

    [lacking] = queries.prices_not_in_business([gone])

    # The list detail's add refuses it for the same reason: Services is not there.
    assert lacking["service_id"] == gone["service_id"]


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

    def test_a_product_gone_altogether_comes_back_as_a_new_one_with_its_prices(self, recoveries, every_app_on):
        hub, shampoo = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, shampoo)
        gone_altogether(hub, shampoo)
        row = recoveries.ask(copy, "pricing", "inventory")

        assert run() == 1

        assert said(row) == ("done", [CATEGORIES, PRODUCTS | {"created": 1}, LINKS, PRICES | {"created": 2}])
        with use_hub(hub):
            [made] = Product.objects.filter(sku="SH-1").values_list("pk", flat=True)
        assert made != shampoo
        assert prices(hub) == [("BULK", made, 800, Decimal("10.000")), ("VIP", made, 900, Decimal("1.000"))]
        # Asked again, nothing is put twice: its places are taken by the prices just put.
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

    def a_priced_service(self, recoveries, every_app_on):
        """A business with a service priced in a list, by their screens' operations: its id."""
        hub, _ = recoveries.business(every_app_on)
        haircut = run_in(hub, "service.service.create", name="Haircut", price=2000, tax_category_key=a_tax_key(hub)).id
        run_in(hub, "pricing.price_list.create", code="VIP", name="VIP prices")
        run_in(hub, "pricing.price_item.add", price_list="VIP", service_id=haircut, price=1500)
        return hub, haircut

    def lost(self, hub, service) -> None:
        """``service`` and its prices gone from the business altogether: no operation deletes a service, a lost
        database does."""
        with use_hub(hub):
            PriceItem.objects.filter(service_id=service).delete()
            Service.objects.filter(pk=service).delete()

    def test_a_service_gone_altogether_comes_back_as_a_new_one_with_its_prices(self, recoveries, every_app_on):
        hub, haircut = self.a_priced_service(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.lost(hub, haircut)
        # As Recoveries asks it, in the apps' order: Services before Price Lists.
        row = recoveries.ask(copy, "service", "pricing")

        assert run() == 1

        assert said(row) == (
            "done",
            [SERVICE_CATEGORIES, SERVICES | {"created": 1}, *NO_LINKS, PRICES | {"created": 1}],
        )
        with use_hub(hub):
            [made] = Service.objects.filter(name="Haircut").values_list("pk", flat=True)
            assert list(PriceItem.objects.values_list("price_list__code", "service_id", "price")) == [
                ("VIP", made, 1500)
            ]
        assert made != haircut
        # Asked again, nothing is put twice: its place is taken by the price just put.
        again = recoveries.ask(copy, "service", "pricing")
        assert run() == 1
        assert said(again) == ("done", [SERVICE_CATEGORIES, SERVICES, *NO_LINKS, PRICES])

    def test_a_service_made_again_by_hand_takes_none_of_the_copys_prices(self, recoveries, every_app_on):
        hub, haircut = self.a_priced_service(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.lost(hub, haircut)
        by_hand = run_in(hub, "service.service.create", name="Haircut", price=2200, tax_category_key=a_tax_key(hub)).id
        row = recoveries.ask(copy, "service", "pricing")

        assert run() == 1

        # Services holds it already (made again with its name, where it was): none is made, and its price stays out.
        status, [*services, prices_given] = said(row)
        assert (status, services) == ("done", [SERVICE_CATEGORIES, SERVICES, *NO_LINKS])
        assert (prices_given["created"], prices_given["not_created"]) == (0, 1)
        assert [reason["reason"].split(":")[0] for reason in prices_given["reasons"]] == ["service.service_not_found"]
        with use_hub(hub):
            assert not PriceItem.objects.filter(service_id=by_hand).exists()

    def test_with_services_turned_off_the_price_stays_out_and_says_why(self, recoveries, every_app_on):
        from base import activation
        from base.models import AppActivation

        hub, haircut = self.a_priced_service(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.lost(hub, haircut)
        with use_hub(hub):
            AppActivation.objects.filter(host=hub.slug, app="service").update(state="off")
            activation.forget(hub.slug)
        row = recoveries.ask(copy, "pricing")

        assert run() == 1

        # Services cannot be asked which service stands for the copy's: the recovery goes on, and the add says why.
        status, [result] = said(row)
        assert (status, result["created"], result["not_created"], result["refused"]) == ("done", 0, 1, "")
        assert [reason["reason"].split(":")[0] for reason in result["reasons"]] == ["pricing.services_unavailable"]
        with use_hub(hub):
            assert not PriceItem.objects.exists()
