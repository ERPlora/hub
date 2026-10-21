"""Write operations of the printing app: printers, settings, the queue and the device that drains it.

Cases ported from the old module (printing.jobs.create's idempotent key and closed vocabulary, the
settings' factory values) and from the old hub's queue (crates/runtime/src/print_queue.rs: five
hand-outs, a 90 s lease, done/failed by the device that took it, retry and discard stamped, nothing
deleted)."""

import dataclasses
import datetime as dt
import json

import pytest
from django.test import RequestFactory
from django.utils import timezone
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.context import system_context
from live.models import OutboxEvent

from apps.printing.models import PrintDevice, Printer, PrintJob, Settings
from apps.printing import services
from apps.printing.tests.conftest import A, B, RECEIPT, ctx_for, enqueue, printer, run

pytestmark = pytest.mark.django_db

ITEM = {"name": "Haircut", "quantity": 1, "total": 18.0}


def events(name: str) -> list[dict]:
    return [event.payload for event in OutboxEvent.objects.filter(name=name).order_by("created_at", "id")]


def job(out) -> PrintJob:
    return PrintJob.objects.get(pk=out.job.id)


def claim(*printers: Printer, device: str = "Till 1"):
    return run("printing.job.claim", {"printers": [str(p.id) for p in printers], "device": device}).job


def done(job_id, device: str = "Till 1", attempt: int = 1):
    return run("printing.job.complete", {"job_id": str(job_id), "device": device, "attempt": attempt})


def failure(job_id, error: str = "printer unreachable", device: str = "Till 1", attempt: int = 1):
    return run("printing.job.fail", {"job_id": str(job_id), "error": error, "device": device, "attempt": attempt})


def expire(job_id) -> None:
    PrintJob.objects.filter(pk=job_id).update(leased_until=timezone.now() - dt.timedelta(seconds=1))


# ── PRINTING-F03 Add a printer by its address ───────────────────────────────────────────────────


def test_a_network_printer_takes_port_9100_80_mm_and_is_active():
    out = printer("Till")
    assert (out.kind, out.address, out.port, out.paper_width, out.usage, out.is_active) == (
        "network",
        "192.168.1.50",
        9100,
        80,
        "receipt",
        True,
    )
    assert out.target == "network:192.168.1.50:9100"
    assert out.state == "ready"
    assert Printer.objects.get(pk=out.id).created_by == "tester"
    assert events("printing.printer.created") == [{"id": str(out.id)}]


@pytest.mark.parametrize(
    ("values", "address", "port", "target"),
    [
        ({"kind": "bluetooth", "address": "aa-bb-cc-dd-ee-ff"}, "AA:BB:CC:DD:EE:FF", None, "bluetooth:AA:BB:CC:DD:EE:FF"),
        ({"kind": "usb", "address": "EPSON_TM-T20.II"}, "EPSON_TM-T20.II", None, "usb:EPSON_TM-T20.II"),
        ({"kind": "system", "address": ""}, "", None, "system"),
        ({"kind": "network", "address": "printer.local", "port": 9101}, "printer.local", 9101, "network:printer.local:9101"),
        ({"kind": "network", "address": "fe80::1"}, "fe80::1", 9100, "network:fe80::1:9100"),
    ],
)
def test_each_connection_keeps_the_address_the_app_understands(values, address, port, target):
    out = printer("P", **values)
    assert (out.address, out.port, out.target) == (address, port, target)


@pytest.mark.parametrize(
    ("values", "field", "message"),
    [
        ({"address": ""}, "address", "Type a valid IP or network name (for example 192.168.1.100)."),
        ({"address": "192.168.1.50/24"}, "address", "Type a valid IP or network name (for example 192.168.1.100)."),
        ({"port": 0}, "port", "The port goes from 1 to 65535."),
        ({"port": 70000}, "port", "The port goes from 1 to 65535."),
        ({"kind": "bluetooth", "address": "AA:BB:CC"}, "address", "Type the MAC as AA:BB:CC:DD:EE:FF."),
        ({"kind": "bluetooth", "address": "AA:BB:CC:DD:EE:FF", "port": 1}, "port", "Only a network printer has a port."),
        (
            {"kind": "usb", "address": "my printer"},
            "address",
            "Type the print queue's name as the system gives it (no spaces, slashes or #).",
        ),
        (
            {"kind": "system", "address": "10.0.0.1"},
            "address",
            "The system printer is the computer's own: it has no address.",
        ),
        (
            {"kind": "system", "address": "", "usage": "kitchen"},
            "usage",
            "The system printer prints A4 pages: give it the Receipt role.",
        ),
    ],
)
def test_an_address_that_no_printer_can_have_is_refused_at_its_field(values, field, message):
    with pytest.raises(InvalidPayload) as refused:
        printer("P", **values)
    assert refused.value.fields == {field: message}
    assert not Printer.objects.exists()


