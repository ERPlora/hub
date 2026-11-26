"""Sending an order from the table's page (``online_order.public.send``), which its QR opens without a session.

The order is saved as pending, for the table whose QR carries the code, and its event goes to the outbox in the same
transaction. Every price is the server's: the customer names the dishes, the options and the set menu's dishes by their
ids, Modifiers values the options and Menus prices the set menu, and a price in the body is refused. What the menu does
not offer, a code that opens no table's page (regenerated, unknown, of a deleted table or of another business) and too
many orders in a row write nothing. The send reads only what it needs of the other apps and runs no other write.
"""

import uuid

import pytest
from live.errors import Conflict, NotFound
from live.models import OutboxEvent
from live.operations import Operation
from pydantic import ValidationError

from apps.combo.tests.conftest import make_combo, make_group, make_option
from apps.modifier.tests.conftest import group as modifier_group
from apps.modifier.tests.conftest import link as modifier_link
from apps.modifier.tests.conftest import option as modifier_option
from apps.online_order import services
from apps.online_order.models import Order, TableCode
from apps.online_order.schemas import PublicSendIn
from base.tenancy.context import use_hub
from base.tests.test_public_door import door, turn_off
from base.throttle import RateLimited

from .conftest import HOST, HUB_DB, A, B, make_table, regenerate, run, visitor

pytestmark = [HUB_DB, pytest.mark.usefixtures("spa_manifest", "hub_a", "hub_b")]

SEND = "online_order.public.send"


def send(code: str, *lines: dict):
    return run(SEND, {"code": code, "lines": list(lines)}, visitor())


def dish(product, quantity: int = 1, **more) -> dict:
    return {"product_id": str(product.id), "quantity": quantity, **more}


def table_of(code: str):
    return TableCode.objects.get(code=code).table_id


def lines() -> list[tuple]:
    order = Order.objects.get()
    return [
        (line.name, line.quantity, line.unit_price, line.notes, line.picks)
        for line in order.lines.order_by("position")
    ]


def outbox() -> list[tuple]:
    return list(OutboxEvent.objects.values_list("name", "scope_key", "payload"))


@pytest.fixture
def menu_of_the_day():
    combo = make_combo("Menu of the day", price=1350)
    starters = make_group(combo, "Starters", min_choices=1, max_choices=1)
    mains = make_group(combo, "Mains", min_choices=1, max_choices=1)
    lentils = make_option(starters, make_product_named("Lentils", 700))
    hake = make_option(mains, make_product_named("Hake", 1400), price_delta=200)
    make_option(mains, make_product_named("Omelette", 900))
    return combo, lentils, hake


def make_product_named(name: str, price: int):
    from apps.combo.tests.conftest import make_product

    return make_product(name, price=price, sku=name.upper()[:4], show_on_website=False)


def test_the_order_waits_as_pending_for_its_table_with_the_menu_s_prices(table_code, dishes):
    sent = send(table_code, dish(dishes["croquettes"], 2, notes="No salt"), dish(dishes["cola"]))
    order = Order.objects.get()
    assert (sent.id, sent.status, sent.total) == (order.id, "pending", 2 * 750 + 250)
    assert (order.table_id, order.status, order.total) == (table_of(table_code), "pending", 1750)
    assert lines() == [("Croquettes", 2, 750, "No salt", []), ("Cola", 1, 250, "", [])]


def test_its_event_goes_to_the_outbox_naming_the_order_and_its_table(table_code, dishes):
    OutboxEvent.objects.all().delete()
    sent = send(table_code, dish(dishes["cola"]))
    assert outbox() == [
        (
            "online_order.order.sent",
            A.key,
            {"order_id": str(sent.id), "table_id": str(table_of(table_code)), "total": 250},
        )
    ]


def test_a_dish_s_options_are_valued_by_modifiers(table_code, dishes):
    modifier_group("Sauces", min_choices=0, max_choices=2)
    aioli = modifier_option("Sauces", "Aioli", price_delta=50)
    modifier_link("Sauces", product_id=str(dishes["croquettes"].id))
    sent = send(table_code, dish(dishes["croquettes"], 2, option_ids=[str(aioli.id)]))
    assert sent.total == 2 * (750 + 50)
    assert lines() == [("Croquettes", 2, 800, "", [{"option_id": str(aioli.id), "name": "Aioli", "price_delta": 50}])]


