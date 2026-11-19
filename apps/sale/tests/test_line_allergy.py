"""The customer's allergy on a line of a check (SALE-F41): the waiter marks, on a line not sent yet, the allergens of
the fourteen the person eating it must not have. The live check says it and which of them the dish contains (in a
menu, dish by dish), and the round sent to the kitchen carries it; the ticket, the invoice and the bill printed for the
table do not. Inventory, Menus and Sales together, no mocks.
"""

import dataclasses
import json

import pytest
from django.utils import translation
from live.assistant.running import invalid_arguments
from live.context import system_context
from live.errors import Conflict, PermissionDenied
from live.models import OutboxEvent
from live.operations import get

from apps.sale import paper
from apps.sale.models import Order, OrderLine, SaleLine
from apps.sale.schemas import PreviewLineOut
from apps.sale.tests.conftest import HOST, HUB_DB, B, ctx_for, run
from apps.sale.tests.test_assistant_card_records import fields_of
from apps.sale.tests.test_line_allergens import (
    FOOD,
    LETTERHEAD,
    add,
    add_menu,
    fired_items,
    kitchen,
    live_check,
    open_check,
)
from base.tenancy.context import use_hub

pytestmark = HUB_DB
#: The fixture taken from the tests of the dish's allergens: a burger, a salad, a flan and «Burger menu».
__all__ = ["kitchen"]

NOT_ONE_OF_THE_FOURTEEN = {
    "en": "That allergen is not one of the fourteen that must be declared.",
    "es": "Ese alérgeno no es uno de los catorce de declaración obligatoria.",
}


def mark(order_id: str, line_id, allergy: list[str], ctx=None):
    return run("sale.order.set_line_allergy", {"order_id": order_id, "line_id": str(line_id), "allergy": allergy}, ctx)


def changes(order_id: str) -> int:
    return OutboxEvent.objects.filter(name="sale.order.changed", payload__order_id=order_id).count()


def post(client, path: str, data: dict, language: str = "en"):
    return client.post(
        f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE=language
    )


@pytest.fixture
def waiter_client(client, make_user):
    client.force_login(make_user("ana", role="hub_employee"))
    return client


def test_a_pending_line_keeps_the_customers_allergy_in_the_order_of_the_list(kitchen):
    order_id = open_check()
    line_id = add(order_id, "BUR").lines[0].id
    (line,) = mark(order_id, line_id, ["milk", "gluten"]).lines
    assert line.allergy == ["gluten", "milk"]
    assert OrderLine.objects.get(pk=line_id).allergy == ["gluten", "milk"]


def test_the_live_check_says_which_of_the_allergy_the_dish_contains(kitchen):
    order_id = open_check()
    burger_id = add(order_id, "BUR").lines[0].id
    salad_id = add(order_id, "SAL").lines[1].id
    mark(order_id, burger_id, ["fish", "gluten"])
    mark(order_id, salad_id, ["gluten"])
    burger, salad = live_check(order_id).lines
    assert (burger.allergy, burger.allergy_in_dish) == (["gluten", "fish"], ["gluten"])
    assert (salad.allergy, salad.allergy_in_dish) == (["gluten"], [])


def test_a_line_without_an_allergy_says_none_and_nothing_in_the_dish(kitchen):
    order_id = open_check()
    add(order_id, "BUR")
    (burger,) = live_check(order_id).lines
    assert (burger.allergy, burger.allergy_in_dish) == ([], [])
    assert all(dish.allergy_in_dish == [] for dish in add_menu(order_id, kitchen["options"]).lines[1].combo.components)


def test_in_a_menu_the_allergy_is_the_lines_and_each_dish_names_what_it_contains(kitchen):
    order_id = open_check()
    menu_id = add_menu(order_id, kitchen["options"]).lines[0].id
    (menu,) = mark(order_id, menu_id, ["egg", "milk"]).lines
    assert (menu.allergy, menu.allergy_in_dish) == (["egg", "milk"], [])
    assert [(dish.product_name, dish.allergy_in_dish) for dish in menu.combo.components] == [
        ("Burger", ["milk"]),
        ("Flan", ["egg", "milk"]),
    ]


