"""The assistant's card for a write of combo (FIX-HUB-COMBO-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258):
in Spanish, every datum it sends by the name the Menus screens give it, never by the title pydantic makes up from the
field («Group Ids», «New Product», «Tax Category Key»). The card is base's (``base.assistant.card``); the names are
combo's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

FRONTEND = Path(apps.get_app_config("combo").path) / "frontend/locale"
SCREENS = json.loads((FRONTEND / "es.json").read_text())["combo"]
SCREENS_EN = json.loads((FRONTEND / "en.json").read_text())["combo"]


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def combo_writes() -> list:
    return [
        op
        for op in registry.values()
        if op.app_label == "combo" and op.kind == "command" and assistant.is_tool(op)
    ]


def test_no_datum_of_a_write_of_combo_reaches_a_spanish_card_by_its_technical_name():
    """Every write of combo the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = combo_writes()
    assert len(writes) > 10  # positive control: the registry has combo's writes
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def test_the_card_names_the_courses_of_a_menu_put_in_a_new_order():
    """Dragging the courses of a menu: the builder's «Platos», never «Group Ids»."""
    reorder = get("combo.group.reorder")
    arguments = {"combo": "Menú del día", "group_ids": ["x", "y"]}
    assert labels(assistant.card(reorder, arguments, "es")) == ["Menú", SCREENS["courses"]["title"]]
    assert labels(assistant.card(reorder, arguments, "en")) == ["Menu", SCREENS_EN["courses"]["title"]]
    assert labels(assistant.card(reorder, {"group_ids": "x"}, "es")) == ["Platos"]


def test_the_card_names_the_choices_of_a_course_put_in_a_new_order():
    """Dragging the choices of a course: the builder's «Elecciones», never «Option Ids»."""
    reorder = get("combo.option.reorder")
    arguments = {"group": "Primeros", "option_ids": ["x", "y"]}
    assert labels(assistant.card(reorder, arguments, "es")) == ["Plato", SCREENS["choices"]["title"]]
    assert labels(assistant.card(reorder, arguments, "en")) == ["Course", SCREENS_EN["choices"]["title"]]


def test_the_card_names_the_products_added_at_once_to_a_course():
    """«Añadir varios»: the products ticked go to the course, as its sheet «Añadir productos a este plato» says."""
    bulk = get("combo.option.bulk_create")
    arguments = {"group": "Postres", "product_ids": ["x", "y"]}
    assert labels(assistant.card(bulk, arguments, "es")) == ["Plato", "Productos"]
    assert labels(assistant.card(bulk, arguments, "en")) == ["Course", "Products"]


def test_the_card_names_the_product_that_replaces_a_choice_apart_from_the_one_it_replaces():
    """Changing the lentils of the starters for the soup: «Producto» is the choice's own, never the one that comes in."""
    update = get("combo.option.update")
    arguments = {"product": "Lentejas", "new_product_id": "x", "new_product": "Sopa"}
    assert labels(assistant.card(update, arguments, "es")) == ["Producto", "Producto nuevo", "Producto nuevo"]
    assert labels(assistant.card(update, arguments, "en")) == ["Product", "New product", "New product"]


def test_the_card_names_the_vat_rate_of_a_menu_as_its_form():
    """The menu form's «Tipo de IVA», never «Tax Category Key»."""
    assert SCREENS["form"]["taxCategory"] == "Tipo de IVA"
    for name in ("combo.combo.create", "combo.combo.update"):
        arguments = {"tax_category_key": "restaurant.food"}
        assert labels(assistant.card(get(name), arguments, "es")) == [SCREENS["form"]["taxCategory"]]
        assert labels(assistant.card(get(name), arguments, "en")) == [SCREENS_EN["form"]["taxCategory"]]


def test_the_card_names_the_sku_of_a_product_gone_from_the_catalogue():
    """A product deleted in Inventory leaves the menus: its «SKU», as Inventory says it, never «Sku»."""
    drop = get("combo.option.drop_product")
    arguments = {"id": "x", "sku": "LEN-01", "name": "Lentejas"}
    assert labels(assistant.card(drop, arguments, "es")) == ["Id", "SKU", "Nombre"]
    assert labels(assistant.card(drop, arguments, "en")) == ["Id", "SKU", "Name"]
