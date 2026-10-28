"""The assistant's card for a write of modifier (FIX-HUB-MODIFIER-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is
hub#258): in Spanish, every datum it sends by the name the Modifiers screens give it, never by the title pydantic makes
up from the field («Option», «Tax Category Key»). The card is base's (``base.assistant.card``); the names are
modifier's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

FRONTEND = Path(apps.get_app_config("modifier").path) / "frontend/locale"
SCREENS = json.loads((FRONTEND / "es.json").read_text())["modifier"]
SCREENS_EN = json.loads((FRONTEND / "en.json").read_text())["modifier"]


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def modifier_writes() -> list:
    return [
        op
        for op in registry.values()
        if op.app_label == "modifier" and op.kind == "command" and assistant.is_tool(op)
    ]


def test_no_datum_of_a_write_of_modifier_reaches_a_spanish_card_by_its_technical_name():
    """Every write of modifier the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = modifier_writes()
    assert len(writes) >= 10  # positive control: the registry has modifier's writes
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def test_the_card_names_the_option_said_by_its_name_as_the_group_sheet_does():
    """Changing or deleting an option the person names («Sin cebolla»): «Opción», as «Borrar opción» says it."""
    for name in ("modifier.option.update", "modifier.option.delete"):
        assert labels(assistant.card(get(name), {"option": "Sin cebolla"}, "es")) == ["Opción"]
        assert labels(assistant.card(get(name), {"option": "No onion"}, "en")) == ["Option"]


def test_the_card_names_the_own_tax_category_of_an_option_as_its_form_does():
    """An option that taxes differently from the dish: the option form's «Categoría fiscal propia»."""
    tax, tax_en = SCREENS["options"]["form"]["tax"], SCREENS_EN["options"]["form"]["tax"]
    for name in ("modifier.option.create", "modifier.option.update"):
        arguments = {"tax_category_key": "product.generic"}
        assert labels(assistant.card(get(name), arguments, "es")) == [tax]
        assert labels(assistant.card(get(name), arguments, "en")) == [tax_en]