def test_a_required_option_left_out_or_one_of_another_dish_writes_nothing(table_code, dishes):
    modifier_group("Doneness", min_choices=1, max_choices=1)
    rare = modifier_option("Doneness", "Rare")
    modifier_link("Doneness", product_id=str(dishes["croquettes"].id))
    with pytest.raises(Conflict) as short:
        send(table_code, dish(dishes["croquettes"]))
    with pytest.raises(Conflict) as foreign:
        send(table_code, dish(dishes["cola"], option_ids=[str(rare.id)]))
    assert (short.value.code, foreign.value.code) == ("modifier.choice_below_min", "modifier.option_not_offered")
    assert (Order.objects.count(), [name for name, *_rest in outbox() if name == "online_order.order.sent"]) == (0, [])


def test_options_with_modifiers_off_write_nothing(table_code, dishes, hub_a):
    modifier_group("Sauces", min_choices=0, max_choices=2)
    aioli = modifier_option("Sauces", "Aioli", price_delta=50)
    modifier_link("Sauces", product_id=str(dishes["croquettes"].id))
    turn_off(hub_a, "modifier")
    with pytest.raises(Conflict) as refused:
        send(table_code, dish(dishes["croquettes"], option_ids=[str(aioli.id)]))
    assert (refused.value.code, refused.value.fields, Order.objects.count()) == (
        "online_order.not_on_menu",
        {"lines.0": str(services.NOT_ON_MENU)},
        0,
    )


def test_a_set_menu_is_priced_by_menus_with_its_supplements(table_code, menu_of_the_day):
    combo, lentils, hake = menu_of_the_day
    picks = [{"option_id": str(lentils.id)}, {"option_id": str(hake.id)}]
    sent = send(table_code, {"combo_id": str(combo.id), "choices": picks, "notes": "Hake well done"})
    assert sent.total == 1350 + 200
    assert lines() == [
        (
            "Menu of the day",
            1,
            1550,
            "Hake well done",
            [
                {"option_id": str(lentils.id), "name": "Lentils", "course": "Starters", "quantity": 1, "price_delta": 0},
                {"option_id": str(hake.id), "name": "Hake", "course": "Mains", "quantity": 1, "price_delta": 200},
            ],
        )
    ]


def test_a_set_menu_short_of_a_course_or_with_a_dish_sold_out_writes_nothing(table_code, menu_of_the_day):
    combo, lentils, hake = menu_of_the_day
    with pytest.raises(Conflict) as short:
        send(table_code, {"combo_id": str(combo.id), "choices": [{"option_id": str(lentils.id)}]})
    hake.product.is_sold_out = True
    hake.product.save()
    with pytest.raises(Conflict) as sold_out:
        send(table_code, {"combo_id": str(combo.id), "choices": [{"option_id": str(lentils.id)}, {"option_id": str(hake.id)}]})
    assert (short.value.code, sold_out.value.code) == ("combo.group_incomplete", "combo.option_sold_out")
    assert Order.objects.count() == 0


@pytest.mark.parametrize("which", ["staff_meal", "gone", "unknown"])
def test_a_dish_the_menu_does_not_offer_writes_nothing(table_code, dishes, which):
    product = dishes.get(which) or type("Unknown", (), {"id": uuid.uuid7()})
    with pytest.raises(Conflict) as refused:
        send(table_code, dish(dishes["cola"]), dish(product))
    assert (refused.value.code, refused.value.fields) == (
        "online_order.not_on_menu",
        {"lines.1": str(services.NOT_ON_MENU)},
    )
    assert Order.objects.count() == 0


def test_a_set_menu_not_on_sale_or_with_menus_off_writes_nothing(table_code, menu_of_the_day, hub_a):
    combo, lentils, hake = menu_of_the_day
    picks = [{"option_id": str(lentils.id)}, {"option_id": str(hake.id)}]
    with pytest.raises(Conflict) as unknown:
        send(table_code, {"combo_id": str(uuid.uuid7()), "choices": picks})
    turn_off(hub_a, "combo")
    with pytest.raises(Conflict) as off:
        send(table_code, {"combo_id": str(combo.id), "choices": picks})
    assert [unknown.value.code, off.value.code] == ["online_order.not_on_menu"] * 2
    assert Order.objects.count() == 0


@pytest.mark.parametrize(
    "line",
    [
        {"product_id": "{p}", "price": 1},
        {"product_id": "{p}", "unit_price": 1},
        {"product_id": "{p}", "option_ids": [], "price_delta": 0},
    ],
)
def test_the_customer_never_says_a_price(client, table_code, dishes, line):
    body = {key: (str(dishes["croquettes"].id) if value == "{p}" else value) for key, value in line.items()}
    refused = door(client, SEND, {"code": table_code, "lines": [body]})
    assert refused.status_code == 422
    with pytest.raises(ValidationError):
        PublicSendIn.model_validate({"code": table_code, "lines": [{"product_id": body["product_id"]}], "total": 1})
    assert Order.objects.count() == 0