def test_two_printers_never_share_a_name_whatever_its_case():
    printer("Kitchen")
    with pytest.raises(Conflict) as refused:
        printer("kitchen", address="192.168.1.51")
    assert refused.value.code == "printing.printer_exists"
    assert refused.value.fields == {"name": "There is already a printer with that name."}


def test_only_who_manages_the_settings_adds_a_printer():
    with pytest.raises(PermissionDenied):
        run("printing.printer.create", {"name": "Till", "kind": "system", "usage": "receipt"}, ctx_for("hub_employee"))
    assert run(
        "printing.printer.create", {"name": "Till", "kind": "system", "usage": "receipt"}, ctx_for("hub_manager")
    ).name == "Till"


# ── PRINTING-F04 What each printer prints ───────────────────────────────────────────────────────


def test_a_printer_is_changed_by_its_name():
    till = printer("Till")
    out = run("printing.printer.update", {"printer": "till", "name": "Front till", "paper_width": 58})
    assert (out.id, out.name, out.paper_width) == (till.id, "Front till", 58)
    assert events("printing.printer.updated") == [{"id": str(till.id), "fields": ["name", "paper_width"]}]


def test_nothing_changed_is_no_event():
    printer("Till")
    run("printing.printer.update", {"printer": "Till", "name": "Till"})
    assert events("printing.printer.updated") == []


def test_a_printer_is_deactivated_and_activated_never_deleted():
    till = printer("Till")
    assert run("printing.printer.update", {"printer_id": str(till.id), "is_active": False}).state == "inactive"
    assert run("printing.printer.update", {"printer_id": str(till.id), "is_active": True}).state == "ready"


def test_changing_the_connection_asks_for_an_address_it_can_have():
    printer("Till", kind="bluetooth", address="AA:BB:CC:DD:EE:FF")
    with pytest.raises(InvalidPayload) as refused:
        run("printing.printer.update", {"printer": "Till", "kind": "network"})
    assert set(refused.value.fields) == {"address"}
    out = run("printing.printer.update", {"printer": "Till", "kind": "network", "address": "10.0.0.7"})
    assert out.target == "network:10.0.0.7:9100"
    out = run("printing.printer.update", {"printer": "Till", "kind": "system", "address": ""})
    assert (out.address, out.port, out.target) == ("", None, "system")


def test_an_unknown_printer_is_not_found():
    with pytest.raises(NotFound) as refused:
        run("printing.printer.update", {"printer": "Nowhere", "is_active": False})
    assert refused.value.message == "There is no printer with that name."


def test_a_printer_that_changes_function_stops_being_the_one_of_its_old_function():
    kitchen = printer("Kitchen", usage="kitchen")
    run("printing.settings.update", {"kitchen_printer": "Kitchen"})
    run("printing.printer.update", {"printer": "Kitchen", "usage": "bar"})
    assert Settings.objects.get().kitchen_printer_id is None
    assert Printer.objects.get(pk=kitchen.id).usage == "bar"


# ── PRINTING-F06 Settings ───────────────────────────────────────────────────────────────────────


def test_the_settings_save_only_what_is_sent():
    out = run("printing.settings.update", {"open_drawer_on_sale": True, "receipt_copies": 2})
    assert (out.print_receipt_on_sale, out.open_drawer_on_sale, out.receipt_copies) == (True, True, 2)
    assert out.updated_at is not None
    assert events("printing.settings.updated") == [{"fields": ["open_drawer_on_sale", "receipt_copies"]}]
    assert Settings.objects.get().updated_by == "tester"


def test_the_printer_of_a_function_is_one_of_its_active_printers():
    kitchen = printer("Kitchen", usage="kitchen")
    printer("Till")
    printer("Old kitchen", usage="kitchen", address="10.0.0.2", is_active=False)
    out = run("printing.settings.update", {"kitchen_printer": "kitchen"})
    assert out.kitchen_printer_id == kitchen.id
    with pytest.raises(InvalidPayload) as refused:
        run("printing.settings.update", {"kitchen_printer": "Till"})
    assert refused.value.fields == {"kitchen_printer": "That printer does not have this role."}
    with pytest.raises(InvalidPayload) as refused:
        run("printing.settings.update", {"kitchen_printer": "Old kitchen"})
    assert refused.value.fields == {"kitchen_printer": "That printer is inactive."}
    with pytest.raises(InvalidPayload) as refused:
        run("printing.settings.update", {"label_printer": "Nowhere"})
    assert refused.value.fields == {"label_printer": "There is no printer with that name."}
    assert run("printing.settings.update", {"kitchen_printer": None}).kitchen_printer_id is None


