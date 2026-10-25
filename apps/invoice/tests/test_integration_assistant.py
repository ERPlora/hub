"""The assistant's card for a write of invoice (FIX-HUB-INVOICE-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258):
in Spanish, every datum it sends by the name the Facturas screens give it, never by the title pydantic makes up from
the field («Duplicate», «Lines», «Next Number»). The card is base's (``base.assistant.card``); the names are invoice's:
the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

LOCALE = Path(apps.get_app_config("invoice").path) / "frontend/locale"
SCREENS = json.loads((LOCALE / "es.json").read_text())["invoice"]
SCREENS_EN = json.loads((LOCALE / "en.json").read_text())["invoice"]


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def invoice_writes() -> list:
    return [op for op in registry.values() if op.app_label == "invoice" and op.kind == "command" and assistant.is_tool(op)]


def test_no_datum_of_a_write_of_invoice_reaches_a_spanish_card_by_its_technical_name():
    """Every write of invoice the assistant may ask for, with all its data: each datum by a name of its own in Spanish,
    never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = invoice_writes()
    # Positive control: the registry has invoice's writes, those that send the data this fix names among them.
    assert {
        "invoice.invoice.create",
        "invoice.invoice.create_from_sale",
        "invoice.invoice.print",
        "invoice.invoice.rectify",
        "invoice.invoice.rectify_from_refund",
        "invoice.invoice.rectify_from_void",
        "invoice.series.create",
        "invoice.series.update",
    } <= {op.name for op in writes}
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def test_the_card_names_a_reprint_as_the_paper_stamps_it():
    print_ = get("invoice.invoice.print")
    assert labels(assistant.card(print_, {"number": "F-1", "duplicate": True}, "es")) == ["Número", SCREENS["paper"]["copy"]]
    assert labels(assistant.card(print_, {"number": "F-1", "duplicate": True}, "en")) == ["Number", SCREENS_EN["paper"]["copy"]]


def test_the_card_names_the_kind_of_a_rectification_as_its_form_does():
    rectify = get("invoice.invoice.rectify")
    arguments = {"invoice_id": "x", "rectification_type": "R4"}
    assert labels(assistant.card(rectify, arguments, "es")) == ["Factura", SCREENS["rectify"]["type"]]
    assert labels(assistant.card(rectify, arguments, "en")) == ["Invoice", SCREENS_EN["rectify"]["type"]]


def test_the_card_names_the_lines_of_a_manual_invoice():
    lines = [{"description": "Corte", "quantity": "1", "unit_price": 1500, "tax_rate": "21"}]
    create = get("invoice.invoice.create")
    assert labels(assistant.card(create, {"lines": lines}, "es")) == ["Líneas"]
    assert labels(assistant.card(create, {"lines": lines}, "en")) == ["Lines"]


def test_the_card_names_a_series_next_number_as_its_form_does():
    for name in ("invoice.series.create", "invoice.series.update"):
        assert labels(assistant.card(get(name), {"next_number": 120}, "es")) == [SCREENS["series"]["form"]["nextNumber"]]
        assert labels(assistant.card(get(name), {"next_number": 120}, "en")) == [SCREENS_EN["series"]["form"]["nextNumber"]]


def test_the_card_names_the_sale_and_the_refund_as_the_record_does():
    for name in ("invoice.invoice.create_from_sale", "invoice.invoice.rectify_from_void"):
        assert labels(assistant.card(get(name), {"sale_id": "x"}, "es")) == [SCREENS["detail"]["fields"]["sale"]]
        assert labels(assistant.card(get(name), {"sale_id": "x"}, "en")) == [SCREENS_EN["detail"]["fields"]["sale"]]
    refund = get("invoice.invoice.rectify_from_refund")
    assert labels(assistant.card(refund, {"refund_id": "x"}, "es")) == [SCREENS["sources"]["refund"]]
    assert labels(assistant.card(refund, {"refund_id": "x"}, "en")) == [SCREENS_EN["sources"]["refund"]]
