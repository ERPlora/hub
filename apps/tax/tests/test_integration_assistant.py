"""The assistant's confirmation card names each datum of a write of Taxes by a name of the app's own
(FIX-HUB-TAX-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258): in Spanish, never by the title pydantic makes
up from the field («Tax Category Key»), nor by a word another app's catalog happens to lend. The card is base's
(``base.assistant.card``); the names are tax's: the titles of its schemas and the ``verbose_name`` of its models, with
their Spanish in its catalog, as its screens (the rules, the aliases and their forms) say them."""

import gettext
import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

APP = Path(apps.get_app_config("tax").path)
SCREENS = json.loads((APP / "frontend/locale/es.json").read_text())["tax"]
SCREENS_EN = json.loads((APP / "frontend/locale/en.json").read_text())["tax"]

#: The writes of Taxes the assistant calls, by name.
TOOLS = sorted(
    name for name, op in registry.items() if op.app_label == "tax" and op.kind == "command" and assistant.is_tool(op)
)
#: The writes that name an existing category (by its key, its name or an alias).
NAME_A_CATEGORY = ("tax.alias.create", "tax.rule.create", "tax.rule.activate", "tax.rule.deactivate", "tax.rule.end")


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def named_by_tax(op, name: str, title: str | None) -> bool:
    """Whether tax itself names the datum ``name`` of ``op``: by its schema's own title, by the ``verbose_name`` of
    one of its models, or by its own catalog. A title pydantic made up that another app's catalog happens to translate
    is not a name of Taxes: it changes if that app's text changes."""
    made_up = assistant._generated_title(name)
    with (APP / "locale/es/LC_MESSAGES/django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    return (
        bool(title and title != made_up)
        or assistant._verbose_name("tax", op.name.split(".")[1], name) is not None
        or own.gettext(made_up) != made_up
    )


def test_no_datum_of_a_write_of_tax_reaches_a_spanish_card_by_its_technical_name():
    """Every write of tax the assistant may ask for, with all its data: each datum by a name of its own in Spanish,
    never the one pydantic makes up. By where the name comes from, not by the word."""
    screen = named_by_the_screen()
    assert len(TOOLS) >= 8  # positive control: the registry has tax's writes
    technical: dict[str, list[str]] = {}
    for name in TOOLS:
        op = get(name)
        props = assistant._schema(op).get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            datum = field["name"]
            if datum not in screen and not named_by_tax(op, datum, props[datum].get("title")):
                technical.setdefault(name, []).append(datum)
    assert technical == {}


def test_the_card_names_the_category_of_a_write_as_the_rules_and_aliases_screens():
    """By its key, its name or an alias, the category a rule or an alias belongs to is «Categoría», as the columns and
    forms of Rules and Aliases say it — in every write that names one."""
    assert SCREENS["rules"]["columns"]["category"] == SCREENS["aliases"]["columns"]["category"]
    for name in NAME_A_CATEGORY:
        card_es = assistant.card(get(name), {"tax_category_key": "cerveza"}, "es")
        card_en = assistant.card(get(name), {"tax_category_key": "beer"}, "en")
        assert labels(card_es) == [SCREENS["rules"]["columns"]["category"]], name
        assert labels(card_en) == [SCREENS_EN["rules"]["columns"]["category"]], name


def test_the_card_names_a_new_alias_as_the_aliases_screen():
    """«Alias», «Categoría» and «Origen», as the columns of Aliases say them."""
    create = get("tax.alias.create")
    arguments = {"alias": "caña", "tax_category_key": "cerveza", "source": "learned"}
    columns, columns_en = SCREENS["aliases"]["columns"], SCREENS_EN["aliases"]["columns"]
    assert labels(assistant.card(create, arguments, "es")) == [
        columns["alias"],
        columns["category"],
        columns["source"],
    ]
    assert labels(assistant.card(create, arguments, "en")) == [
        columns_en["alias"],
        columns_en["category"],
        columns_en["source"],
    ]
