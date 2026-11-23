"""«Take the soft drink off the Terraza list» (PRICING-F08): after removing a price from a price list, what the model
hears back is what the article costs on that list now, read after the removal: a lower quantity of that list, on a
customer group's list the general list's, or else the catalog's. Never the price just removed, which the model had
nothing else to go on before (hub#2235: «3.00 EUR» said for a soft drink that now costs 2.50 €).

The model only receives the tool's description and the JSON text of its result (``live.assistant.run_tool``).
"""

import json

import pytest
from live import assistant as shared
from live.operations import UnknownOperation, get

from apps.pricing.models import PriceItem

from .conftest import HUB_DB, ctx_for, make_group, make_item, make_list, make_product, make_service

pytestmark = HUB_DB

REMOVE = "pricing.price_item.remove"


def heard(arguments: dict, language: str = "en") -> dict:
    """The removal's result as the model receives it: the JSON text of the tool's outcome, for an admin."""
    outcome = shared.run_tool(ctx_for(language=language), get(REMOVE), json.dumps(arguments))
    assert outcome.outcome == "ok", outcome.content
    return json.loads(outcome.content)


def charged(answer: dict) -> tuple:
    return answer["price_now"], answer["price_now_list"], answer["currency"]


@pytest.mark.parametrize("language", ["en", "es"])
def test_off_the_terraza_list_the_soft_drink_is_charged_its_catalog_price_not_the_removed_one(language):
    terraza = make_list("TERRAZA", "Terraza")
    soft_drink = make_product("Soft drink", "SOFT", price=250)
    item = make_item(terraza, soft_drink, price=300)

    answer = heard({"price_list": "Terraza", "product": "Soft drink"}, language)

    assert answer["id"] == str(item.id)
    assert answer["name"] == "Soft drink"
    assert charged(answer) == (250, None, "EUR")
    assert not PriceItem.objects.exists()


def test_a_quantity_taken_off_a_list_leaves_that_list_s_price_for_the_next_lower_quantity():
    terraza = make_list("TERRAZA", "Terraza")
    beer = make_product("Beer", "BEER", price=250)
    make_item(terraza, beer, price=230)
    make_item(terraza, beer, price=200, min_quantity="6")
    make_item(terraza, beer, price=180, min_quantity="12")

    answer = heard({"price_list": "Terraza", "product": "Beer", "min_quantity": "12"})

    assert charged(answer) == (200, "Terraza", "EUR")


def test_off_a_list_in_another_currency_the_catalog_s_price_is_in_the_business_s_currency():
    dollars = make_list("USD", "Dollars", currency="USD")
    soft_drink = make_product("Soft drink", "SOFT", price=250)
    make_item(dollars, soft_drink, price=320)

    answer = heard({"price_list": "Dollars", "product": "Soft drink"})

    assert charged(answer) == (250, None, "EUR")


def test_off_a_customer_group_s_list_its_customers_pay_the_general_list_s_price():
    partners = make_list("SOCIOS", "Socios", customer_group_id=make_group("Partners").id)
    general = make_list("GEN", "General", is_default=True)
    beer = make_product("Beer", "BEER", price=250)
    make_item(partners, beer, price=180)
    make_item(general, beer, price=220)

    answer = heard({"price_list": "Socios", "product": "Beer"})

    assert charged(answer) == (220, "General", "EUR")


def test_off_a_group_s_list_without_tax_a_general_list_with_tax_does_not_step_in():
    """Prices with and without tax are never compared (PRICING-F13): the group buys without it."""
    partners = make_list("SOCIOS", "Socios", customer_group_id=make_group("Partners").id, tax_included=False)
    general = make_list("GEN", "General", is_default=True, tax_included=True)
    beer = make_product("Beer", "BEER", price=250)
    make_item(partners, beer, price=150)
    make_item(general, beer, price=220)

    answer = heard({"price_list": "Socios", "product": "Beer"})

    assert charged(answer) == (250, None, "EUR")


def test_off_a_list_used_by_its_name_the_general_list_does_not_step_in():
    """A list for no group is only used when it is asked for by name, and then alone (PRICING-F13)."""
    terraza = make_list("TERRAZA", "Terraza")
    general = make_list("GEN", "General", is_default=True)
    soft_drink = make_product("Soft drink", "SOFT", price=250)
    make_item(terraza, soft_drink, price=300)
    make_item(general, soft_drink, price=270)

    answer = heard({"price_list": "Terraza", "product": "Soft drink"})

    assert charged(answer) == (250, None, "EUR")


def test_off_a_list_a_service_is_charged_its_price_in_services():
    haircut = make_service("Haircut", price=1800)
    vip = make_list("VIP")
    make_item(vip, None, price=1500, service_id=haircut.id, service_name="Haircut")

    answer = heard({"price_list": "VIP", "service": "Haircut"})

    assert (answer["name"], *charged(answer)) == ("Haircut", 1800, None, "EUR")


def test_with_services_off_a_service_s_price_is_still_removed_and_what_it_costs_now_is_not_known(monkeypatch):
    import apps.pricing.queries as queries

    def missing(name):
        raise UnknownOperation(name)

    haircut = make_service("Haircut", price=1800)
    item = make_item(make_list("VIP"), None, price=1500, service_id=haircut.id, service_name="Haircut")
    monkeypatch.setattr(queries.other_apps, "get", missing)

    answer = heard({"id": str(item.id)})

    assert (answer["name"], answer["price_now"], answer["price_now_list"]) == ("Haircut", None, None)
    assert not PriceItem.objects.exists()


def test_the_description_names_the_price_it_answers_and_never_the_removed_one():
    text = shared.description(get(REMOVE))
    answered = set(get(REMOVE).output.model_fields)

    assert {"price_now", "price_now_list"} <= answered
    assert "price_now" in text and "price_now_list" in text
    assert "never the price just removed" in text
    assert "another list's price or the catalog's" not in text