def test_the_employee_reads_the_settings_and_does_not_change_them():
    with pytest.raises(PermissionDenied):
        run("printing.settings.update", {"receipt_copies": 2}, ctx_for("hub_employee"))


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
    """hub#1735, hub#1803: never «ERPlora Bridge», a product that is gone; the business's name once invoicing
    knows it (ERPlora until then), in the language of whoever tests."""
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


# ── PRINTING-F18 The device takes and confirms ──────────────────────────────────────────────────


STAMPED = {**RECEIPT, "locale": "en", "decimals": 2}


def test_a_device_takes_the_oldest_job_of_its_printers():
    till = printer("Till")
    first = enqueue(source_ref="T-1").job
    second = enqueue(source_ref="T-2").job
    taken = claim(till)
    assert taken.id == first.id
    assert (taken.kind, taken.printer_id, taken.target, taken.paper_width, taken.attempts) == (
        "document",
        till.id,
        "network:192.168.1.50:9100",
        80,
        1,
    )
    assert (taken.document_type, taken.document, taken.copies, taken.copy_document, taken.open_drawer, taken.html) == (
        "receipt",
        STAMPED,
        1,
        None,
        False,
        "",
    )
    sent = PrintJob.objects.get(pk=first.id)
    # The job names the device by its registration, never by the id it sent (that id is its credential,
    # hub#2551): whoever sets up printers pairs the device by printing from it, as «Device 1».
    assert (sent.status, sent.device, sent.print_device.name, sent.attempts) == ("sent", "Device 1", "Device 1", 1)
    assert sent.leased_until > timezone.now() + dt.timedelta(seconds=80)
    # The device is told how long it has to answer (WORKBOOK «Contrato con la plataforma», claim).
    assert taken.leased_until == sent.leased_until
    assert claim(till).id == second.id
    assert claim(till) is None
    assert events("printing.job.claimed")[0] == {"id": str(first.id), "printer_id": str(till.id)}


def test_the_copies_of_a_receipt_are_duplicates_never_a_second_original():
    # RD 1619/2012 art. 14.4: only the first paper is the original; the renderer prints «DUPLICADO» with
    # `duplicate: true` (escpos.rs). The device prints `document` once and `copy_document` copies − 1 times.
    till = printer("Till")
    run("printing.settings.update", {"receipt_copies": 3})
    enqueue()
    taken = claim(till)
    assert (taken.copies, taken.document) == (3, STAMPED)
    assert taken.copy_document == {**STAMPED, "duplicate": True}
    enqueue("invoice", {**RECEIPT, "vat_number": "B12345674", "customer_name": "Acme", "customer_tax_id": "B87654321",
                        "tax_breakdown": [{"rate": 21, "base": 14.88, "tax": 3.12}]}, copies=2)
    assert claim(till).copy_document["duplicate"] is True
    printer("Kitchen", usage="kitchen", address="10.0.0.2")
    enqueue("kitchen_order", {"items": [ITEM]}, copies=2)
    kitchen = claim(Printer.objects.get(name="Kitchen"))
    assert kitchen.copy_document == kitchen.document


def test_a_job_without_printer_goes_to_the_first_device_with_a_printer_of_its_function():
    waiting = enqueue().job
    assert waiting.printer_id is None
    till = printer("Till")
    kitchen = printer("Kitchen", usage="kitchen", address="10.0.0.2")
    assert claim(kitchen) is None
    taken = claim(till)
    assert taken.id == waiting.id
    assert PrintJob.objects.get(pk=waiting.id).printer_id == till.id


def test_a_device_never_takes_what_is_not_its_own():
    till = printer("Till")
    office = printer("Office", kind="system", address="")
    printer("Other", address="10.0.0.9")
    enqueue(printer="Other")
    enqueue("invoice", {}, format="a4", html="<p>F</p>", printer="Office")
    assert claim(till) is None
    assert claim(office).format == "a4"


def test_two_devices_never_take_the_same_job():
    till = printer("Till")
    enqueue()
    assert claim(till, device="A") is not None
    assert claim(till, device="B") is None


def test_a_job_with_no_answer_goes_back_after_its_lease_and_fails_after_five_hand_outs():
    till = printer("Till")
    queued = enqueue().job
    for attempt in range(1, 6):
        taken = claim(till)
        assert (taken.id, taken.attempts) == (queued.id, attempt)
        expire(queued.id)
    assert claim(till) is None
    failed = PrintJob.objects.get(pk=queued.id)
    assert (failed.status, failed.attempts, failed.last_error) == ("failed", 5, "No answer from the device.")


