"""Every write the assistant may run that takes a tax category — a till section, an open-price line, a product or a
category of Inventory, a service, an option, a menu, an invoice line, a tax rule or an alias — says it on its card by
the name the Taxes screens give it, in the person's language («Producto — general»), never by the key the apps keep
(«product.generic»), at any depth (the open lines of a sale, the rows of an import). A text the person said that names
no category is said as said: the write refuses it."""

import json

import pytest
from live import assistant as shared
from live.operations import Operation, get

from apps.tax.models import TaxCategory
from apps.tax.tests.conftest import HUB_DB, ctx_for
from base import assistant
from base.tests.card_values import writes

#: The data by which a write takes a category of Taxes: its key, its name or an alias.
TAX_CATEGORY_DATA = {"tax_category_key", "default_tax_category_key"}
KEY = "product.generic"
NAMES = {"es": "Producto — general", "en": "Product — generic"}


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


@HUB_DB
@pytest.mark.parametrize("language", ["es", "en"])
def test_every_write_that_takes_a_tax_category_says_it_by_its_name(language):
    """The case of the issue, a till section «Varios» at the general rate: «Producto — general», never
    «product.generic»; and so every other write of any app that takes one."""
    cases = [(op, path) for op in writes() for path in category_paths(op)]
    apps_with_one = {op.app_label for op, _ in cases}
    assert {"sale", "inventory", "service", "modifier", "combo", "invoice", "tax"} <= apps_with_one  # positive control
    by_key = {
        f"{op.name}:{'.'.join(path)}": said
        for op, path in cases
        if NAMES[language] not in (said := drawn(op, sent_at(path, KEY), language)) or KEY in said
    }
    assert by_key == {}


@HUB_DB
def test_a_category_said_by_its_name_or_of_the_business_reads_as_the_taxes_screens_name_it():
    """The person may say a category by its name, in any of the two languages, and a business may have one of its
    own: the card says the name its Taxes screens show."""
    TaxCategory.objects.create(key="drink.craft_beer", name="Cervezas artesanas")
    write = get("sale.department.create")
    assert NAMES["es"] in drawn(write, {"tax_category_key": "Product — generic"}, "es")
    assert "Cervezas artesanas" in drawn(write, {"tax_category_key": "drink.craft_beer"}, "en")


@HUB_DB
def test_a_text_that_names_no_category_is_said_as_said():
    """Words that name no category («chucherías») reach the card as the person said them, and the write refuses them;
    without a person at hand (an automation's card) nothing is read for anybody: the text goes as sent."""
    write = get("sale.department.create")
    assert '"chucherías"' in drawn(write, {"tax_category_key": "chucherías"}, "es")
    card = assistant.cards.card(write, {"tax_category_key": KEY}, "es")
    assert [field["value"] for field in card["fields"]] == [KEY]
