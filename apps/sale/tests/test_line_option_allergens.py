"""The allergens of the options chosen for a dish add to its own (MODIFIER-F12). When the line is ordered it keeps
those of its product and those of every option picked, once each and in the order of the list of the fourteen, also
an option charged on a line of its own, and keeps them as it keeps its options: changing the option later does not
change the line. The customer's allergy warning (SALE-F41) and the round sent to the kitchen count them.
Inventory, Modifiers and Sales together, no mocks.
"""

import pytest
from live.context import system_context
from live.models import OutboxEvent

from apps.sale.models.orders import OrderLine
from apps.sale.tests.conftest import HUB_DB, A, run

pytestmark = HUB_DB

FOOD = "restaurant.food"
GENERIC = "product.generic"


def setup(name: str, data: dict):
    return run(name, data, system_context(A))


@pytest.fixture
def extras(product):
    """«Extras», up to four and repeatable: cheese with milk, no onion with none, a brioche bun with gluten and egg,
    and a glass of wine with sulphites that taxes at 21 % and so is charged on a line of its own. A burger with
    gluten, a dish with milk and sesame and a salad without allergens offer them."""
    setup("modifier.group.create", {"name": "Extras", "max_choices": 4, "allow_repeat": True})
    options = {
        "cheese": {"name": "Cheese", "price_delta": 100, "allergens": ["milk"]},
        "onion": {"name": "No onion"},
        "bun": {"name": "Brioche bun", "price_delta": 50, "allergens": ["gluten", "egg"]},
        "wine": {"name": "Wine", "price_delta": 300, "tax_category_key": GENERIC, "allergens": ["sulphites"]},
    }
    ids = {key: str(setup("modifier.option.create", {"group": "Extras", "price_delta": 0, **one}).id) for key, one in options.items()}
    dishes = (("Burger", "BUR", ["gluten"]), ("Bowl", "BOW", ["sesame", "milk"]), ("Salad", "SAL", []))
    for name, sku, allergens in dishes:
        dish = product(name, sku, 800, FOOD, allergens=allergens)
        setup("modifier.link.attach", {"group": "Extras", "product_id": str(dish.id)})
    return ids


def order(sku: str, *option_ids: str, order_id: str | None = None):
    """The check (a new one unless ``order_id``) and the line of ``sku`` with ``option_ids`` just added to it."""
    order_id = order_id or str(run("sale.order.open", {"label": "Table 4"}).id)
    data = {"order_id": order_id, "product": sku, "option_ids": list(option_ids)}
    return order_id, run("sale.order.add_line", data).lines[-1]


def fired_items(order_id: str) -> list[dict]:
    run("sale.order.fire", {"order_id": order_id})
    return OutboxEvent.objects.filter(name="sale.order.fired").order_by("-created_at", "-id").first().payload["items"]


def test_a_burger_with_gluten_ordered_with_cheese_says_gluten_and_milk(extras):
    _, line = order("BUR", extras["cheese"])
    assert line.allergens == ["gluten", "milk"]
    assert OrderLine.objects.get().allergens == ["gluten", "milk"]


def test_the_sum_follows_the_order_of_the_list_and_names_each_allergen_once(extras):
    _, line = order("BOW", extras["cheese"], extras["bun"], extras["cheese"])
    assert line.allergens == ["gluten", "egg", "milk", "sesame"]


def test_an_option_charged_on_a_line_of_its_own_adds_its_allergens_too(extras):
    _, line = order("BUR", extras["wine"])
    assert [child.name for child in line.modifier_lines] == ["Wine"]
    assert line.allergens == ["gluten", "sulphites"]


def test_a_dish_without_allergens_takes_its_options_and_an_option_without_adds_none(extras):
    order_id, salad = order("SAL", extras["cheese"])
    _, plain = order("SAL", extras["onion"], order_id=order_id)
    _, burger = order("BUR", extras["onion"], order_id=order_id)
    assert (salad.allergens, plain.allergens, burger.allergens) == (["milk"], [], ["gluten"])


def test_the_line_keeps_what_it_summed_when_the_option_changes_after(extras):
    order_id, _ = order("BUR", extras["cheese"])
    setup("modifier.option.update", {"id": extras["cheese"], "allergens": ["egg"]})
    (line,) = run("sale.order.get", {"order_id": order_id}).lines
    assert line.allergens == ["gluten", "milk"]
    (item,) = fired_items(order_id)
    assert item["allergens"] == ["gluten", "milk"]
    # A new line with the same option takes what Modifiers says now.
    assert order("BUR", extras["cheese"], order_id=order_id)[1].allergens == ["gluten", "egg"]


def test_the_customers_allergy_warns_of_an_allergen_only_the_option_brings(extras):
    order_id, line = order("BUR", extras["cheese"])
    data = {"order_id": order_id, "line_id": str(line.id), "allergy": ["milk"]}
    run("sale.order.set_line_allergy", data)
    (marked,) = run("sale.order.get", {"order_id": order_id}).lines
    assert (marked.allergy, marked.allergy_in_dish) == (["milk"], ["milk"])
    (item,) = fired_items(order_id)
    assert (item["allergens"], item["allergy"]) == (["gluten", "milk"], ["milk"])
