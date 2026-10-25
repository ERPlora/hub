"""The assistant's card for a write of inventory (FIX-HUB-INVENTORY-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is
hub#258): in Spanish, every datum it sends by the name the Inventory screens give it, never by the title pydantic makes
up from the field («Category Ids», «Initial Stock», «Dry Run»). The card is base's (``base.assistant.card``); the names
are inventory's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

FRONTEND = Path(apps.get_app_config("inventory").path) / "frontend/locale"
SCREENS = json.loads((FRONTEND / "es.json").read_text())["inventory"]
SCREENS_EN = json.loads((FRONTEND / "en.json").read_text())["inventory"]

#: The data Spanish calls by the code's very word: the card says what the screen (or the till's strip) says.
SPELLED_ALIKE = {
    "slug": SCREENS["categories"]["columns"]["slug"],
    # The category form does not show it; the till's strip paints it.
    "color": "Color",
}


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def inventory_writes() -> list:
    return [
        op for op in registry.values() if op.app_label == "inventory" and op.kind == "command" and assistant.is_tool(op)
    ]


def test_no_datum_of_a_write_of_inventory_reaches_a_spanish_card_by_its_technical_name():
    """Every write of inventory the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish (or the screen's word when Spanish spells it like the code), never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = inventory_writes()
    assert len(writes) > 10  # positive control: the registry has inventory's writes
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            name, label = field["name"], field["label"]
            if name in SPELLED_ALIKE:
                assert label == SPELLED_ALIKE[name], (op.name, name)
            elif name not in screen and label == name.title().replace("_", " "):
                technical.setdefault(op.name, []).append(name)
    assert technical == {}


def test_the_card_names_a_new_products_data_as_its_form_does():
    arguments = {"initial_stock": "5", "ean13": "8410000000000", "category_ids": ["x"]}
    form = ("initialStock", "ean13", "categories")
    create = get("inventory.product.create")
    assert labels(assistant.card(create, arguments, "es")) == [SCREENS["form"][key] for key in form]
    assert labels(assistant.card(create, arguments, "en")) == [SCREENS_EN["form"][key] for key in form]
    edit = assistant.card(get("inventory.product.update"), {"category_ids": [], "tax_category_key": "iva-21"}, "es")
    assert labels(edit) == [SCREENS["tax"]["label"], SCREENS["form"]["categories"]]


def test_the_card_names_an_import_and_its_rehearsal():
    """The rows of the file (the report's «Rows» alone is the very title pydantic makes up, so it cannot be a name of
    its own), and the rehearsal by what the preview does: it checks the file and creates nothing."""
    rehearsal = {"rows": [{"line": 1, "name": "Vino", "sku": "V1"}], "dry_run": True}
    for name in ("inventory.product.bulk_create", "inventory.category.bulk_create"):
        assert labels(assistant.card(get(name), {"rows": rehearsal["rows"]}, "es")) == ["Filas del fichero"]
    assert labels(assistant.card(get("inventory.product.bulk_create"), rehearsal, "es")) == [
        "Filas del fichero",
        "Solo revisar",
    ]
    assert labels(assistant.card(get("inventory.product.bulk_create"), rehearsal, "en")) == ["File rows", "Check only"]


def test_the_card_names_a_category_sold_out_and_a_count_as_their_screens_do():
    category = assistant.card(get("inventory.category.create"), {"name": "Vinos", "tax_category_key": "iva-21"}, "es")
    assert labels(category) == ["Nombre", SCREENS["categories"]["form"]["tax"]]
    sold_out = assistant.card(get("inventory.product.set_sold_out"), {"product": "Vino", "sold_out": True}, "es")
    assert labels(sold_out) == ["Producto", SCREENS["products"]["soldOut"]]
    count = assistant.card(get("inventory.stock.count"), {"product": "Vino", "stock": "4", "reason": "recuento"}, "es")
    assert labels(count) == ["Producto", SCREENS["stock"]["countQty"], "Motivo"]
    receipt = assistant.card(get("inventory.stock.receive"), {"items": [{"product": "Vino", "qty": "6"}]}, "es")
    assert labels(receipt) == [SCREENS["tabs"]["products"]]