def test_a_job_back_from_an_expired_lease_wakes_the_devices():
    till = printer("Till")
    queued = enqueue().job
    claim(till)
    expire(queued.id)
    before = len(events("printing.job.queued"))
    claim(printer("Kitchen", usage="kitchen", address="10.0.0.2"))  # reclaims the expired lease
    assert len(events("printing.job.queued")) == before + 1
    assert events("printing.job.queued")[-1]["id"] == str(queued.id)


def test_the_device_confirms_the_paper_once_and_the_document_is_let_go():
    till = printer("Till")
    queued = enqueue().job
    claim(till)
    ack = done(queued.id)
    assert (ack.confirmed, ack.job.status) == (True, "done")
    assert ack.job.printed_at is not None
    assert Printer.objects.get(pk=till.id).last_printed_at is not None
    again = done(queued.id)
    assert (again.confirmed, again.job.status) == (True, "done")
    assert len(events("printing.job.printed")) == 1
    # RGPD: a printed job keeps its number and its trail, not the customer's paper.
    printed = PrintJob.objects.get(pk=queued.id)
    assert (printed.document, printed.html, printed.reference) == ({}, "", "T-000123")


def test_a_late_confirmation_of_the_same_device_is_taken_never_printed_twice():
    # A slow printer with copies passes the 90 s; another claim puts the job back in the queue; the paper
    # did come out: the device's «done» is taken from the queue too (the old hub's rule).
    till = printer("Till")
    queued = enqueue().job
    claim(till)
    expire(queued.id)
    claim(printer("Kitchen", usage="kitchen", address="10.0.0.2"))  # reclaims the expired lease
    assert PrintJob.objects.get(pk=queued.id).status == "pending"
    ack = done(queued.id)
    assert (ack.confirmed, ack.job.status) == (True, "done")
    assert claim(till) is None


def test_a_confirmation_from_another_device_or_an_attempt_never_handed_out_is_refused():
    till = printer("Till")
    queued = enqueue().job
    claim(till, device="A")
    for device, attempt in (("B", 1), ("A", 2)):
        with pytest.raises(Conflict) as refused:
            done(queued.id, device=device, attempt=attempt)
        assert refused.value.code == "printing.job_not_yours"
    assert PrintJob.objects.get(pk=queued.id).status == "sent"


def test_a_failure_from_another_device_or_another_attempt_is_refused():
    till = printer("Till")
    queued = enqueue().job
    claim(till, device="A")
    for device, attempt in (("B", 1), ("A", 2)):
        with pytest.raises(Conflict) as refused:
            failure(queued.id, device=device, attempt=attempt)
        assert refused.value.code == "printing.job_not_yours"
    assert PrintJob.objects.get(pk=queued.id).status == "sent"


def test_a_failure_puts_the_job_back_until_five_and_then_it_fails():
    till = printer("Till")
    queued = enqueue().job
    for attempt in range(1, 5):
        claim(till)
        ack = failure(queued.id, attempt=attempt)
        assert (ack.confirmed, ack.job.status, ack.job.attempts, ack.job.last_error) == (
            True,
            "pending",
            attempt,
            "printer unreachable",
        )
    claim(till)
    ack = failure(queued.id, "out of paper", attempt=5)
    assert (ack.job.status, ack.job.attempts) == ("failed", 5)
    assert ack.job.failed_at is not None
    stored = Printer.objects.get(pk=till.id)
    assert (stored.last_error, stored.last_failed_at is not None) == ("out of paper", True)
    assert events("printing.job.failed")[-1] == {"id": str(queued.id), "final": True}
    assert failure(queued.id, "late", attempt=5).confirmed is False


# ── PRINTING-F18 Only a device the business set up prints (FIX-PRINTING-JOBS-CLAIMED-BY-ANY-DEVICE) ─
# A session with «print» took the jobs of any printer by naming it, and confirmed or failed them by naming the
# device that had them (shown in the queue: hub#2551). The device is the one that prints (the old hub's
# `_print_host`, hub#342): whoever sets up printers registers it with the printers it reaches; then only it,
# with any session that prints, takes, confirms or fails their jobs.

EMPLOYEE, MANAGER = "hub_employee", "hub_manager"
#: The devices' own ids (the SPA's X-Device-Id, the `deviceId` of /ws/print's hello): their credential.
TILL_ID = "3f1c9a52-6b0e-4c1d-9a77-0d2b5f8e4c11"
SPARE_ID = "9b7d2e40-1a35-4f6c-8e21-5c0a7d3b9f02"


def on_device(device: str | None, role: str = MANAGER) -> object:
    """The context of a person using the device ``device``: the SPA sends its id in ``X-Device-Id``."""
    headers = {"HTTP_X_DEVICE_ID": device} if device is not None else {}
    return dataclasses.replace(ctx_for(role), request=RequestFactory().post("/api/printing/devices", **headers))


