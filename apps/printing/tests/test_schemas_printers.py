"""Schemas of the printers: how one is named, changed and added, and what an input refuses."""

import uuid

from apps.printing.schemas.printers import PrinterIn, PrinterRefIn, PrinterUpdateIn

from .test_schemas_fields import refused


def test_a_printer_is_named_by_its_id_or_its_name():
    refused(PrinterRefIn, {})
    assert PrinterRefIn.model_validate({"printer": " Kitchen "}).printer == "Kitchen"
    some = uuid.uuid4()
    assert PrinterRefIn.model_validate({"printer_id": str(some)}).printer_id == some


def test_a_printer_change_says_which_one_and_what_changes():
    refused(PrinterUpdateIn, {"name": "Bar"})
    refused(PrinterUpdateIn, {"printer": "Till"})
    assert PrinterUpdateIn.model_validate({"printer": "Till", "is_active": False}).is_active is False


def test_a_new_printer():
    refused(PrinterIn, {"name": "", "kind": "network", "usage": "receipt"})
    refused(PrinterIn, {"name": "Till", "kind": "wifi", "usage": "receipt"})
    refused(PrinterIn, {"name": "Till", "kind": "network", "usage": "receipt", "paper_width": 76})
    printer = PrinterIn.model_validate({"name": " Till ", "kind": "network", "address": " 10.0.0.9 ", "usage": "receipt"})
    assert (printer.name, printer.address, printer.port, printer.paper_width, printer.is_active) == ("Till", "10.0.0.9", None, 80, True)
