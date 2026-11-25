"""Every write the assistant may run that takes a tax category — a till section, an open-price line, a product or a
category of Inventory, a service, an option, a menu, an invoice line, a tax rule or an alias — says it on its card by
the name the Taxes screens give it, in the person's language, with the rate it charges today in the business's country
(«Producto — general · 21 %», as the Sections screen), never by the key the apps keep («product.generic»), at any depth
(the open lines of a sale, the rows of an import). A rule says its category by its name alone: its country and its rate
are its own. A text the person said that names no category is said as said: the write refuses it."""

import json

import pytest
from live import assistant as shared
from live.operations import Operation, get

from apps.tax.models import TaxCategory, TaxRule
from apps.tax.tests.conftest import HUB_DB, ctx_for
from base import assistant
from base.tests.card_values import writes
from base.tests.test_assistant_yes_for_its_card import said, yes_to_its_card

#: The data by which a write takes a category of Taxes: its key, its name or an alias.
TAX_CATEGORY_DATA = {"tax_category_key", "default_tax_category_key"}
KEY = "product.generic"
NAMES = {"es": "Producto — general", "en": "Product — generic"}
RATES = {"es": "21\xa0%", "en": "21%"}
WITH_RATE = {language: f"{name} · {RATES[language]}" for language, name in NAMES.items()}


def category_paths(op: Operation) -> list[tuple[str, ...]]:
    """Where ``op``'s input takes a tax category, at any depth: the path of each such datum, a list's items as ``[]``."""
    schema = op.input.model_json_schema()
    defs = schema.get("$defs", {})
    found: list[tuple[str, ...]] = []

    def walk(prop: dict, path: tuple[str, ...], depth: int = 0) -> None:
        prop = shared.resolved(prop, defs)
        if depth > 8:
            return
        for branch in [*prop.get("anyOf", []), *prop.get("oneOf", [])]:
            walk(branch, path, depth + 1)
        if isinstance(prop.get("items"), dict):
            walk(prop["items"], (*path, "[]"), depth + 1)
        for name, inner in prop.get("properties", {}).items():
            if name in TAX_CATEGORY_DATA:
                found.append((*path, name))
            else:
                walk(inner, (*path, name), depth + 1)

    walk(schema, ())
    return sorted(set(found))


def sent_at(path: tuple[str, ...], value: str):
    """The arguments that send ``value`` at ``path`` and nothing else (one item in each list on the way)."""
    if not path:
        return value
    head, *rest = path
    return [sent_at(tuple(rest), value)] if head == "[]" else {head: sent_at(tuple(rest), value)}


def drawn(op: Operation, arguments: dict, language: str, ctx=None) -> str:
    card = assistant.cards.card(op, arguments, language, ctx or ctx_for(role="hub_owner", language=language))
    return json.dumps(card["fields"], ensure_ascii=False)


def is_rule_write(op: Operation) -> bool:
    return op.name.startswith("tax.rule.")


def sections(person) -> list[str]:
    op = get("sale.department.list")
    return [row.name for row in op(person, op.input()).rows]


@HUB_DB
@pytest.mark.parametrize("language", ["es", "en"])
def test_every_write_that_takes_a_tax_category_says_it_by_its_name_and_its_rate_today(language):
    """A till section «Varios» at the general rate: «Producto — general · 21 %», never «product.generic»; and so every
    other write of any app that takes one, but a rule's, which says the name alone."""
    cases = [(op, path) for op in writes() for path in category_paths(op)]
    apps_with_one = {op.app_label for op, _ in cases}
    assert {"sale", "inventory", "service", "modifier", "combo", "invoice", "tax"} <= apps_with_one  # positive control
    assert {is_rule_write(op) for op, _ in cases} == {True, False}
    otherwise = {
        f"{op.name}:{'.'.join(path)}": card
        for op, path in cases
        if json.dumps((NAMES if is_rule_write(op) else WITH_RATE)[language], ensure_ascii=False)
        not in (card := drawn(op, sent_at(path, KEY), language))
        or KEY in card
    }
    assert otherwise == {}


@HUB_DB
def test_a_rule_of_another_country_never_says_the_rate_of_the_businesss():
    """A Portuguese rule at 23 % on a Spanish business's card: Spain's 21 % beside it would read as the new one."""
    arguments = {"country_code": "PT", "tax_category_key": KEY, "rate_pct": "23"}
    card = drawn(get("tax.rule.create"), arguments, "es")
    assert (NAMES["es"] in card, '"23"' in card, "21" in card) == (True, True, False)


@HUB_DB
def test_a_category_with_no_rule_in_force_is_said_by_its_name_alone():
    TaxRule.objects.filter(category__key=KEY).update(is_active=False)
    card = drawn(get("sale.department.create"), {"name": "Varios", "tax_category_key": KEY}, "es")
    assert (f'"{NAMES["es"]}"' in card, "%" in card) == (True, False)


@HUB_DB
def test_the_yes_is_for_the_rate_the_card_said():
    """The rate changes between the card and the yes: nothing is created, and the new card says the new rate."""
    person = ctx_for(role="hub_owner", language="es")
    arguments = {"name": "Varios", "tax_category_key": KEY, "sort_order": 0}

    again = yes_to_its_card(
        person,
        "sale.department.create",
        arguments,
        lambda: TaxRule.objects.filter(category__key=KEY, parent=None).update(rate_pct="22"),
    )

    assert (again["executed"], dict(said(again))["tax_category_key"]) == ([], f"{NAMES['es']} · 22\xa0%")
    assert sections(person) == []


@HUB_DB
def test_the_yes_to_the_same_rate_creates_the_section():
    person = ctx_for(role="hub_owner", language="es")
    arguments = {"name": "Varios", "tax_category_key": KEY, "sort_order": 0}
    done = yes_to_its_card(person, "sale.department.create", arguments)
    assert [(row["name"], row["outcome"]) for row in done["executed"]] == [("sale.department.create", "ok")]
    assert sections(person) == ["Varios"]


@HUB_DB
def test_a_category_said_by_its_name_or_of_the_business_reads_as_the_taxes_screens_name_it():
    """The person may say a category by its name, in any of the two languages, and a business may have one of its
    own: the card says the name its Taxes screens show."""
    TaxCategory.objects.create(key="drink.craft_beer", name="Cervezas artesanas")
    write = get("sale.department.create")
    assert WITH_RATE["es"] in drawn(write, {"tax_category_key": "Product — generic"}, "es")
    assert "Cervezas artesanas" in drawn(write, {"tax_category_key": "drink.craft_beer"}, "en")


@HUB_DB
def test_a_text_that_names_no_category_is_said_as_said():
    """Words that name no category («chucherías») reach the card as the person said them, and the write refuses them;
    without a person at hand (an automation's card) nothing is read for anybody: the text goes as sent."""
    write = get("sale.department.create")
    assert '"chucherías"' in drawn(write, {"tax_category_key": "chucherías"}, "es")
    card = assistant.cards.card(write, {"tax_category_key": KEY}, "es")
    assert [field["value"] for field in card["fields"]] == [KEY]