def test_unmarking_them_all_takes_the_allergy_off(kitchen):
    order_id = open_check()
    line_id = add(order_id, "BUR").lines[0].id
    mark(order_id, line_id, ["gluten"])
    (line,) = mark(order_id, line_id, []).lines
    assert (line.allergy, line.allergy_in_dish) == ([], [])
    assert OrderLine.objects.get(pk=line_id).allergy == []


def test_marking_it_tells_the_check_changed(kitchen):
    order_id = open_check()
    line_id = add(order_id, "BUR").lines[0].id
    before, told = Order.objects.get(pk=order_id).version, changes(order_id)
    mark(order_id, line_id, ["gluten"])
    assert Order.objects.get(pk=order_id).version == before + 1
    assert changes(order_id) == told + 1


def test_the_same_allergy_again_changes_nothing_and_tells_nothing(kitchen):
    order_id = open_check()
    line_id = add(order_id, "BUR").lines[0].id
    mark(order_id, line_id, ["gluten", "milk"])
    before, told = Order.objects.get(pk=order_id).version, changes(order_id)
    (line,) = mark(order_id, line_id, ["milk", "gluten"]).lines
    assert line.allergy == ["gluten", "milk"]
    assert (Order.objects.get(pk=order_id).version, changes(order_id)) == (before, told)


def test_a_line_already_sent_to_the_kitchen_is_refused_and_keeps_what_it_had(kitchen, waiter_client):
    order_id = open_check()
    line_id = add(order_id, "BUR").lines[0].id
    mark(order_id, line_id, ["gluten"])
    fired_items(order_id)
    data = {"order_id": order_id, "line_id": str(line_id), "allergy": ["milk"]}
    response = post(waiter_client, "/sale/orders/set_line_allergy", data)
    assert (response.status_code, response.json()["error"]["code"]) == (409, "sale.order_line_not_available")
    assert OrderLine.objects.get(pk=line_id).allergy == ["gluten"]


def test_a_line_of_a_check_no_longer_open_is_refused(kitchen):
    order_id = open_check()
    line_id = add(order_id, "BUR").lines[0].id
    run("sale.order.void", {"order_id": order_id})
    with pytest.raises(Conflict) as refused:
        mark(order_id, line_id, ["gluten"])
    assert refused.value.code == "sale.order_changed"


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_api_refuses_an_allergen_off_the_list_on_its_field(kitchen, waiter_client, language):
    order_id = open_check()
    line_id = add(order_id, "BUR").lines[0].id
    data = {"order_id": order_id, "line_id": str(line_id), "allergy": ["gluten", "nuts"]}
    response = post(waiter_client, "/sale/orders/set_line_allergy", data, language)
    error = response.json()["error"]
    assert (response.status_code, error["code"]) == (422, "invalid_payload")
    assert error["fields"] == {"allergy": NOT_ONE_OF_THE_FOURTEEN[language]}
    assert OrderLine.objects.get(pk=line_id).allergy == []


def test_a_waiter_marks_it_through_the_api(kitchen, waiter_client):
    order_id = open_check()
    line_id = add(order_id, "BUR").lines[0].id
    data = {"order_id": order_id, "line_id": str(line_id), "allergy": ["sesame"]}
    response = post(waiter_client, "/sale/orders/set_line_allergy", data)
    (line,) = response.json()["lines"]
    assert (response.status_code, line["allergy"], line["allergy_in_dish"]) == (200, ["sesame"], ["sesame"])


def test_someone_who_may_not_sell_cannot_mark_it(kitchen):
    order_id = open_check()
    line_id = add(order_id, "BUR").lines[0].id
    ctx = ctx_for()
    no_selling = dataclasses.replace(ctx, permissions=frozenset(ctx.permissions) - {"sale.add_sale"})
    with pytest.raises(PermissionDenied):
        mark(order_id, line_id, ["gluten"], no_selling)
    assert OrderLine.objects.get(pk=line_id).allergy == []