def register(*printers: Printer, device: str | None = TILL_ID, name: str = "Till", role: str = MANAGER):
    """Sets up the device ``device`` to print on ``printers`` (printing.device.register, from the device)."""
    return run("printing.device.register", {"name": name, "printers": [str(p.id) for p in printers]}, ctx=on_device(device, role))


def take(*printers: Printer, device: str = TILL_ID, role: str = EMPLOYEE):
    return run("printing.job.claim", {"printers": [str(p.id) for p in printers], "device": device}, ctx=ctx_for(role)).job


def answer(operation: str, job_id, device: str = TILL_ID, attempt: int = 1, role: str = EMPLOYEE):
    extra = {"error": "printer unreachable"} if operation == "printing.job.fail" else {}
    data = {"job_id": str(job_id), "device": device, "attempt": attempt, **extra}
    return run(operation, data, ctx=ctx_for(role))


def test_an_employee_on_a_device_nobody_set_up_takes_nothing_and_changes_nothing():
    till = printer("Till")
    held = enqueue(source_ref="T-1").job
    claim(till, device="A")  # whoever sets up printers takes it from device A, whose lease then runs out
    expire(held.id)
    waiting = enqueue(source_ref="T-2").job
    devices = PrintDevice.objects.count()
    with pytest.raises(PermissionDenied) as refused:
        take(till, device="stranger")
    assert refused.value.code == "printing.device_not_registered"
    # Nothing moved: not the job it asked for, not the expired lease a claim puts back, no device paired.
    assert PrintJob.objects.get(pk=waiting.id).status == "pending"
    assert PrintJob.objects.get(pk=held.id).status == "sent"
    assert PrintDevice.objects.count() == devices


def test_a_manager_sets_up_this_device_and_an_employee_on_it_prints_its_printers():
    till = printer("Till")
    kitchen = printer("Kitchen", usage="kitchen", address="10.0.0.2")
    device = register(till, kitchen, name="Counter till")
    assert (device.name, sorted(p.name for p in device.printers), device.this_device) == (
        "Counter till",
        ["Kitchen", "Till"],
        True,
    )
    assert (device.registered_by, device.last_seen_at) == ("tester", None)
    assert events("printing.device.registered") == [{"id": str(device.id)}]
    queued = enqueue().job
    taken = take(till)
    assert taken.id == queued.id
    stored = PrintJob.objects.get(pk=queued.id)
    assert (stored.device, stored.print_device_id) == ("Counter till", device.id)
    assert PrintDevice.objects.get(pk=device.id).last_seen_at is not None
    ack = answer("printing.job.complete", queued.id)
    assert (ack.confirmed, ack.job.status, ack.job.device) == (True, "done", "Counter till")


def test_an_employee_takes_nothing_of_a_printer_its_device_does_not_reach():
    till = printer("Till")
    other = printer("Other", address="10.0.0.9")
    register(till)
    queued = enqueue(printer="Other").job
    with pytest.raises(PermissionDenied) as refused:
        take(till, other)
    assert refused.value.code == "printing.printer_not_on_device"
    assert PrintJob.objects.get(pk=queued.id).status == "pending"
    assert take(till) is None, "its own printer has nothing: Other's job is not handed to it"


def test_only_the_device_that_took_a_job_confirms_or_fails_it():
    till = printer("Till")
    register(till)
    register(till, device=SPARE_ID, name="Spare")
    queued = enqueue().job
    take(till)
    for device in (SPARE_ID, "never-set-up"):
        for operation in ("printing.job.complete", "printing.job.fail"):
            with pytest.raises(Conflict) as refused:
                answer(operation, queued.id, device=device)
            assert refused.value.code == "printing.job_not_yours", (device, operation)
    assert PrintJob.objects.get(pk=queued.id).status == "sent"
    assert answer("printing.job.fail", queued.id).job.status == "pending"


def test_whoever_sets_up_printers_pairs_the_device_by_printing_from_it():
    till = printer("Till")
    kitchen = printer("Kitchen", usage="kitchen", address="10.0.0.2")
    queued = enqueue().job
    assert take(till, device="till-1", role=MANAGER).id == queued.id
    device = PrintDevice.objects.get()
    assert (device.name, [p.id for p in device.printers.all()], device.registered_by) == ("Device 1", [till.id], "tester")
    assert events("printing.device.registered") == [{"id": str(device.id)}]
    # Printing from it on another printer adds that one; then an employee on it prints on both.
    take(till, kitchen, device="till-1", role=MANAGER)
    assert {p.id for p in PrintDevice.objects.get().printers.all()} == {till.id, kitchen.id}
    assert events("printing.device.updated") == [{"id": str(device.id)}]
    enqueue("kitchen_order", {"items": [ITEM]})
    assert take(kitchen, device="till-1") is not None
    # The next device it pairs is the second one.
    take(till, device="till-2", role=MANAGER)
    assert sorted(PrintDevice.objects.values_list("name", flat=True)) == ["Device 1", "Device 2"]