SOME = str(uuid.uuid7())


@pytest.mark.parametrize(
    "lines_sent",
    [
        [],
        [{}],
        [{"product_id": SOME, "combo_id": SOME}],
        [{"product_id": SOME, "choices": [{"option_id": SOME}]}],
        [{"combo_id": SOME, "option_ids": [SOME]}],
        [{"product_id": SOME, "quantity": 0}],
        [{"product_id": SOME, "quantity": 100}],
    ],
)
def test_an_order_of_nothing_or_a_line_that_is_not_one_thing_is_refused(lines_sent):
    with pytest.raises(ValidationError):
        PublicSendIn.model_validate({"code": "c" * 22, "lines": lines_sent})


def test_a_regenerated_unknown_or_deleted_table_s_code_writes_nothing(table_code, dishes):
    table = make_table("7")
    old = regenerate(table)
    regenerate(table)
    deleted = make_table("9")
    gone = regenerate(deleted)
    run("table.table.delete", {"id": str(deleted.id)})
    for code in (old, "x" * 22, gone):
        with pytest.raises(NotFound) as refused:
            send(code, dish(dishes["cola"]))
        assert refused.value.code == "online_order.qr_not_active"
    assert Order.objects.count() == 0


def test_the_phone_sends_through_the_door(client, table_code, dishes):
    answer = door(client, SEND, {"code": table_code, "lines": [dish(dishes["cola"], 3)]}, HTTP_ACCEPT_LANGUAGE="es")
    assert answer.status_code == 200
    order = Order.objects.get()
    assert answer.json() == {"id": str(order.id), "status": "pending", "total": 750}


def test_a_code_of_another_business_writes_nothing_in_either(client, hub_b, dishes):
    with use_hub(hub_b):
        theirs = regenerate(make_table("4"), scope=B)
    refused = door(client, SEND, {"code": theirs, "lines": [dish(dishes["cola"])]})
    assert (refused.status_code, refused.json()["error"]["code"]) == (404, "online_order.qr_not_active")
    other_host = door(client, SEND, {"code": theirs, "lines": [dish(dishes["cola"])]}, host=HOST, slug=B.key)
    assert other_host.status_code == 404
    assert Order.objects.count() == 0
    with use_hub(hub_b):
        assert Order.objects.count() == 0


def test_too_many_orders_from_one_table_or_in_the_business_are_refused(monkeypatch, table_code, dishes):
    monkeypatch.setattr(services, "TABLE_LIMIT", 2)
    monkeypatch.setattr(services, "BUSINESS_LIMIT", 3)
    send(table_code, dish(dishes["cola"]))
    send(table_code, dish(dishes["cola"]))
    with pytest.raises(RateLimited) as table_full:
        send(table_code, dish(dishes["cola"]))
    other = regenerate(make_table("5"))
    send(other, dish(dishes["cola"]))
    with pytest.raises(RateLimited) as business_full:
        send(regenerate(make_table("6")), dish(dishes["cola"]))
    assert (table_full.value.code, table_full.value.status) == ("base.rate_limited", 429)
    assert str(table_full.value.message) == str(business_full.value.message) == str(services.TOO_MANY_ORDERS)
    assert Order.objects.count() == 3


def test_the_send_reads_the_menu_and_writes_nothing_else(monkeypatch, table_code, dishes, menu_of_the_day):
    combo, lentils, hake = menu_of_the_day
    modifier_group("Sauces", min_choices=0, max_choices=2)
    aioli = modifier_option("Sauces", "Aioli", price_delta=50)
    modifier_link("Sauces", product_id=str(dishes["croquettes"].id))
    assert services.ORDER_READS == {"table.view_table", "inventory.view_product", "modifier.view", "combo.view"}
    called = []
    real = Operation.__call__

    def spy(self, ctx, data):
        called.append((self.name, self.kind, frozenset(ctx.permissions)))
        return real(self, ctx, data)

    monkeypatch.setattr(Operation, "__call__", spy)
    send(
        table_code,
        dish(dishes["croquettes"], option_ids=[str(aioli.id)]),
        {"combo_id": str(combo.id), "choices": [{"option_id": str(lentils.id)}, {"option_id": str(hake.id)}]},
    )
    assert {name for name, _kind, _held in called} == {
        SEND,
        "table.table.get",
        "inventory.product.list_for_sale",
        "modifier.selection.resolve",
        "combo.combo.for_sale",
        "combo.combo.resolve",
    }
    assert [name for name, kind, _held in called if kind == "command"] == [SEND]
    assert {held for name, _kind, held in called if name != SEND} == {
        frozenset({"online_order.public"} | services.ORDER_READS)
    }
