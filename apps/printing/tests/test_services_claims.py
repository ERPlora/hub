"""The device that prints takes, confirms and fails the jobs of its printers (PRINTING-F18), and only a device the
business set up does."""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import Conflict, PermissionDenied

from apps.printing.models import PrintDevice, Printer, PrintJob
from apps.printing.tests.conftest import HUB_DB, RECEIPT, ctx_for, enqueue, printer, run
from apps.printing.tests.test_services import (
    ITEM,
    MANAGER,
    SPARE_ID,
    STAMPED,
    answer,
    claim,
    done,
    events,
    expire,
    failure,
    register,
    take,
)

pytestmark = HUB_DB


# ── PRINTING-F18 The device takes and confirms ──────────────────────────────────────────────────


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
    # The job names the device by its registration, never by the id it sent (that id is its credential):
    # whoever sets up printers pairs the device by printing from it, as «Device 1».
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
    # did come out: the device's «done» is taken from the queue too.
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


def test_printing_from_a_new_device_on_no_active_printer_pairs_nothing_and_changes_nothing():
    # Review of hub#120: a manager on a device nobody set up, naming only inactive printers, paired it as
    # «Device N» with no printer — a device that prints nothing, listed in Devices.
    till = printer("Till")
    off = printer("Off", address="10.0.0.3")
    run("printing.printer.update", {"printer_id": str(off.id), "is_active": False})
    held = enqueue(source_ref="T-1").job
    claim(till, device="A")
    expire(held.id)
    waiting = enqueue(source_ref="T-2").job
    devices, registered = PrintDevice.objects.count(), events("printing.device.registered")
    with pytest.raises(PermissionDenied) as refused:
        take(off, device="till-1", role=MANAGER)
    assert refused.value.code == "printing.device_not_registered"
    # Nothing moved: no device paired, not the expired lease a claim puts back, not the queued job.
    assert (PrintDevice.objects.count(), events("printing.device.registered")) == (devices, registered)
    assert PrintJob.objects.get(pk=held.id).status == "sent"
    assert PrintJob.objects.get(pk=waiting.id).status == "pending"


def test_a_retired_device_confirms_and_fails_nothing_it_still_holds():
    # Retiring a device is a decision (a till lost or replaced): the job it had in hand is not confirmed nor failed
    # from it any more, and goes back to the queue when its time to answer runs out.
    till = printer("Till")
    device = register(till)
    queued = enqueue().job
    take(till)
    run("printing.device.retire", {"device_id": str(device.id)}, ctx=ctx_for(MANAGER))
    for operation in ("printing.job.complete", "printing.job.fail"):
        with pytest.raises(Conflict) as refused:
            answer(operation, queued.id)
        assert refused.value.code == "printing.job_not_yours", operation
    assert PrintJob.objects.get(pk=queued.id).status == "sent"
    expire(queued.id)
    register(till, device=SPARE_ID, name="Spare")
    assert take(till, device=SPARE_ID).id == queued.id, "back in the queue, the spare set up for Till takes it"