def test_a_retired_device_takes_nothing_and_printing_from_it_does_not_bring_it_back():
    till = printer("Till")
    device = register(till)
    retired = run("printing.device.retire", {"device_id": str(device.id)}, ctx=ctx_for(MANAGER))
    assert retired.id == device.id
    assert events("printing.device.retired") == [{"id": str(device.id)}]
    enqueue()
    for role in (EMPLOYEE, MANAGER):
        with pytest.raises(PermissionDenied) as refused:
            take(till, role=role)
        assert refused.value.code == "printing.device_not_registered", role
    assert run("printing.device.list", ctx=ctx_for(EMPLOYEE)).rows == []
    # Setting it up again, from the device, brings back the same registration.
    again = register(till, name="Till again")
    assert (again.id, again.name) == (device.id, "Till again")
    assert take(till) is not None


def test_the_devices_id_never_shows_in_the_queue_nor_in_its_registration():
    # hub#2551: an employee who read the till's id in the queue could print, confirm and fail as the till.
    till = printer("Till")
    register(till, name="Till")
    queued = enqueue().job
    take(till)
    shown = [
        run("printing.job.list", ctx=ctx_for(EMPLOYEE)),
        run("printing.device.list", ctx=ctx_for(EMPLOYEE)),
        run("printing.device.list", ctx=on_device(TILL_ID, EMPLOYEE)),
    ]
    for out in shown:
        assert TILL_ID not in json.dumps(out.model_dump(mode="json")), out
    stored = PrintDevice.objects.get()
    assert TILL_ID not in stored.key and len(stored.key) == 64, "the database keeps a digest of the id, never the id"
    assert PrintJob.objects.get(pk=queued.id).device == "Till"


def test_setting_up_a_device_takes_its_own_id_and_active_printers_of_the_business():
    till = printer("Till")
    with pytest.raises(InvalidPayload) as refused:
        register(till, device=None)  # the assistant or an API key: no device of its own
    assert refused.value.code == "printing.device_required"
    off = printer("Old", address="10.0.0.8", is_active=False)
    for printers in ([off], []):
        with pytest.raises(InvalidPayload) as refused:
            register(*printers)
        assert set(refused.value.fields) == {"printers"}, printers
    with pytest.raises(PermissionDenied):
        register(till, role=EMPLOYEE)
    assert not PrintDevice.objects.exists()


def test_a_manager_renames_a_device_and_changes_its_printers_from_any_device():
    till = printer("Till")
    kitchen = printer("Kitchen", usage="kitchen", address="10.0.0.2")
    device = register(till)
    changed = run(
        "printing.device.update",
        {"device_id": str(device.id), "name": "Kitchen tablet", "printers": [str(kitchen.id)]},
        ctx=ctx_for(MANAGER),
    )
    assert (changed.name, [p.id for p in changed.printers], changed.this_device) == ("Kitchen tablet", [kitchen.id], False)
    assert events("printing.device.updated") == [{"id": str(device.id)}]
    enqueue()
    with pytest.raises(PermissionDenied) as refused:
        take(till)
    assert refused.value.code == "printing.printer_not_on_device"
    with pytest.raises(PermissionDenied):
        run("printing.device.update", {"device_id": str(device.id), "name": "Mine"}, ctx=ctx_for(EMPLOYEE))
    with pytest.raises(NotFound) as missing:
        run("printing.device.update", {"device_id": str(PrintJob().id), "name": "Ghost"}, ctx=ctx_for(MANAGER))
    assert missing.value.code == "printing.device_not_found"


def test_a_device_set_up_in_a_hub_is_told_on_that_hubs_channel_only():
    # Writing in hub B never tells hub A: the device's events travel on the scope of whoever set it up.
    till = printer("Till")
    ctx = dataclasses.replace(on_device(TILL_ID), scope=B)
    device = run("printing.device.register", {"name": "Till", "printers": [str(till.id)]}, ctx=ctx)
    run("printing.device.retire", {"device_id": str(device.id)}, ctx=dataclasses.replace(ctx_for(MANAGER), scope=B))
    scoped = OutboxEvent.objects.filter(name__startswith="printing.device.").values_list("name", "scope_key")
    assert sorted(scoped) == [("printing.device.registered", "b"), ("printing.device.retired", "b")]


