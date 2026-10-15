"""A real sale printed by name (PRINTING-F07, F08, F13, F18): a sale charged through sale's own operations,
read with ``sale.sale.get`` and sent to ``printing.job.create`` the way Sales will at checkout (WORKBOOK
«Contrato con la plataforma»: asked of the sale worker). No mocks: the document the device takes is the
one the app's renderer reads (``crates/peripherals/src/escpos.rs``), field by field.
"""

import json
from decimal import Decimal

import pytest
from live.context import system_context

from apps.printing import documents
from apps.printing.tests.conftest import A, printer, run

pytestmark = pytest.mark.django_db

#: Every field the app's renderer reads from a receipt (`render_receipt` and its helpers).
RENDERER_RECEIPT_FIELDS = {
    "business_name",
    "business_address",
    "vat_number",
    "phone",
    "receipt_id",
    "duplicate",
    "rectifying",
    "cashier",
    "customer_name",
    "customer_tax_id",
    "customer_address",
    "items",
    "subtotal",
    "tax_amount",
    "tax_label",
    "tax_breakdown",
    "discount",
    "total",
    "payment_method",
    "paid",
    "change",
    "qr_data",
    "qr_heading",
    "qr_legend",
    "receipt_header",
    "receipt_footer",
    "decimals",
    "locale",
}


def units(cents: int) -> float:
    """The renderer prints major-unit floats the producer already divided (escpos.rs `money_decimals`)."""
    return float(Decimal(cents) / 100)


def receipt_of(sale, *, duplicate: bool = False) -> dict:
    """The receipt document of a sale, as Sales will compose it (the old `document-mappers.ts`)."""
    return {
        "receipt_id": sale.number,
        "cashier": sale.created_by,
        "customer_name": sale.customer_name,
        "items": [
            {"name": line.name, "quantity": float(line.quantity), "total": units(line.line_total)}
            for line in sale.lines
        ],
        "subtotal": units(sale.subtotal),
        "tax_amount": units(sale.tax_total),
        "tax_breakdown": [
            {"rate": float(row.rate_pct), "base": units(row.base), "tax": units(row.tax)} for row in sale.breakdown
        ],
        "total": units(sale.total),
        "payment_method": sale.payment_method_name,
        "paid": units(sale.tendered_total),
        "change": units(sale.change_total),
        "duplicate": duplicate,
        "decimals": 2,
        "locale": "es",
    }


@pytest.fixture
def sale(db):
    """A real sale of two coffees (1.50 € each, 21 % VAT included) charged by card through sale (a card needs
    no open cash session)."""
    run(
        "inventory.product.create",
        {"name": "Coffee", "sku": "COF", "price": 150, "tax_category_key": "product.generic"},
        system_context(A),
    )
    charged = run(
        "sale.sale.complete",
        {
            "idempotency_key": "printing-sale-1",
            "lines": [{"product": "COF", "quantity": "2"}],
            "payments": [{"method": "card"}],
        },
    )
    return run("sale.sale.get", {"sale_id": str(charged.id)})


def test_a_charged_sale_is_printed_at_checkout_by_name(sale):
    till = printer("Till")
    run("printing.settings.update", {"open_drawer_on_sale": True})
    out = run(
        "printing.job.create",
        {
            "job_key": f"sale-{sale.id}-receipt",
            "document_type": "receipt",
            "document": receipt_of(sale),
            "automatic": True,
            "source_app": "sale",
            "source_ref": sale.number,
        },
    )
    assert (out.duplicate, out.skipped, out.job.reference, out.job.printer_name) == (False, None, sale.number, "Till")
    assert out.job.open_drawer is True

    taken = run("printing.job.claim", {"printers": [str(till.id)], "device": "Till 1"}).job
    assert (taken.kind, taken.document_type, taken.target, taken.open_drawer) == (
        "document",
        "receipt",
        "network:192.168.1.50:9100",
        True,
    )
    document = taken.document
    # What the device hands to erplora_print: a JSON object the renderer reads and does not refuse.
    assert documents.problems("receipt", document) is None
    assert set(document) <= RENDERER_RECEIPT_FIELDS
    assert json.loads(json.dumps(document)) == document
    assert document["receipt_id"] == sale.number
    assert document["items"] == [{"name": "Coffee", "quantity": 2.0, "total": 3.0}]
    assert document["total"] == 3.0
    assert round(document["subtotal"] + document["tax_amount"], 2) == document["total"]
    assert document["tax_breakdown"] and all(set(row) == {"rate", "base", "tax"} for row in document["tax_breakdown"])
    assert run("printing.job.complete", {"job_id": str(taken.id), "device": "Till 1", "attempt": 1}).job.status == "done"


def test_charging_again_with_the_same_key_prints_one_receipt(sale):
    printer("Till")
    request = {"job_key": f"sale-{sale.id}-receipt", "document_type": "receipt", "document": receipt_of(sale)}
    first = run("printing.job.create", request)
    again = run("printing.job.create", request)
    assert (again.duplicate, again.job.id) == (True, first.job.id)


def test_a_reprint_is_a_duplicate_with_its_own_key(sale):
    printer("Till")
    run("printing.job.create", {"job_key": f"sale-{sale.id}-receipt", "document_type": "receipt", "document": receipt_of(sale)})
    reprint = run(
        "printing.job.create",
        {"job_key": f"sale-{sale.id}-reprint-1", "document_type": "receipt", "document": receipt_of(sale, duplicate=True)},
    )
    assert reprint.duplicate is False
    assert run("printing.job.list", {"search": sale.number}).total == 2


def test_with_the_receipt_off_the_checkout_prints_nothing(sale):
    printer("Till")
    run("printing.settings.update", {"print_receipt_on_sale": False})
    out = run(
        "printing.job.create",
        {"job_key": f"sale-{sale.id}-receipt", "document_type": "receipt", "document": receipt_of(sale), "automatic": True},
    )
    assert (out.job, out.skipped) == (None, "print_on_sale_off")


def test_a_refused_print_never_spoils_the_checkout_that_asked_for_it(sale):
    # Sales asks inside the charge's transaction: a refusal rolls back only printing's savepoint, so the
    # charge goes on and commits (WORKBOOK PRINTING-F07: a sale never falls because of printing).
    from django.db import transaction
    from live.errors import OperationError

    printer("Till")
    with transaction.atomic():
        with pytest.raises(OperationError):
            run("printing.job.create", {"document_type": "prebill", "document": {"lines": []}})
        out = run("printing.job.create", {"job_key": f"sale-{sale.id}-receipt", "document_type": "receipt", "document": receipt_of(sale)})
    assert run("printing.job.list", {"search": sale.number}).total == 1
    assert out.job.status == "pending"
