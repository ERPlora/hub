"""Read operations of the printing app: the settings (the factory ones until saved), the printers with
their state, the state of one printer, the queue and its summary by function."""

import datetime as dt

import pytest
from django.db.models import F
from django.utils import timezone
from live.errors import NotFound, PermissionDenied

from apps.printing.models import Printer, PrintJob
from apps.printing.queries import PENDING
from apps.printing.tests.conftest import ctx_for, enqueue, printer, run

pytestmark = pytest.mark.django_db

ITEM = {"name": "Haircut", "quantity": 1, "total": 18.0}


def age(job_id, minutes: int) -> None:
    PrintJob.objects.filter(pk=job_id).update(created_at=timezone.now() - dt.timedelta(minutes=minutes))


# ── Settings ────────────────────────────────────────────────────────────────────────────────────


def test_a_business_that_never_saved_has_the_factory_settings():
    # printing#42: the read answers the defaults and never writes a row.
    out = run("printing.settings.get")
    assert (out.print_receipt_on_sale, out.open_drawer_on_sale, out.receipt_copies, out.updated_at) == (True, False, 1, None)
    assert (out.receipt_printer_id, out.kitchen_printer_id, out.bar_printer_id, out.label_printer_id) == (None,) * 4
    from apps.printing.models import Settings

    assert not Settings.objects.exists()


def test_the_settings_read_what_was_saved():
    kitchen = printer("Kitchen", usage="kitchen")
    run("printing.settings.update", {"print_receipt_on_sale": False, "kitchen_printer": "Kitchen"})
    out = run("printing.settings.get", ctx=ctx_for("hub_employee"))
    assert (out.print_receipt_on_sale, out.kitchen_printer_id) == (False, kitchen.id)


def test_a_role_without_printing_reads_nothing():
    with pytest.raises(PermissionDenied):
        run("printing.settings.get", ctx=ctx_for("nobody"))


# ── Printers (PRINTING-F03, F04, F19) ───────────────────────────────────────────────────────────


def test_the_printers_by_name_with_search_and_filters():
    printer("Till")
    printer("Kitchen", usage="kitchen", address="10.0.0.2")
    printer("Office", kind="system", address="", is_active=False)
    page = run("printing.printer.list")
    assert [row.name for row in page.rows] == ["Kitchen", "Office", "Till"]
    assert (page.total, page.limit, page.offset) == (3, 50, 0)
    assert [row.name for row in run("printing.printer.list", {"search": "10.0.0"}).rows] == ["Kitchen"]
    assert [row.name for row in run("printing.printer.list", {"usage": "kitchen"}).rows] == ["Kitchen"]
    assert [row.name for row in run("printing.printer.list", {"kind": "system"}).rows] == ["Office"]
    assert [row.name for row in run("printing.printer.list", {"is_active": True}).rows] == ["Kitchen", "Till"]
    assert [row.name for row in run("printing.printer.list", {"sort": "name", "dir": "desc", "limit": 1}).rows] == ["Till"]


def test_a_printer_by_its_name_or_its_id():
    till = printer("Till")
    assert run("printing.printer.get", {"printer": "TILL"}).id == till.id
    assert run("printing.printer.get", {"printer_id": str(till.id)}).name == "Till"
    assert run("printing.printer.get", {"printer": str(till.id)}).name == "Till"
    with pytest.raises(NotFound):
        run("printing.printer.get", {"printer": "Nowhere"})


def test_the_state_of_a_printer():
    till = printer("Till")
    assert run("printing.printer.get", {"printer": "Till"}).state == "ready"
    queued = enqueue().job
    assert run("printing.printer.get", {"printer": "Till"}).pending == 1
    assert run("printing.printer.get", {"printer": "Till"}).state == "ready"
    age(queued.id, 2)
    assert run("printing.printer.get", {"printer": "Till"}).state == "waiting"
    now = timezone.now()
    Printer.objects.filter(pk=till.id).update(last_failed_at=now, last_error="out of paper")
    out = run("printing.printer.get", {"printer": "Till"})
    assert (out.state, out.last_error) == ("failing", "out of paper")
    Printer.objects.filter(pk=till.id).update(last_printed_at=now + dt.timedelta(seconds=1))
    assert run("printing.printer.get", {"printer": "Till"}).state == "waiting"
    Printer.objects.filter(pk=till.id).update(is_active=False)
    assert run("printing.printer.get", {"printer": "Till"}).state == "inactive"


def test_the_status_of_a_printer_counts_its_queue():
    printer("Till")
    run("printing.settings.update", {"receipt_printer": "Till"})
    first = enqueue().job
    age(first.id, 3)
    second = enqueue().job
    PrintJob.objects.filter(pk=second.id).update(status="failed")
    out = run("printing.printer.status", {"printer": "till"}, ctx_for("hub_employee"))
    assert (out.printer.name, out.is_default, out.pending, out.sent, out.failed) == ("Till", True, 1, 0, 1)
    assert out.oldest_pending_at < timezone.now() - dt.timedelta(minutes=2)


# ── The queue (PRINTING-F01, F14) ───────────────────────────────────────────────────────────────


