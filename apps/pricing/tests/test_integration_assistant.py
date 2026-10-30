"""The assistant's card for a write of pricing (FIX-HUB-PRICING-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is
hub#258): in Spanish, every datum it sends by the name the Price lists screens give it, never by the title pydantic
makes up from the field («Customer Group», «Rule»). The card is base's (``base.assistant.card``); the names are
pricing's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
from pathlib import Path

import pytest
from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

from .conftest import ctx_for, make_list, make_product

FRONTEND = Path(apps.get_app_config("pricing").path) / "frontend/locale"
SCREENS = json.loads((FRONTEND / "es.json").read_text())["pricing"]
SCREENS_EN = json.loads((FRONTEND / "en.json").read_text())["pricing"]


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def pricing_writes() -> list:
    return [
        op
        for op in registry.values()
        if op.app_label == "pricing" and op.kind == "command" and assistant.is_tool(op)
    ]


def test_no_datum_of_a_write_of_pricing_reaches_a_spanish_card_by_its_technical_name():
    """Every write of pricing the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = pricing_writes()
    assert len(writes) > 10  # positive control: the registry has pricing's writes
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def test_the_card_names_the_customer_group_said_by_its_name_as_the_forms_do():
    """A price list or a rule for a group the person names («los socios»): the forms' «Customer group»."""
    group, group_en = SCREENS["lists"]["form"]["group"], SCREENS_EN["lists"]["form"]["group"]
    assert SCREENS["rules"]["form"]["group"] == group
    for name in ("pricing.price_list.create", "pricing.price_list.update", "pricing.rule.create", "pricing.rule.update"):
        assert labels(assistant.card(get(name), {"customer_group": "Socios"}, "es")) == [group]
        assert labels(assistant.card(get(name), {"customer_group": "Socios"}, "en")) == [group_en]


def test_the_card_names_the_rule_it_changes_as_the_discount_rules_screen_does():
    """Editing, deactivating or activating a rule named by its code or name: «Regla de descuento», never «Rule»."""
    for name in ("pricing.rule.update", "pricing.rule.deactivate", "pricing.rule.activate"):
        assert labels(assistant.card(get(name), {"rule": "VERANO"}, "es")) == ["Regla de descuento"]
        assert labels(assistant.card(get(name), {"rule": "VERANO"}, "en")) == ["Discount rule"]


# ── A price in the currency of its list (BASE-F97) ────────────────────────────────────────────────────────────────────


def priced(card: dict) -> dict:
    """The price the card shows, as the screen paints it: its kind, its figure and its currency when it is not the
    business's."""
    [price] = [field for field in card["fields"] if field["name"] == "price"]
    return {key: price[key] for key in ("kind", "value", "money") if key in price}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("currency", "money"),
    [("USD", {"currency": "USD", "decimals": 2}), ("PLN", {"currency": "PLN", "decimals": 2})],
    ids=["dollars", "zlotys"],
)
@pytest.mark.parametrize("named", ["price_list_id", "price_list"], ids=["by its id", "by its code"])
def test_a_price_added_to_a_list_in_another_currency_is_said_in_that_currency(currency, money, named):
    """«Pon el champú a 15 en la lista de dólares»: the price goes in the minor unit of the list's currency, and the
    card said it in the business's («15,00 €»). It reads the list as the person, by what the write names it. A list
    is always in a currency with two decimals (``D_CURRENCY``): none in yen."""
    price_list = make_list("DOLARES", currency=currency)
    product = make_product("Shampoo", "SH-1")
    which = {"price_list_id": str(price_list.id), "price_list": "DOLARES"}[named]
    arguments = {named: which, "product_id": str(product.id), "price": 1500}
    card = assistant.card(get("pricing.price_item.add"), arguments, "es", ctx_for(language="es"))
    assert priced(card) == {"kind": "money", "value": 1500, "money": money}


@pytest.mark.django_db
def test_a_price_on_a_list_that_is_not_there_is_said_as_sent():
    """No currency made up: the write refuses a list that does not exist, and the card does not paint a price in one."""
    card = assistant.card(get("pricing.price_item.add"), {"price_list": "NADA", "product": "Shampoo", "price": 1500}, "es", ctx_for(language="es"))
    assert priced(card) == {"kind": "text", "value": 1500}
