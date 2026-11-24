"""Asking for a print (PRINTING-F05, F07–F13, F16): the job, its key, its printer, its paper's envelope and the test
page."""

import pytest
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied

from apps.printing.models import PrintJob
from apps.printing.tests.conftest import HUB_DB, RECEIPT, ctx_for, enqueue, printer, run
from apps.printing.tests.test_services import ITEM, STAMPED, events, job

pytestmark = HUB_DB


# ── Asking for a print (PRINTING-F07–F13, F16) ──────────────────────────────────────────────────


def test_a_receipt_waits_in_the_queue_of_receipts_with_its_number():
    out = enqueue()
    queued = job(out)
    assert (out.duplicate, out.skipped) == (False, None)
    assert (queued.kind, queued.document_type, queued.usage, queued.status, queued.format) == (
        "document",
        "receipt",
        "receipt",
        "pending",
        "receipt",
    )
    assert queued.document == {**RECEIPT, "locale": "en", "decimals": 2}
    assert (queued.reference, queued.printer_id, queued.copies, queued.created_by) == ("T-000123", None, 1, "tester")
    assert events("printing.job.queued") == [
        {"id": str(queued.id), "usage": "receipt", "printer_id": None, "kind": "document"}
    ]


def test_the_same_key_is_one_job():
    first = enqueue(job_key="sale-1-receipt")
    again = enqueue(job_key="sale-1-receipt", document={**RECEIPT, "total": 99})
    assert again.duplicate is True
    assert again.job.id == first.job.id
    assert PrintJob.objects.count() == 1
    assert job(again).document["total"] == 18.0
    assert len(events("printing.job.queued")) == 1


def test_a_job_without_key_gets_its_own():
    assert enqueue().job.job_key != enqueue().job.job_key


def test_each_document_goes_to_its_function():
    assert enqueue("kitchen_order", {"items": [ITEM]}).job.usage == "kitchen"
    assert enqueue("barcode_label", {"product_name": "Shampoo", "barcode": "SHA-1", "price": 9.5}).job.usage == "label"
    assert enqueue("kitchen_order", {"items": [ITEM]}, usage="bar").job.usage == "bar"


def test_the_printer_is_the_one_of_its_function_or_the_first_active_one():
    printer("B till", address="10.0.0.2")
    printer("A till", address="10.0.0.1", is_active=False)
    assert enqueue().job.printer_name == "B till"
    printer("C till", address="10.0.0.3")
    run("printing.settings.update", {"receipt_printer": "C till"})
    assert enqueue().job.printer_name == "C till"


def test_a_given_printer_is_used_even_of_another_function():
    printer("Kitchen", usage="kitchen")
    out = enqueue(printer="kitchen", source_app="assistant")
    assert (out.job.printer_name, out.job.usage, out.job.source_app) == ("Kitchen", "receipt", "assistant")


def test_a_given_printer_must_be_active_and_take_the_paper():
    printer("Till", is_active=False)
    printer("Office", kind="system", address="")
    with pytest.raises(Conflict) as refused:
        enqueue(printer="Till")
    assert refused.value.code == "printing.printer_inactive"
    with pytest.raises(Conflict) as refused:
        enqueue(printer="Office")
    assert refused.value.code == "printing.printer_incompatible"
    with pytest.raises(NotFound):
        enqueue(printer="Nowhere")
    assert not PrintJob.objects.exists()


def test_an_a4_page_goes_to_the_system_printer_and_a_receipt_to_the_thermal_one():
    printer("Till")
    printer("Office", kind="system", address="")
    page = enqueue("invoice", {}, format="a4", html="<p>Invoice F-1</p>", source_ref="F-1")
    assert (page.job.printer_name, page.job.format, page.job.reference) == ("Office", "a4", "F-1")
    assert enqueue().job.printer_name == "Till"


def test_a_document_the_printer_would_refuse_is_refused_at_the_door():
    with pytest.raises(InvalidPayload) as refused:
        enqueue("prebill", {"lines": [ITEM]})
    assert refused.value.fields == {"document": "A bill has lines to charge for: this one has none."}
    with pytest.raises(InvalidPayload):
        enqueue("invoice", {"items": [ITEM]})
    assert not PrintJob.objects.exists()


def test_a_receipt_takes_the_settings_copies_unless_told():
    run("printing.settings.update", {"receipt_copies": 3})
    assert enqueue().job.copies == 3
    assert enqueue(copies=1).job.copies == 1
    assert enqueue("kitchen_order", {"items": [ITEM]}).job.copies == 1


def test_the_print_at_checkout_follows_the_settings():
    out = enqueue(automatic=True)
    assert (out.job.open_drawer, out.skipped) == (False, None)
    run("printing.settings.update", {"open_drawer_on_sale": True})
    assert enqueue(automatic=True).job.open_drawer is True
    assert enqueue(automatic=False).job.open_drawer is False


def test_with_the_receipt_off_at_checkout_only_the_drawer_opens():
    run("printing.settings.update", {"print_receipt_on_sale": False})
    out = enqueue(automatic=True)
    assert (out.job, out.duplicate, out.skipped) == (None, False, "print_on_sale_off")
    assert not PrintJob.objects.exists()
    run("printing.settings.update", {"open_drawer_on_sale": True})
    out = enqueue(automatic=True, job_key="sale-9-receipt")
    assert out.skipped == "print_on_sale_off"
    assert (out.job.kind, out.job.open_drawer, out.job.document_type, out.job.job_key) == (
        "drawer",
        True,
        "",
        "sale-9-receipt",
    )


