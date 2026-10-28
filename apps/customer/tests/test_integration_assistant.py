"""The assistant's card for a write of customer (FIX-HUB-CUSTOMER-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is
hub#258): in Spanish, every datum it sends by the name the Customers screens give it, never by the title pydantic makes
up from the field («Absorbed», «Group Ids», «Field Values»). The card is base's (``base.assistant.card``); the names are
customer's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

FRONTEND = Path(apps.get_app_config("customer").path) / "frontend/locale"
SCREENS = json.loads((FRONTEND / "es.json").read_text())["customer"]
SCREENS_EN = json.loads((FRONTEND / "en.json").read_text())["customer"]


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def customer_writes() -> list:
    return [
        op
        for op in registry.values()
        if op.app_label == "customer" and op.kind == "command" and assistant.is_tool(op)
    ]


def test_no_datum_of_a_write_of_customer_reaches_a_spanish_card_by_its_technical_name():
    """Every write of customer the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = customer_writes()
    assert len(writes) >= 20  # positive control: the registry has customer's writes
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def test_the_card_names_the_duplicate_card_merged_into_the_one_that_stays():
    """«Fusionar con…»: the card that stays is the customer, the one picked is the duplicate the merge screen asks for
    («Buscar la ficha duplicada»), by its id or by its name."""
    merge = get("customer.customer.merge")
    assert labels(assistant.card(merge, {"absorbed": "x"}, "es")) == ["Ficha duplicada"]
    arguments = {"customer": "Ana", "absorbed_id": "x", "absorbed": "Ana López"}
    assert labels(assistant.card(merge, arguments, "es")) == ["Cliente", "Ficha duplicada", "Ficha duplicada"]
    assert labels(assistant.card(merge, arguments, "en")) == ["Customer", "Duplicate customer", "Duplicate customer"]


def test_the_card_names_the_groups_and_tags_of_a_card_as_its_membership_sheet():
    """«Guardar grupos» and «Guardar etiquetas»: by their ids or by their names, «Grupos» and «Etiquetas»."""
    groups = get("customer.customer.set_groups")
    arguments = {"group_ids": ["x"], "groups": ["VIP"]}
    assert labels(assistant.card(groups, arguments, "es")) == [SCREENS["membership"]["groups"]] * 2
    assert labels(assistant.card(groups, arguments, "en")) == [SCREENS_EN["membership"]["groups"]] * 2
    tags = get("customer.customer.set_tags")
    arguments = {"tag_ids": ["x"], "tags": ["Alérgico"]}
    assert labels(assistant.card(tags, arguments, "es")) == [SCREENS["membership"]["tags"]] * 2
    assert labels(assistant.card(tags, arguments, "en")) == [SCREENS_EN["membership"]["tags"]] * 2


def test_the_card_names_the_custom_fields_of_an_edited_card_as_its_form():
    update = get("customer.customer.update")
    arguments = {"field_values": [{"field_id": "x", "value": "42"}]}
    assert labels(assistant.card(update, arguments, "es")) == [SCREENS["form"]["customFields"]]
    assert labels(assistant.card(update, arguments, "en")) == [SCREENS_EN["form"]["customFields"]]


def test_the_card_names_the_rows_of_a_csv_import():
    """«Importar CSV»: the file's rows, as its summary counts them («{total} filas»)."""
    imported = get("customer.customer.import")
    assert labels(assistant.card(imported, {"rows": [{"name": "Ana"}]}, "es")) == ["Filas a importar"]
    assert labels(assistant.card(imported, {"rows": [{"name": "Ana"}]}, "en")) == ["Rows to import"]


def test_the_card_names_a_group_and_its_colour_never_by_their_technical_names():
    """The group's sheet says «Color»: the card says whose colour it is, since «Color» alone is the field's own name;
    the group it acts on, when named, is «Grupo»."""
    assert SCREENS["groups"]["color"] == "Color"
    for name in ("customer.group.create", "customer.group.update"):
        assert labels(assistant.card(get(name), {"color": "success"}, "es")) == ["Color del grupo"]
        assert labels(assistant.card(get(name), {"color": "success"}, "en")) == ["Group color"]
    for name in ("customer.group.update", "customer.group.delete"):
        assert labels(assistant.card(get(name), {"group": "VIP"}, "es")) == ["Grupo"]
        assert labels(assistant.card(get(name), {"group": "VIP"}, "en")) == ["Group"]


def test_the_card_names_a_tag_and_its_colour_never_by_their_technical_names():
    assert SCREENS["tags"]["color"] == "Color"
    for name in ("customer.tag.create", "customer.tag.update"):
        assert labels(assistant.card(get(name), {"color": "success"}, "es")) == ["Color de la etiqueta"]
        assert labels(assistant.card(get(name), {"color": "success"}, "en")) == ["Tag color"]
    for name in ("customer.tag.update", "customer.tag.delete"):
        assert labels(assistant.card(get(name), {"tag": "Alérgico"}, "es")) == ["Etiqueta"]
        assert labels(assistant.card(get(name), {"tag": "Alérgico"}, "en")) == ["Tag"]


def test_the_card_names_a_note_and_its_author():
    """«Añadir nota»: the note as its field says («Nota»), and who wrote it when it is not the person signed in."""
    note = get("customer.note.add")
    arguments = {"customer": "Ana", "content": "Prefiere mesa junto a la ventana", "author_name": "Luis"}
    assert labels(assistant.card(note, arguments, "es")) == ["Cliente", SCREENS["notes"]["label"], "Autor"]
    assert labels(assistant.card(note, arguments, "en")) == ["Customer", SCREENS_EN["notes"]["label"], "Author"]


def test_the_card_names_the_order_a_customer_is_put_on_as_a_pedido_never_a_sort_order():
    """The card's «Pedidos enlazados» say «Pedido»; the model's verbose name «orden» is also the one of the lists'
    sort order, so the card said «Orden»."""
    assert SCREENS["orders"]["order"].startswith("Pedido ")
    link = get("customer.order.link")
    arguments = {"order_id": "x", "customer": "Ana"}
    assert labels(assistant.card(link, arguments, "es")) == ["Pedido abierto", "Cliente"]
    assert labels(assistant.card(link, arguments, "en")) == ["Open order", "Customer"]