def test_the_queue_newest_first_with_its_printer_and_what_can_be_done():
    printer("Till")
    first = enqueue(source_ref="T-1").job
    age(first.id, 5)
    second = enqueue(source_ref="T-2").job
    PrintJob.objects.filter(pk=first.id).update(status="failed", attempts=5, last_error="out of paper")
    page = run("printing.job.list")
    assert [row.reference for row in page.rows] == ["T-2", "T-1"]
    newest, oldest = page.rows
    assert (newest.printer_name, newest.status, newest.retryable, newest.cancellable, newest.stale) == (
        "Till",
        "pending",
        True,
        True,
        False,
    )
    assert (oldest.status, oldest.retryable, oldest.cancellable, oldest.last_error) == ("failed", True, True, "out of paper")
    assert second.id == newest.id


def test_a_sent_job_with_no_answer_is_stale():
    printer("Till")
    queued = enqueue().job
    PrintJob.objects.filter(pk=queued.id).update(status="sent", leased_until=timezone.now() - dt.timedelta(seconds=1))
    row = run("printing.job.list").rows[0]
    assert (row.status, row.stale, row.retryable, row.cancellable) == ("sent", True, True, True)
    PrintJob.objects.filter(pk=queued.id).update(leased_until=timezone.now() + dt.timedelta(seconds=60))
    row = run("printing.job.list").rows[0]
    assert (row.stale, row.retryable, row.cancellable) == (False, False, False)


def test_the_queue_filters():
    till = printer("Till")
    printer("Kitchen", usage="kitchen", address="10.0.0.2")
    enqueue(source_ref="T-1")
    kitchen = enqueue("kitchen_order", {"items": [ITEM], "order_number": 7}).job
    PrintJob.objects.filter(pk=kitchen.id).update(status="done")
    assert [row.reference for row in run("printing.job.list", {"usage": "kitchen"}).rows] == ["7"]
    assert [row.reference for row in run("printing.job.list", {"status": "pending"}).rows] == ["T-1"]
    assert [row.reference for row in run("printing.job.list", {"printer_id": str(till.id)}).rows] == ["T-1"]
    assert [row.reference for row in run("printing.job.list", {"search": "t-1"}).rows] == ["T-1"]
    assert [row.reference for row in run("printing.job.list", {"sort": "usage", "dir": "asc"}).rows] == ["7", "T-1"]


def test_the_summary_by_function():
    printer("Till")
    printer("Kitchen", usage="kitchen", address="10.0.0.2")
    run("printing.settings.update", {"kitchen_printer": "Kitchen"})
    old = enqueue().job
    age(old.id, 4)
    enqueue()
    label = enqueue("barcode_label", {"product_name": "Shampoo", "barcode": "SHA-1", "price": 9.5}).job
    PrintJob.objects.filter(pk=label.id).update(status="failed")
    out = run("printing.job.summary")
    by_usage = {row.usage: row for row in out.usages}
    assert [row.usage for row in out.usages] == ["receipt", "kitchen", "bar", "label"]
    assert (by_usage["receipt"].printers, by_usage["receipt"].pending, by_usage["receipt"].default_printer) == (1, 2, None)
    assert by_usage["receipt"].oldest_pending_at < timezone.now() - dt.timedelta(minutes=3)
    assert (by_usage["kitchen"].printers, by_usage["kitchen"].default_printer, by_usage["kitchen"].pending) == (1, "Kitchen", 0)
    assert (by_usage["label"].printers, by_usage["label"].failed) == (0, 1)
    assert (out.pending, out.failed) == (2, 1)


def test_the_summary_names_the_printer_each_function_prints_on():
    # hub#1527: the card says WHERE a function prints, never only how many printers it has.
    def prints_on() -> dict:
        return {row.usage: row.prints_on for row in run("printing.job.summary").usages}

    printer("Till 2", address="10.0.0.9")
    printer("till")
    printer("Office", kind="system", address="")
    printer("Bar", usage="bar", address="10.0.0.3", is_active=False)
    # Nothing chosen: the first active receipt printer by name, whatever its case; a function with no active one, none.
    assert prints_on() == {"receipt": "till", "kitchen": None, "bar": None, "label": None}
    run("printing.settings.update", {"receipt_printer": "Till 2"})
    assert prints_on()["receipt"] == "Till 2"
    # The chosen one goes inactive: its function prints on the first active one again.
    run("printing.printer.update", {"printer": "Till 2", "is_active": False})
    run("printing.printer.update", {"printer": "till", "is_active": False})
    # Only the computer's printer is left: receipts come out there (on A4).
    assert prints_on()["receipt"] == "Office"


# ── The devices that print (PRINTING-F18) ───────────────────────────────────────────────────────


