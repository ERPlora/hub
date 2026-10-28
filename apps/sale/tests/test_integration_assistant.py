"""The assistant's card for a write of sale (FIX-HUB-SALE-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258): in
Spanish, every datum it sends by the name the Sales screens give it, never by the title pydantic makes up from the
field («Allocations», «Line Id», «Combo Lines»). The card is base's (``base.assistant.card``); the names are sale's:
the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
import re
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


def test_no_label_of_a_write_of_sale_names_the_internal_unit_of_its_money():
    """Money reaches the card painted in the business's currency («12,50 zł», «1.250 ¥»), whose minor unit is not
    always the cent: no datum of a write of sale is named with the unit the server stores it in («Descuento
    (céntimos)» beside «12,50 €»), in Spanish or in English."""
    writes = sale_writes()
    assert len(writes) > 30  # positive control: the registry has sale's writes
    unit = re.compile(r"cents|céntimos|centavos", re.IGNORECASE)
    named_by_unit: dict[str, list[tuple[str, str]]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for language in ("es", "en"):
            for field in assistant.card(op, dict.fromkeys(props, "x"), language)["fields"]:
                if unit.search(field["label"]):
                    named_by_unit.setdefault(op.name, []).append((language, field["label"]))
    assert named_by_unit == {}


def test_the_card_names_a_checks_fixed_discount_apart_from_its_percentage_and_paints_it_as_money():
    """SALE-F14: the check's discount is a percentage or a fixed amount («importe fijo») in the business's currency;
    the card paints the amount as money and names it so, never «Descuento (céntimos)», and never as the
    percentage («Descuento (%)») beside it."""
    arguments = {"order_id": "x", "discount_percent": "10", "discount_amount": 1250}
    for name in ("sale.order.set_discount", "sale.order.set_discount_over_limit"):
        for language, percent, amount in (
            ("es", "Descuento (%)", "Descuento de importe fijo"),
            ("en", "Discount (%)", "Fixed-amount discount"),
        ):
            card = assistant.card(get(name), arguments, language)
            fields = {field["name"]: field for field in card["fields"]}
            assert (name, fields["discount_percent"]["label"]) == (name, percent)
            assert (name, fields["discount_amount"]["label"], fields["discount_amount"]["kind"], fields["discount_amount"]["value"]) == (
                name,
                amount,
                "money",
                1250,
            )
