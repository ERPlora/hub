"""Who prints each function: the Home's «Set up your printer» and the bell's «Nothing is printing»."""

import datetime as dt

import pytest
from django.db.models import F
from django.utils import timezone
from live.errors import PermissionDenied

from apps.printing.models import PrintJob
from apps.printing.queries.waiting import PENDING
from apps.printing.tests.conftest import HUB_DB, ctx_for, enqueue, printer, queued_ago, reaches, run

pytestmark = HUB_DB

ITEM = {"name": "Haircut", "quantity": 1, "total": 18.0}


# A device set up here (not retired) prints the active printers it reaches: the jobs of those printers, and the jobs of
# a function no printer took yet on the paper of one of them (``printing.job.claim``). A job no such device can take
# waits for ever: that is what the bell counts — once it has waited a minute, and counting as such a device only one
# that gave news in the last 90 s (below). The Home's step asks set up only: a device off right now is not a step
# undone.


def coverage(usage: str = "receipt", ctx=None, *, waited: dt.timedelta | None = dt.timedelta(minutes=2)):
    """``printing.device.coverage`` of ``usage``: (configured, count). ``waited``: read as if every job waiting had been
    queued that long before (the bell counts what waited a minute); ``None``: as they are."""
    if waited is not None:
        PrintJob.objects.filter(PENDING).update(created_at=F("created_at") - waited)
    out = run("printing.device.coverage", {"usage": usage}, ctx=ctx)
    assert out.usage == usage
    return out.configured, out.count


def test_a_business_without_printers_has_nobody_printing_and_nothing_waiting():
    assert coverage() == (False, 0)


def test_a_receipt_printer_no_device_reaches_prints_nothing_and_its_receipts_wait_for_nobody():
    printer("Till")
    enqueue()
    enqueue(job_key="sale:2")
    assert coverage() == (False, 2)


def test_a_device_set_up_with_the_receipt_printer_prints_the_receipts():
    reaches(printer("Till"))
    enqueue()
    assert coverage() == (True, 0)


def test_a_device_set_up_but_off_still_ticks_the_step_and_its_receipts_ring_the_bell():
    # A device set up counts for the step, live or not: a till off overnight is not a step undone. But nobody is
    # printing its receipts: the bell says so.
    reaches(printer("Till"), seen=dt.timedelta(minutes=5))
    enqueue()
    assert coverage() == (True, 1)


def test_a_retired_device_an_inactive_printer_or_another_functions_printer_print_no_receipt():
    till = printer("Till")
    reaches(till, retired=True)
    reaches(printer("Kitchen", usage="kitchen", address="10.0.0.2"), name="Kitchen tablet")
    enqueue()
    assert coverage() == (False, 1)
    assert coverage("kitchen") == (True, 0)

    reaches(till, name="New till")
    run("printing.printer.update", {"printer_id": str(till.id), "is_active": False})
    assert coverage()[0] is False


def test_the_computers_own_printer_prints_a4_pages_not_the_receipt():
    # Sales' receipt goes on receipt paper (the thermal printer); the computer's printer takes the A4 pages only.
    reaches(printer("Office", kind="system", address=""))
    assert coverage() == (False, 0)


def test_a_receipt_waiting_for_a_printer_is_not_printed_by_a_device_that_reaches_its_function_on_a4_only():
    # A device reaching the computer's printer of the receipts prints their A4 pages, not their paper: a receipt
    # queued with no receipt printer waits for nobody (the paper of printing.job.claim), on the bell too.
    reaches(printer("Office", kind="system", address=""))
    enqueue()
    assert coverage() == (False, 1)


def test_a_job_waits_for_nobody_when_its_own_printer_is_reached_by_no_device():
    # The device asks for the jobs of its printers: one sent to the other receipt printer is not its own.
    till, spare = printer("Till"), printer("Spare", address="10.0.0.9")
    reaches(till)
    enqueue(printer=str(spare.id))
    enqueue(printer=str(till.id), job_key="sale:2")
    assert coverage() == (True, 1)