def test_a_checkout_without_cash_keeps_the_drawer_shut():
    """PRINTING-F13: the drawer opens when cash comes in (Square, Toast, Odoo, Shopify, Lightspeed); the till
    says when it did not, and the settings still decide when it did."""
    run("printing.settings.update", {"open_drawer_on_sale": True})
    assert enqueue(automatic=True, open_drawer=False).job.open_drawer is False
    assert enqueue(automatic=True, open_drawer=True).job.open_drawer is True
    run("printing.settings.update", {"print_receipt_on_sale": False})
    out = enqueue(automatic=True, open_drawer=False)
    assert (out.job, out.skipped) == (None, "print_on_sale_off")
    run("printing.settings.update", {"open_drawer_on_sale": False})
    assert enqueue(automatic=True, open_drawer=True).job is None


def test_whoever_prints_asks_for_a_print_and_nobody_else():
    assert enqueue().job is not None
    assert run("printing.job.create", {"document_type": "receipt", "document": RECEIPT}, ctx_for("hub_employee")).job
    with pytest.raises(PermissionDenied):
        run("printing.job.create", {"document_type": "receipt", "document": RECEIPT}, ctx_for("nobody"))


# ── PRINTING-F05 Test page ──────────────────────────────────────────────────────────────────────


def test_a_test_page_is_a_job_of_its_printer():
    kitchen = printer("Kitchen", usage="kitchen")
    out = run("printing.printer.test", {"printer": "Kitchen"}, ctx_for(language="es"))
    queued = PrintJob.objects.get(pk=out.id)
    assert (queued.kind, queued.printer_id, queued.usage, queued.format, queued.document) == (
        "test_page",
        kitchen.id,
        "kitchen",
        "receipt",
        {"locale": "es"},
    )
    assert out.reference == "Kitchen"


def test_the_system_printer_tests_with_an_a4_page():
    printer("Office", kind="system", address="")
    out = run("printing.printer.test", {"printer": "Office"})
    queued = PrintJob.objects.get(pk=out.id)
    assert queued.format == "a4"
    assert "Office" in queued.html and "<script" not in queued.html


def test_the_a4_test_page_is_signed_by_the_business_in_the_callers_language():
    """Never «ERPlora Bridge», a product that is gone; the business's name once invoicing knows it (ERPlora until then),
    in the language of whoever tests."""
    printer("Office", kind="system", address="")
    unnamed = PrintJob.objects.get(pk=run("printing.printer.test", {"printer": "Office"}).id).html
    assert "<h1>ERPlora</h1>" in unnamed and "Bridge" not in unnamed
    run("invoice.issuer.update", {"legal_name": "Salón Ana SL", "tax_id": "B12345674", "address": "Calle Mayor 1"})
    out = run("printing.printer.test", {"printer": "Office"}, ctx_for(language="es"))
    named = PrintJob.objects.get(pk=out.id).html
    assert "<h1>Salón Ana SL</h1>" in named and '<html lang="es">' in named and "Impresora OK" in named


def test_an_inactive_printer_is_not_tested():
    printer("Till", is_active=False)
    with pytest.raises(Conflict) as refused:
        run("printing.printer.test", {"printer": "Till"})
    assert refused.value.code == "printing.printer_inactive"
    assert refused.value.message == "That printer is inactive: activate it to test it."


# ── The paper's envelope: language and money scale ────────────────────────────────────


def test_a_document_without_language_or_scale_takes_the_callers_and_the_currencys():
    assert job(enqueue()).document == STAMPED
    spanish = run("printing.job.create", {"document_type": "receipt", "document": RECEIPT}, ctx_for(language="es"))
    assert job(spanish).document["locale"] == "es"
    yen = enqueue(document={**RECEIPT, "total": 1800}, currency="JPY")
    assert job(yen).document["decimals"] == 0
    own = enqueue(document={**RECEIPT, "locale": "ca", "decimals": 3})
    assert (job(own).document["locale"], job(own).document["decimals"]) == ("ca", 3)


def test_a_generic_document_prints_every_key_so_it_gets_no_scale():
    # The renderer prints every key of a generic document but title, receipt_id and locale.
    assert job(enqueue("generic", {"title": "Note", "text": "hello"})).document == {"title": "Note", "text": "hello", "locale": "en"}


def test_a_value_that_is_not_json_is_refused_at_the_door_never_a_crash():
    from decimal import Decimal

    import pydantic

    with pytest.raises(pydantic.ValidationError):
        enqueue(document={**RECEIPT, "total": Decimal("18.00")})
    assert not PrintJob.objects.exists()


# ── PRINTING-F05 The test page names the business ──────────────────────────────────────────────


def test_the_test_page_carries_the_business_name_when_invoicing_knows_it():
    printer("Till")
    assert PrintJob.objects.get(pk=run("printing.printer.test", {"printer": "Till"}).id).document == {"locale": "en"}
    run("invoice.issuer.update", {"legal_name": "Salón Ana SL", "tax_id": "B12345674", "address": "Calle Mayor 1"})
    out = run("printing.printer.test", {"printer": "Till"})
    assert PrintJob.objects.get(pk=out.id).document == {"locale": "en", "business_name": "Salón Ana SL"}


def test_an_a4_page_prints_once_whatever_the_receipt_copies():
    printer("Office", kind="system", address="")
    run("printing.settings.update", {"receipt_copies": 3})
    page = enqueue("receipt", {}, format="a4", html="<p>T-1</p>")
    assert page.job.copies == 1


def test_a_chosen_printer_that_is_inactive_is_passed_over_for_the_first_active_one_of_its_function():
    till = printer("Till")
    spare = printer("Spare")
    run("printing.settings.update", {"receipt_printer": "Till"})
    run("printing.printer.update", {"printer_id": str(till.id), "is_active": False})
    queued = enqueue()
    assert (queued.job.printer_id, queued.job.printer_name) == (spare.id, "Spare")