def test_the_channel_reads_the_printers_of_the_device_that_says_hello():
    # base's /ws/print has the device's id in its hello, not in a header: printing.device.get by that id.
    till = printer("Till")
    printer("Kitchen", usage="kitchen", address="10.0.0.2")
    register(till)
    found = run("printing.device.get", {"device": TILL_ID}, ctx=ctx_for(EMPLOYEE)).device
    assert (found.name, [(p.id, p.usage) for p in found.printers], found.this_device) == ("Till", [(till.id, "receipt")], True)
    assert run("printing.device.get", {"device": "never-set-up"}, ctx=ctx_for(EMPLOYEE)).device is None


# ── PRINTING-F04 A printer that leaves takes no queued job with it ───────────────────────────────


def test_deactivating_a_printer_moves_its_queued_jobs_to_the_printer_of_its_function_now():
    printer("Till")
    printer("Till 2", address="10.0.0.2")
    queued = enqueue(printer="Till").job
    before = len(events("printing.job.queued"))
    run("printing.printer.update", {"printer": "Till", "is_active": False})
    moved = PrintJob.objects.get(pk=queued.id)
    assert moved.printer.name == "Till 2"
    assert len(events("printing.job.queued")) == before + 1


def test_a_printer_that_changes_role_or_connection_lets_go_of_what_it_no_longer_prints():
    printer("Till")
    queued = enqueue(printer="Till").job
    run("printing.printer.update", {"printer": "Till", "usage": "kitchen"})
    assert PrintJob.objects.get(pk=queued.id).printer_id is None
    printer("Till 2", address="10.0.0.2")
    other = enqueue(printer="Till 2").job
    run("printing.printer.update", {"printer": "Till 2", "kind": "system", "address": ""})
    assert PrintJob.objects.get(pk=other.id).printer_id is None


def test_a_rename_keeps_the_queue_where_it_is():
    till = printer("Till")
    queued = enqueue(printer="Till").job
    run("printing.printer.update", {"printer": "Till", "name": "Front till"})
    assert PrintJob.objects.get(pk=queued.id).printer_id == till.id


# ── PRINTING-F14 Retry and cancel ───────────────────────────────────────────────────────────────


def failed_job(till: Printer) -> PrintJob:
    queued = enqueue().job
    PrintJob.objects.filter(pk=queued.id).update(status="failed", attempts=5, last_error="out of paper")
    return PrintJob.objects.get(pk=queued.id)


def test_a_failed_job_goes_back_to_the_queue_with_no_attempts():
    till = printer("Till")
    failed = failed_job(till)
    out = run("printing.job.retry", {"job_id": str(failed.id)}, ctx_for(actor="Ana"))
    assert (out.status, out.attempts, out.retried_by) == ("pending", 0, "Ana")
    assert out.retried_at is not None
    assert events("printing.job.retried") == [{"id": str(failed.id)}]
    assert events("printing.job.queued")[-1]["id"] == str(failed.id)


def test_a_retry_goes_to_the_printer_that_prints_its_function_now():
    till = printer("Till")
    failed = failed_job(till)
    PrintJob.objects.filter(pk=failed.id).update(printer_id=till.id)
    Printer.objects.filter(pk=till.id).update(is_active=False)
    new = printer("New till", address="10.0.0.5")
    assert run("printing.job.retry", {"job_id": str(failed.id)}).printer_id == new.id


def test_a_queued_failed_or_unanswered_job_is_retried_and_nothing_else():
    till = printer("Till")
    queued = enqueue(source_ref="T-7").job
    assert run("printing.job.retry", {"reference": "T-7"}).status == "pending"
    claim(till)
    with pytest.raises(Conflict) as refused:
        run("printing.job.retry", {"reference": "T-7"})
    assert refused.value.code == "printing.job_not_retryable"
    assert refused.value.message == (
        "Only a queued or failed job, or a sent one with no answer, goes back to the queue; this one is sent."
    )
    expire(queued.id)
    assert run("printing.job.retry", {"reference": "T-7"}).status == "pending"


def test_a_job_is_cancelled_with_its_reason_stays_and_lets_its_document_go():
    printer("Till")
    queued = enqueue(source_ref="T-8").job
    out = run("printing.job.cancel", {"reference": "T-8", "reason": "customer left"}, ctx_for(actor="Ana"))
    assert (out.status, out.cancelled_by, out.cancel_reason) == ("cancelled", "Ana", "customer left")
    cancelled = PrintJob.objects.get(pk=queued.id)
    assert (cancelled.document, cancelled.html, cancelled.reference) == ({}, "", "T-8")
    assert events("printing.job.cancelled") == [{"id": str(queued.id)}]


