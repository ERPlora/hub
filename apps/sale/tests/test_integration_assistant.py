"""The assistant's card for a write of sale (FIX-HUB-SALE-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258): in
Spanish, every datum it sends by the name the Sales screens give it, never by the title pydantic makes up from the
field («Allocations», «Line Id», «Combo Lines»). The card is base's (``base.assistant.card``); the names are sale's:
the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

FRONTEND = Path(apps.get_app_config("sale").path) / "frontend/locale"
SCREENS = json.loads((FRONTEND / "es.json").read_text())["sale"]
SCREENS_EN = json.loads((FRONTEND / "en.json").read_text())["sale"]


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def sale_writes() -> list:
    return [op for op in registry.values() if op.app_label == "sale" and op.kind == "command" and assistant.is_tool(op)]


def test_no_datum_of_a_write_of_sale_reaches_a_spanish_card_by_its_technical_name():
    """Every write of sale the assistant may ask for, with all its data: each datum by a name of its own in Spanish,
    never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = sale_writes()
    assert len(writes) > 30  # positive control: the registry has sale's writes
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def test_the_card_names_a_refunds_money_as_the_refund_screen_does():
    refund = get("sale.sale.refund")
    arguments = {"allocations": [{"payment_id": "x", "amount": 500}]}
    assert labels(assistant.card(refund, arguments, "es")) == [SCREENS["refund"]["amount"]]
    assert labels(assistant.card(refund, arguments, "en")) == [SCREENS_EN["refund"]["amount"]]


def test_the_card_names_the_lines_a_check_starts_with_by_their_kind():
    arguments = {"open_lines": [], "service_lines": [], "combo_lines": []}
    open_check = get("sale.order.open")
    assert labels(assistant.card(open_check, arguments, "es")) == [
        "Líneas de precio libre",
        SCREENS["pos"]["services"],
        "Menús",
    ]
    assert labels(assistant.card(open_check, arguments, "en")) == ["Open-price lines", SCREENS_EN["pos"]["services"], "Menus"]


def test_the_card_names_a_line_of_the_check_and_the_voucher_that_pays_it():
    voucher = assistant.card(get("sale.order.apply_voucher"), {"line_id": "x", "grant_id": "y"}, "es")
    assert labels(voucher) == ["Línea", "Bono"]
    voucher = assistant.card(get("sale.order.apply_voucher"), {"line_id": "x", "grant_id": "y"}, "en")
    assert labels(voucher) == ["Line", "Voucher"]


def test_the_card_names_what_goes_to_the_kitchen_as_the_kitchen_reads_it():
    """Dine in, takeaway or delivery; the rush the till marks; who serves the check («Atiende»)."""
    arguments = {"channel": "takeaway", "priority": "rush", "waiter": "Ana"}
    fire = get("sale.order.fire")
    assert labels(assistant.card(fire, arguments, "es")) == ["Tipo de pedido", "Prioridad", "Atendido por"]
    assert labels(assistant.card(fire, arguments, "en")) == ["Order type", "Priority", "Served by"]


def test_the_card_names_the_two_checks_of_a_merge_and_the_lines_of_a_split():
    merge = assistant.card(get("sale.order.merge"), {"from_order_id": "x", "to_order_id": "y"}, "es")
    assert labels(merge) == ["Cuenta de origen", "Cuenta de destino"]
    assert labels(assistant.card(get("sale.order.split"), {"line_ids": []}, "es")) == ["Líneas a mover"]
    assert labels(assistant.card(get("sale.sale.complete"), {"line_ids": []}, "es")) == ["Líneas a cobrar"]


def test_the_card_names_a_quick_note_and_a_reprint():
    note = assistant.card(get("sale.quick_note.delete"), {"quick_note": "Sin sal"}, "es")
    assert labels(note) == [SCREENS["quickNotes"]["entity"]["one"].capitalize()]
    reprint = assistant.card(get("sale.sale.print"), {"duplicate": True}, "es")
    assert labels(reprint) == ["Imprimir como duplicado"]
