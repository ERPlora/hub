"""The documents a printer can paint: the closed vocabulary of the app's renderer and the checks it would
refuse at the printer, made at the door instead (WORKBOOK «Contrato con la plataforma»)."""

import pytest

from apps.printing import documents

ITEM = {"name": "Haircut", "quantity": 1, "total": 18.0}


def test_the_vocabulary_is_the_eight_the_apps_renderer_knows():
    # crates/peripherals/src/escpos.rs (`DocumentType::parse`) of ERPlora/app: the same eight, no more.
    assert documents.DOCUMENT_TYPES == (
        "receipt",
        "kitchen_order",
        "invoice",
        "delivery_note",
        "barcode_label",
        "cash_session_report",
        "prebill",
        "generic",
    )


@pytest.mark.parametrize(
    ("document_type", "usage"),
    [
        ("receipt", "receipt"),
        ("invoice", "receipt"),
        ("prebill", "receipt"),
        ("cash_session_report", "receipt"),
        ("delivery_note", "receipt"),
        ("generic", "receipt"),
        ("kitchen_order", "kitchen"),
        ("barcode_label", "label"),
    ],
)
def test_each_document_has_the_function_that_prints_it(document_type, usage):
    assert documents.default_usage(document_type) == usage


def test_a_receipt_with_its_lines_passes():
    assert documents.problems("receipt", {"receipt_id": "T-1", "items": [ITEM], "total": 18.0}) is None


def test_a_document_is_an_object():
    assert documents.problems("receipt", ["not", "an", "object"]) == "A document is a JSON object of fields to print."


def test_a_bill_without_lines_is_refused():
    # The renderer refuses it rather than cutting a blank bill (hub#501).
    message = "A bill has lines to charge for: this one has none."
    assert documents.problems("prebill", {"items": []}) == message
    assert documents.problems("prebill", {"lines": [ITEM]}) == message
    assert documents.problems("prebill", {"items": [ITEM]}) is None


def test_a_full_invoice_needs_both_parties_its_number_and_its_tax_breakdown():
    invoice = {
        "vat_number": "B12345678",
        "receipt_id": "F-2026-1",
        "customer_name": "Acme SL",
        "customer_tax_id": "B87654321",
        "tax_breakdown": [{"rate": 21, "base": 100.0, "tax": 21.0}],
        "items": [ITEM],
    }
    assert documents.problems("invoice", invoice) is None
    for field in ("vat_number", "receipt_id", "customer_name", "customer_tax_id"):
        assert documents.problems("invoice", {**invoice, field: " "}) == f"A full invoice needs “{field}”."
    for breakdown in ([], [{"rate": 21, "base": 100.0}], "21%"):
        assert documents.problems("invoice", {**invoice, "tax_breakdown": breakdown}) == (
            "A full invoice needs “tax_breakdown”: one {rate, base, tax} per VAT rate."
        )


def test_a_document_has_a_size_limit():
    big = {"items": [ITEM], "note": "x" * documents.MAX_DOCUMENT_BYTES}
    assert documents.problems("receipt", big) == "The document is larger than 512 KB."


def test_a_label_a_report_and_a_generic_document_have_no_lines():
    assert documents.problems("barcode_label", {"product_name": "Shampoo", "barcode": "SHA-1", "price": 9.5}) is None
    assert documents.problems("cash_session_report", {"receipt_id": "S-261014-0001"}) is None
    assert documents.problems("generic", {"title": "Note"}) is None


@pytest.mark.parametrize(
    ("document", "reference"),
    [
        ({"receipt_id": "T-000123"}, "T-000123"),
        ({"order_number": 42}, "42"),
        ({"product_name": "Shampoo"}, "Shampoo"),
        ({"title": "Note"}, "Note"),
        ({}, ""),
    ],
)
def test_the_reference_a_person_reads_in_the_queue(document, reference):
    assert documents.reference(document) == reference


def test_a_value_that_is_not_json_is_said_not_raised():
    from decimal import Decimal

    message = "A document holds JSON values only: text, numbers, true or false, lists and objects."
    assert documents.problems("receipt", {"items": [ITEM], "total": Decimal("1.50")}) == message
    assert documents.problems("receipt", {"items": [ITEM], "total": float("nan")}) == message