def test_a_job_a_device_is_printing_or_printed_is_not_cancelled():
    till = printer("Till")
    queued = enqueue().job
    claim(till)
    with pytest.raises(Conflict) as refused:
        run("printing.job.cancel", {"job_id": str(queued.id)})
    assert refused.value.code == "printing.job_not_cancellable"
    done(queued.id)
    with pytest.raises(Conflict) as refused:
        run("printing.job.cancel", {"job_id": str(queued.id)})
    assert refused.value.message == "A job that is printing or has printed is not cancelled; this one is printed."


def test_the_newest_job_of_a_reference_is_the_one_named():
    printer("Till")
    enqueue(source_ref="T-9")
    newest = enqueue(source_ref="T-9").job
    assert run("printing.job.cancel", {"reference": "T-9"}).id == newest.id
    with pytest.raises(NotFound) as refused:
        run("printing.job.cancel", {"reference": "T-404"})
    assert refused.value.message == "There is no print job with that id or number."


@pytest.mark.parametrize("role", ["hub_manager", "hub_employee"])
def test_only_who_runs_the_business_retries_and_cancels(role):
    printer("Till")
    queued = enqueue().job
    with pytest.raises(PermissionDenied):
        run("printing.job.cancel", {"job_id": str(queued.id)}, ctx_for(role))
    with pytest.raises(PermissionDenied):
        run("printing.job.retry", {"job_id": str(queued.id)}, ctx_for(role))


# ── The paper's envelope: language and money scale (hub#1159, hub#2129) ─────────────────────────


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


# Notifications: after the COMMIT, on the channel of the command's scope only


@pytest.fixture
def listen(db_dsn):
    import psycopg

    sessions = []

    def open_session(scope):
        from live.outbox import channel_for

        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=1.0, stop_after=None):
    import json

    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout, stop_after=stop_after)]


@pytest.mark.django_db(transaction=True)
def test_a_job_queued_in_b_wakes_b_only(listen):
    from live.outbox import channel_for

    from apps.printing.tests.conftest import A, B

    on_a, on_b = listen(A), listen(B)
    run("printing.job.create", {"document_type": "receipt", "document": RECEIPT}, ctx_for(scope=B))
    assert received(on_b, stop_after=1) == [(channel_for(B), {"events": ["printing.job.queued"]})]
    assert received(on_a, timeout=0.3) == []


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


# ── PRINTING-F20 How long the queue keeps a job (HUB-F206) ──────────────────────────────────────────


def ended(days: int, status: str, **more) -> PrintJob:
    """A job of the queue that ended ``days`` ago in ``status`` (or, still waiting, was queued then)."""
    when = timezone.now() - dt.timedelta(days=days)
    queued = PrintJob.objects.get(pk=enqueue(source_ref=f"{status}-{days}").job.id)
    stamp = {"done": "printed_at", "cancelled": "cancelled_at", "failed": "failed_at"}.get(status)
    PrintJob.objects.filter(pk=queued.pk).update(status=status, created_at=when - dt.timedelta(minutes=5), **({stamp: when} if stamp else {}), **more)
    return queued


def prune(ctx=None):
    return run("printing.job.prune", {}, ctx or system_context(A))


def test_a_finished_job_is_forgotten_30_days_after_it_ended_and_a_waiting_one_never():
    printer("Till")
    gone = [ended(31, "done"), ended(31, "cancelled"), ended(31, "failed")]
    kept = [ended(29, "done"), ended(29, "failed"), ended(60, "pending"), ended(60, "sent")]
    out = prune()
    assert out.count == 3
    assert set(PrintJob.objects.values_list("pk", flat=True)) == {job.pk for job in kept}
    assert not PrintJob.objects.filter(pk__in=[job.pk for job in gone]).exists()
    # The screens that show the queue re-run: a deleted failed job no longer counts.
    assert events("printing.job.pruned") == [{"count": 3}]


def test_nothing_to_forget_is_no_event():
    printer("Till")
    ended(10, "done")
    assert prune().count == 0
    assert events("printing.job.pruned") == []


def test_the_queue_is_forgotten_in_batches(monkeypatch):
    printer("Till")
    for _ in range(3):
        ended(40, "done")
    monkeypatch.setattr(services, "PRUNE_BATCH", 2)
    assert [prune().count, prune().count, prune().count] == [2, 1, 0]


def test_a_forgotten_key_can_print_again():
    printer("Till")
    old = ended(40, "done")
    prune()
    again = enqueue(job_key=old.job_key)
    assert (again.duplicate, again.job.status) == (False, "pending")


def test_only_the_platform_forgets_the_queue():
    for role in ("hub_manager", "hub_employee"):
        with pytest.raises(PermissionDenied):
            prune(ctx_for(role))

