"""Services with the platform's assistant (flow service-business-currency): every amount a write of Services takes
is money for the assistant — the card the person confirms paints it in the business's currency (``kind == "money"``)
and the assistant's instructions tell the AI to send it in the minor unit of that currency (17 € → 1700, ¥17 → 17).
An amount is a ``Cents`` field of the schemas (bounded by ``MAX_CENTS``); a write that is a tool of the assistant with
such a field must hand it to the card as money, or the AI could send 65 for «65 €».

And by its name (FIX-HUB-SERVICE-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258): in Spanish, every datum a write
of Services sends reaches the card by the name the Services screens give it, never by the title pydantic makes up from
the field («Absorbed Id», «Tax Category Key», «Items»). The card is base's (``base.assistant.card``); the names are
service's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from live.operations import get, registry

from apps.service.schemas import MAX_CENTS
from base import assistant
from base.tests.test_assistant import named_by_the_screen

APP = Path(apps.get_app_config("service").path)
SCREENS = json.loads((APP / "frontend/locale/es.json").read_text())["service"]
SCREENS_EN = json.loads((APP / "frontend/locale/en.json").read_text())["service"]

#: The writes of Services the assistant calls, by name.
TOOLS = sorted(name for name, op in registry.items() if op.app_label == "service" and op.kind == "command" and assistant.is_tool(op))


def money_fields(name: str) -> list[str]:
    """The fields of the input of ``name`` that are an amount (``Cents``: at most ``MAX_CENTS``)."""
    schema = assistant._schema(get(name))
    defs = schema.get("$defs", {})
    return [field for field, prop in schema.get("properties", {}).items() if assistant._resolved(prop, defs).get("maximum") == MAX_CENTS]


def test_the_writes_with_an_amount_are_found():
    """The detector is not empty: a service's price and a voucher's closed price are among them."""
    found = {(name, field) for name in TOOLS for field in money_fields(name)}
    assert {("service.service.create", "price"), ("service.package.create", "fixed_price")} <= found


@pytest.mark.parametrize("language", ["es", "en"])
@pytest.mark.parametrize("name", TOOLS)
def test_every_amount_of_a_write_reaches_the_card_as_money(name, language):
    fields = money_fields(name)
    card = assistant.card(get(name), {field: 1500 for field in fields}, language)
    assert {field["name"]: field["kind"] for field in card["fields"]} == dict.fromkeys(fields, "money")


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def named_by_service(op, name: str, title: str | None) -> bool:
    """Whether service itself names the datum ``name`` of ``op``: by its schema's own title, by the ``verbose_name`` of
    one of its models, or by its own catalog. A title pydantic made up that another app's catalog happens to translate
    («Reference» → «Referencia», from Printing's) is not a name of Services: it changes if that app's text changes."""
    made_up = assistant._generated_title(name)
    with (APP / "locale/es/LC_MESSAGES/django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    return (
        bool(title and title != made_up)
        or assistant._verbose_name("service", op.name.split(".")[1], name) is not None
        or own.gettext(made_up) != made_up
    )


def test_no_datum_of_a_write_of_service_reaches_a_spanish_card_by_its_technical_name():
    """Every write of service the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up. By where the name comes from, not by the word: «Color» is said the same
    in both languages and is its model's."""
    screen = named_by_the_screen()
    assert len(TOOLS) >= 25  # positive control: the registry has service's writes
    technical: dict[str, list[str]] = {}
    for name in TOOLS:
        op = get(name)
        props = assistant._schema(op).get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            datum = field["name"]
            if datum not in screen and not named_by_service(op, datum, props[datum].get("title")):
                technical.setdefault(name, []).append(datum)
    assert technical == {}


def test_the_card_names_the_duplicate_customer_whose_vouchers_move():
    """Customers merges a duplicate card into the one that stays: the duplicate as its merge screen calls it."""
    reassign = get("service.grant.reassign")
    assert labels(assistant.card(reassign, {"absorbed_id": "x"}, "es")) == ["Ficha duplicada"]
    assert labels(assistant.card(reassign, {"absorbed_id": "x"}, "en")) == ["Duplicate customer"]


def test_the_card_names_the_tax_category_of_a_service_as_its_form():
    for name in ("service.service.create", "service.service.update"):
        arguments = {"tax_category_key": "general"}
        assert labels(assistant.card(get(name), arguments, "es")) == [SCREENS["services"]["form"]["tax"]]
        assert labels(assistant.card(get(name), arguments, "en")) == [SCREENS_EN["services"]["form"]["tax"]]
    settings = get("service.settings.update")
    arguments = {"default_tax_category_key": "general"}
    assert labels(assistant.card(settings, arguments, "es")) == [SCREENS["settings"]["defaultTax"]]
    assert labels(assistant.card(settings, arguments, "en")) == [SCREENS_EN["settings"]["defaultTax"]]


def test_the_card_names_the_services_a_package_includes_as_its_form():
    create = get("service.package.create")
    arguments = {"items": [{"service": "Corte"}]}
    assert labels(assistant.card(create, arguments, "es")) == [SCREENS["packages"]["form"]["lines"]]
    assert labels(assistant.card(create, arguments, "en")) == [SCREENS_EN["packages"]["form"]["lines"]]


def test_the_card_names_the_refund_or_void_that_gives_sessions_back():
    """Sales gives back the sessions spent in a sale it refunds or voids: the card names that document by what it is,
    with service's own words, not with the «Referencia» another app's catalog lends to pydantic's «Reference»."""
    give_back = get("service.session.return")
    assert labels(assistant.card(give_back, {"reference": "x"}, "es")) == ["Devolución o anulación"]
    assert labels(assistant.card(give_back, {"reference": "x"}, "en")) == ["Refund or void"]
    with translation.override("es"):
        assert translation.gettext("Reference") == "Referencia"  # the lent word the guardrail must not take for one
