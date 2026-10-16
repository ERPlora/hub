"""What a printer can paint: the closed vocabulary of the app's ESC/POS renderer and the checks it makes at
the printer, made here at the door so a document that would come out wrong is refused when it is asked for
(WORKBOOK «Contrato con la plataforma»).

The bytes are the app's (``crates/peripherals/src/escpos.rs`` of ERPlora/app, ``erplora_print``): the
document travels structured, never rendered on the server (PLAN-HUB §5; hub#501). This file holds no ORM.
"""

import json
from typing import Any

from django.utils.translation import gettext_lazy as _

#: The renderer's vocabulary (``DocumentType::parse``): anything else would be refused at the printer.
DOCUMENT_TYPES = (
    "receipt",
    "kitchen_order",
    "invoice",
    "delivery_note",
    "barcode_label",
    "cash_session_report",
    "prebill",
    "generic",
)

#: The function that prints a document when the caller does not say (the old hub's routes).
_USAGE = {"kitchen_order": "kitchen", "barcode_label": "label"}

#: A print job is a ticket or an invoice, not a file: bounded like the old hub's queue.
MAX_DOCUMENT_BYTES = 512 * 1024

NOT_AN_OBJECT = _("A document is a JSON object of fields to print.")
NOT_JSON = _("A document holds JSON values only: text, numbers, true or false, lists and objects.")
TOO_LARGE = _("The document is larger than 512 KB.")
BILL_WITHOUT_LINES = _("A bill has lines to charge for: this one has none.")
INVOICE_NEEDS = _("A full invoice needs “%(field)s”.")
INVOICE_NEEDS_BREAKDOWN = _("A full invoice needs “tax_breakdown”: one {rate, base, tax} per VAT rate.")

#: What a full invoice cannot do without (``check_full_invoice`` of the renderer).
_INVOICE_FIELDS = ("vat_number", "receipt_id", "customer_name", "customer_tax_id")


def default_usage(document_type: str) -> str:
    """The function a document goes to: the kitchen order to the kitchen, the label to labels, the rest
    to the receipt printer."""
    return _USAGE.get(document_type, "receipt")


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _breakdown_ok(rows: Any) -> bool:
    return (
        isinstance(rows, list)
        and bool(rows)
        and all(isinstance(row, dict) and all(_is_number(row.get(k)) for k in ("rate", "base", "tax")) for row in rows)
    )


def problems(document_type: str, document: Any) -> str | None:
    """Why the printer would refuse ``document`` (a sentence for a person), or ``None``."""
    if not isinstance(document, dict):
        return str(NOT_AN_OBJECT)
    try:
        size = len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode())
    except (TypeError, ValueError):
        return str(NOT_JSON)
    if size > MAX_DOCUMENT_BYTES:
        return str(TOO_LARGE)
    if document_type == "prebill":
        items = document.get("items")
        if not (isinstance(items, list) and items):
            return str(BILL_WITHOUT_LINES)
    if document_type == "invoice":
        for field in _INVOICE_FIELDS:
            value = document.get(field)
            if not (isinstance(value, str) and value.strip()):
                return str(INVOICE_NEEDS) % {"field": field}
        if not _breakdown_ok(document.get("tax_breakdown")):
            return str(INVOICE_NEEDS_BREAKDOWN)
    return None


def reference(document: dict) -> str:
    """What names a document in the queue: its number, its order, its product or its title."""
    for key in ("receipt_id", "order_number", "product_name", "title"):
        value = document.get(key)
        if value not in (None, ""):
            return str(value)
    return ""
