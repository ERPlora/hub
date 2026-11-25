"""Writes of the prices of a list (WORKBOOK PRICING-F07 and F08): add, change and remove one. A refusal writes
nothing and records no event."""

from decimal import Decimal

from live.errors import Conflict, InvalidPayload, NotFound

from apps.pricing.models import PriceItem

from .conftest import HUB_DB, make_item, make_list, make_product, make_service
from .test_services import events, no_events, refused, run

pytestmark = HUB_DB


def test_a_product_s_price_is_put_in_a_list_by_their_names():
    price_list = make_list("VIP")
    product = make_product("Shampoo", "SH-1", price=1500)
    row = run("pricing.price_item.add", {"price_list": "vip", "product": "sh-1", "price": 1200, "min_quantity": "10"})
    assert (row.name, row.sku, row.base_price, row.price, row.min_quantity) == ("Shampoo", "SH-1", 1500, 1200, Decimal("10.000"))
    assert events("pricing.price_item.added") == [
        {
            "id": str(row.id),
            "price_list_id": str(price_list.id),
            "product_id": str(product.id),
            "service_id": None,
            "min_quantity": "10.000",
            "price": 1200,
            "currency": "EUR",
        }
    ]


def test_a_service_s_price_keeps_a_copy_of_its_name():
    make_list("VIP")
    haircut = make_service("Haircut", price=1800)
    row = run("pricing.price_item.add", {"price_list": "VIP", "service": "haircut", "price": 1500})
    assert (row.kind, row.service_id, row.name, row.base_price) == ("service", haircut.id, "Haircut", None)
    assert PriceItem.objects.get().service_name == "Haircut"


def test_the_same_article_twice_from_the_same_quantity_is_refused():
    price_list = make_list("VIP")
    product = make_product("Shampoo", "SH-1")
    make_item(price_list, product, min_quantity="1")
    error = refused(Conflict, "pricing.price_item.add", {"price_list": "VIP", "product_id": str(product.id), "price": 1})
    assert (error.code, set(error.fields)) == ("pricing.price_item_exists", {"min_quantity"})
    assert PriceItem.objects.count() == 1


def test_a_price_needs_a_live_list_a_live_product_and_a_quantity_on_its_step():
    make_list("OFF", is_active=False)
    make_list("VIP")
    product = make_product("Shampoo", "SH-1")
    assert refused(Conflict, "pricing.price_item.add", {"price_list": "OFF", "product": "SH-1", "price": 1}).code == (
        "pricing.price_list_unavailable"
    )
    refused(NotFound, "pricing.price_item.add", {"price_list": "NOPE", "product": "SH-1", "price": 1})
    gone = make_product("Wax", "WX", is_deleted=True)
    refused(NotFound, "pricing.price_item.add", {"price_list": "VIP", "product_id": str(gone.id), "price": 1})
    error = refused(InvalidPayload, "pricing.price_item.add", {"price_list": "VIP", "product_id": str(product.id), "price": 1, "min_quantity": "1.5"})
    assert set(error.fields) == {"min_quantity"}
    by_weight = make_product("Coffee", "CF", unit="kg")
    run("pricing.price_item.add", {"price_list": "VIP", "product_id": str(by_weight.id), "price": 1, "min_quantity": "0.5"})
    make_service("Haircut")
    error = refused(InvalidPayload, "pricing.price_item.add", {"price_list": "VIP", "service": "Haircut", "price": 1, "min_quantity": "2.5"})
    assert set(error.fields) == {"min_quantity"}


def test_without_services_a_service_cannot_be_priced(monkeypatch):
    import apps.pricing.queries as queries
    from live.operations import UnknownOperation

    def missing(name):
        raise UnknownOperation(name)

    monkeypatch.setattr(queries.other_apps, "get", missing)
    make_list("VIP")
    error = refused(Conflict, "pricing.price_item.add", {"price_list": "VIP", "service": "Haircut", "price": 1})
    assert error.code == "pricing.services_unavailable"


def test_a_price_is_changed_and_removed():
    price_list = make_list("VIP")
    product = make_product("Shampoo", "SH-1")
    item = make_item(price_list, product, price=1200)
    make_item(price_list, product, price=1000, min_quantity="10")
    row = run("pricing.price_item.update", {"id": str(item.id), "price": 1100})
    assert row.price == 1100
    assert events("pricing.price_item.updated") == [{"id": str(item.id)}]
    run("pricing.price_item.update", {"id": str(item.id), "price": 1100})
    assert len(events("pricing.price_item.updated")) == 1
    error = refused(Conflict, "pricing.price_item.update", {"id": str(item.id), "min_quantity": "10"})
    assert error.code == "pricing.price_item_exists"
    removed = run("pricing.price_item.remove", {"price_list": "VIP", "product": "Shampoo"})
    assert removed.id == item.id
    assert events("pricing.price_item.removed") == [{"id": str(item.id), "price_list_id": str(price_list.id)}]
    refused(NotFound, "pricing.price_item.remove", {"id": str(item.id)})
    refused(NotFound, "pricing.price_item.update", {"id": str(item.id), "price": 1})
    assert PriceItem.objects.count() == 1


def test_the_prices_of_a_deactivated_list_are_not_changed_but_can_be_removed():
    price_list = make_list("OFF")
    item = make_item(price_list, make_product("Shampoo", "SH-1"), price=1200)
    price_list.is_active = False
    price_list.save()
    error = refused(Conflict, "pricing.price_item.update", {"id": str(item.id), "price": 1000})
    assert error.code == "pricing.price_list_unavailable"
    assert PriceItem.objects.get().price == 1200 and no_events()
    assert run("pricing.price_item.remove", {"id": str(item.id)}).id == item.id