def test_the_round_sent_to_the_kitchen_carries_each_lines_allergy(kitchen):
    order_id = open_check()
    burger_id = add(order_id, "BUR").lines[0].id
    add(order_id, "SAL")
    menu_id = add_menu(order_id, kitchen["options"]).lines[2].id
    mark(order_id, burger_id, ["gluten"])
    mark(order_id, menu_id, ["egg"])
    burger, salad, menu = fired_items(order_id)
    assert (burger["allergy"], salad["allergy"], menu["allergy"]) == (["gluten"], [], ["egg"])
    assert OrderLine.objects.get(pk=menu_id).allergy == ["egg"]


def test_a_line_split_in_units_keeps_the_allergy_on_each(kitchen):
    order_id = open_check()
    line_id = run("sale.order.add_line", {"order_id": order_id, "product": "BUR", "quantity": "2"}).lines[0].id
    mark(order_id, line_id, ["milk"])
    split = run("sale.order.split_line", {"order_id": order_id, "line_id": str(line_id)})
    assert [line.allergy for line in split.order.lines] == [["milk"]] * 2


def test_neither_the_ticket_nor_the_bill_for_the_table_says_it(kitchen):
    order_id = open_check()
    line_id = add(order_id, "BUR").lines[0].id
    mark(order_id, line_id, ["mustard"])
    valued = run("sale.checkout.preview", {"order_id": order_id})
    assert not {"allergy", "allergy_in_dish"} & set(PreviewLineOut.model_fields)
    with translation.override("es"):
        bill = paper.bill(valued, label="Table 4", letterhead=LETTERHEAD, decimals=2)
    assert "Mostaza" not in str(bill)
    charge = run(
        "sale.sale.complete",
        {"idempotency_key": "allergy-ticket", "order_id": order_id, "payments": [{"method": "card"}]},
    )
    sale = run("sale.sale.get", {"sale_id": str(charge.id)})
    assert not any(hasattr(line, "allergy") for line in sale.lines)
    assert not any(hasattr(line, "allergy") for line in SaleLine.objects.all())


def test_a_line_of_another_business_is_out_of_reach(kitchen, hub_b):
    water = {"name": "Water", "sku": "WAT", "price": 200, "tax_category_key": FOOD}
    with use_hub(hub_b):
        run("inventory.product.create", water, system_context(B))
        other = run("sale.order.open", {"lines": [{"product": "WAT"}]}, ctx_for(scope=B))
        told = changes(str(other.id))
    order_id = open_check()
    add(order_id, "BUR")
    with pytest.raises(Conflict) as refused:
        mark(order_id, other.lines[0].id, ["gluten"])
    assert refused.value.code == "sale.order_line_not_available"
    with use_hub(hub_b):
        assert OrderLine.objects.get(pk=other.lines[0].id).allergy == []
        assert changes(str(other.id)) == told


# By the assistant


def test_the_assistants_card_says_the_check_the_dish_and_the_allergy_by_their_names(kitchen):
    order_id = open_check()
    line_id = add(order_id, "BUR").lines[0].id
    arguments = {"order_id": order_id, "line_id": str(line_id), "allergy": ["milk", "gluten"]}
    fields = fields_of("sale.order.set_line_allergy", arguments, "es")
    assert (fields["order_id"]["value"], fields["line_id"]["value"]) == ("Table 4", "Burger")
    assert (fields["allergy"]["label"], fields["allergy"]["value"]) == ("Alergia del cliente", ["Leche", "Gluten"])


def test_the_assistant_hears_an_allergen_off_the_list_before_any_card_is_drawn(kitchen):
    order_id = open_check()
    line_id = add(order_id, "BUR").lines[0].id
    arguments = {"order_id": order_id, "line_id": str(line_id), "allergy": ["shellfish"]}
    refused = invalid_arguments(get("sale.order.set_line_allergy"), arguments)
    assert (refused.outcome, refused.code) == ("error", "invalid_payload")
    assert "allergy" in json.loads(refused.content)["error"]["fields"]