def test_a_job_without_a_printer_waits_for_nobody_until_a_device_reaches_one_of_its_function_and_paper():
    till = printer("Till", is_active=False)
    reaches(till)
    enqueue()
    assert PrintJob.objects.get().printer_id is None
    assert coverage() == (False, 1)
    run("printing.printer.update", {"printer_id": str(till.id), "is_active": True})
    assert coverage() == (True, 0)


def test_only_waiting_jobs_count_never_one_a_device_has_or_that_ended():
    printer("Till")
    for status in ("sent", "done", "failed", "cancelled"):
        PrintJob.objects.filter(pk=enqueue(job_key=f"sale:{status}").job.id).update(status=status)
    assert coverage() == (False, 0)


def test_each_function_counts_its_own_jobs():
    printer("Till")
    printer("Kitchen", usage="kitchen", address="10.0.0.2")
    enqueue()
    enqueue("kitchen_order", {"order_number": "12", "table": "4", "items": [ITEM]}, job_key="kitchen:12")
    assert (coverage("receipt"), coverage("kitchen"), coverage("bar"), coverage("label")) == (
        (False, 1),
        (False, 1),
        (False, 0),
        (False, 0),
    )


def test_whoever_sees_the_printers_reads_it_and_nobody_else():
    assert coverage(ctx=ctx_for("hub_employee")) == (False, 0)
    with pytest.raises(PermissionDenied):
        run("printing.device.coverage", {"usage": "receipt"}, ctx=ctx_for("nobody"))


# ── The bell by the clock ──
# A job waits for nobody once it has waited a minute (``UNDRAINED_ALERT_SECONDS``: not every till that restarts) and no
# device set up to print it gave news in the last 90 s (``HOST_TTL_SECONDS``: three missed beats of 30 s). News is its
# hello and its beats on base's /ws/print (``printing.device.seen``), asking for a job and being set up from it.


def test_a_receipt_waiting_a_minute_with_its_device_off_rings_the_bell():
    reaches(printer("Till"), seen=dt.timedelta(seconds=95))
    queued_ago(65)
    assert coverage(waited=None) == (True, 1)


def test_a_device_that_gave_news_in_the_last_90_seconds_prints_them_and_the_bell_is_quiet():
    device = reaches(printer("Till"), seen=dt.timedelta(seconds=85))
    queued_ago(65)
    assert coverage(waited=None) == (True, 0)
    # The till went quiet: three beats later, it counts as off.
    type(device).objects.filter(pk=device.pk).update(last_seen_at=timezone.now() - dt.timedelta(seconds=95))
    assert coverage(waited=None) == (True, 1)


def test_a_device_that_never_gave_news_prints_nothing():
    reaches(printer("Till"), seen=None)
    queued_ago(65)
    assert coverage(waited=None) == (True, 1)


def test_a_receipt_queued_less_than_a_minute_ago_does_not_ring_it_yet():
    # Not a red badge on every screen each time a till restarts: the bell waits a minute.
    till = printer("Till")
    reaches(till, seen=None)
    queued_ago(50)
    queued_ago(5, job_key="sale:2")
    assert coverage(waited=None) == (True, 0)
    queued_ago(70, job_key="sale:3")
    assert coverage(waited=None) == (True, 1), "only what waited a minute"


def test_the_minute_counts_for_a_printer_no_device_reaches_too():
    printer("Till")
    queued_ago(30)
    assert coverage(waited=None) == (False, 0)
    queued_ago(61, job_key="sale:2")
    assert coverage(waited=None) == (False, 1)


def test_another_devices_news_does_not_print_a_printer_it_does_not_reach():
    till, spare = printer("Till"), printer("Spare", address="10.0.0.9")
    reaches(till, name="Till device", seen=dt.timedelta(minutes=5))
    reaches(spare, name="Spare device")
    queued_ago(65, printer=str(till.id))
    assert coverage(waited=None) == (True, 1)