def test_the_devices_by_name_with_the_printers_each_one_reaches():
    from apps.printing.models import PrintDevice

    till = printer("Till")
    kitchen = printer("Kitchen", usage="kitchen", address="10.0.0.2", is_active=False)
    counter = PrintDevice.objects.create(name="Counter", key=PrintDevice.key_of("counter"), registered_by="Ana")
    counter.printers.add(till.id, kitchen.id)
    PrintDevice.objects.create(name="bar tablet", key=PrintDevice.key_of("bar"))
    gone = PrintDevice.objects.create(name="Old till", key=PrintDevice.key_of("old"), retired_at=timezone.now())
    gone.printers.add(till.id)

    out = run("printing.device.list", ctx=ctx_for("hub_employee"))
    assert (out.total, [row.name for row in out.rows]) == (2, ["bar tablet", "Counter"])
    row = out.rows[1]
    assert [(p.name, p.usage, p.is_active) for p in row.printers] == [("Kitchen", "kitchen", False), ("Till", "receipt", True)]
    assert (row.registered_by, row.last_seen_at, row.this_device) == ("Ana", None, False)
    assert run("printing.device.list", {"limit": 1, "offset": 1}).rows[0].name == "Counter"
    with pytest.raises(PermissionDenied):
        run("printing.device.list", ctx=ctx_for("nobody"))


# ── Who prints each function: the Home's «Set up your printer» and the bell's «Nothing is printing» ───────────────
# A device set up here (not retired) prints the active printers it reaches: the jobs of those printers, and the jobs of
# a function no printer took yet on the paper of one of them (``printing.job.claim``). A job no such device can take
# waits for ever: that is what the bell counts (old-hub:HUB_SHELL-F63, gh:hub#800) — once it has waited a minute, and
# counting as such a device only one that gave news in the last 90 s (FIX-HUB-PRINTING-BELL-SILENT-WITH-DEVICE-OFF,
# below). The Home's step asks set up only: a device off right now is not a step undone.


def reaches(*printers, name: str = "Counter", retired: bool = False, seen: dt.timedelta | None = dt.timedelta(0)):
    """A device set up with ``printers``; ``seen``: how long ago it last gave news (``None``: never)."""
    from apps.printing.models import PrintDevice

    now = timezone.now()
    device = PrintDevice.objects.create(
        name=name,
        key=PrintDevice.key_of(name),
        retired_at=now if retired else None,
        last_seen_at=None if seen is None else now - seen,
    )
    device.printers.add(*(p.id for p in printers))
    return device


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
    # The old hub's «registered for the station, live or not» (hub#1948): a till off overnight is not a step undone. But
    # nobody is printing its receipts: the bell says so (print_hosts::is_undrained, live_hosts == 0).
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


# ── The bell by the clock (FIX-HUB-PRINTING-BELL-SILENT-WITH-DEVICE-OFF): the old hub's ``print_hosts::is_undrained``.
# A job waits for nobody once it has waited a minute (``UNDRAINED_ALERT_SECONDS``: not every till that restarts) and no
# device set up to print it gave news in the last 90 s (``HOST_TTL_SECONDS``: three missed beats of 30 s). News is its
# hello and its beats on base's /ws/print (``printing.device.seen``), asking for a job and being set up from it.


def queued_ago(seconds: int, **more):
    """A receipt queued ``seconds`` ago."""
    job = enqueue(**more).job
    PrintJob.objects.filter(pk=job.id).update(created_at=timezone.now() - dt.timedelta(seconds=seconds))
    return job


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
    # Not a red badge on every screen each time a till restarts (the old hub's 60 s).
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


def test_the_summary_by_function_counts_what_no_device_set_up_here_can_print():
    # The bell's «Nothing is printing “…”» leads to the printers' summary: each function says it too, so the card
    # never says «Ready» while its paper waits for nobody.
    till = printer("Till")
    enqueue()

    def unattended() -> dict:
        return {row.usage: row.unattended for row in run("printing.job.summary").usages}

    assert unattended() == {"receipt": 1, "kitchen": 0, "bar": 0, "label": 0}
    reaches(till, seen=None)
    # «Set one up» is for what no device set up prints: one set up, even off, is no device to set up.
    assert unattended()["receipt"] == 0


def test_the_summary_by_function_counts_what_waited_a_minute_with_its_device_off_as_the_bell():
    # Where the bell's «Nothing is printing “Receipt”» leads, the receipts' card says the device is off, not «Ready».
    till = printer("Till")
    device = reaches(till, seen=dt.timedelta(minutes=5))
    queued_ago(65)
    queued_ago(10, job_key="sale:2")

    def stalled() -> dict:
        return {row.usage: row.stalled for row in run("printing.job.summary").usages}

    assert stalled() == {"receipt": 1, "kitchen": 0, "bar": 0, "label": 0}
    type(device).objects.filter(pk=device.pk).update(last_seen_at=timezone.now())
    assert stalled()["receipt"] == 0


def test_a_job_waiting_without_a_printer_is_only_taken_by_a_device_of_its_own_function():
    # A kitchen order with no kitchen printer waits for one: the device of the receipts never takes it.
    reaches(printer("Till"))
    enqueue(usage="kitchen", job_key="kitchen:1")
    assert PrintJob.objects.get().printer_id is None
    summary = {row.usage: row.unattended for row in run("printing.job.summary").usages}
    assert (summary["receipt"], summary["kitchen"]) == (0, 1)
