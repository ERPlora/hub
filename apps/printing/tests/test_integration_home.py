"""Printing on the Home (PLAN-HUB round 2026-10-21; FIX-PRINTING-SETUP-HOOKS): base's own queries bring the old hub's
core item «Set up your printer» (gh:hub#1948), recommended, pending until a device set up here reaches an active
receipt printer, to whoever sets printers up; and the bell's «Nothing is printing “…”» (old-hub:HUB_SHELL-F63,
gh:hub#800), one row per function with the jobs that have waited a minute and no device on can print (set up here and
seen in the last 90 s, FIX-HUB-PRINTING-BELL-SILENT-WITH-DEVICE-OFF), to everybody with Printing, leading to the
printers' state by function (gh:hub#2016). Every change of either records an event they are refreshed on, the bell
reads the clock every 30 s for what time moves, and a change in hub B re-runs B's Home only.

base and printing run for real: the hooks come from PrintingConfig through base's own queries, as the person.
"""

import dataclasses
import datetime as dt
import json

import psycopg
import pytest
from django.apps import apps
from django.db.models import F
from django.utils import timezone
from live.live_registry import live_registry
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.printing.models import PrintDevice, PrintJob
from apps.printing.tests.conftest import A, B, ctx_for, enqueue, printer, run
from apps.printing.tests.test_services import SPARE_ID, TILL_ID, answer, on_device, register, take
from base.permissions import VIEW_HOME
from base.schemas import BellCountersIn, SetupStatusIn

STEP = "printing.printer"
WAIT = 1.0
QUIET = 0.3


def step(ctx) -> dict | None:
    """Printing's step of «Finish setting up your business» for the person of ``ctx`` (``None``: not told)."""
    items = get("base.setup.status")(ctx, SetupStatusIn()).model_dump(mode="json")["items"]
    found = [item for item in items if item["app"] == "printing"]
    assert len(found) <= 1, found
    return found[0] if found else None


def bell_read(ctx, *, waited: dt.timedelta | None = dt.timedelta(minutes=2)) -> dict:
    """``base.bell.counters`` for the person of ``ctx``, as the SPA receives it. ``waited``: read as if every job waiting
    had been queued that long before (the bell counts what waited a minute); ``None``: as they are."""
    if waited is not None:
        PrintJob.objects.filter(status=PrintJob.Status.PENDING).update(created_at=F("created_at") - waited)
    return get("base.bell.counters")(ctx, BellCountersIn()).model_dump(mode="json")


def bell(ctx, **read) -> dict[str, dict]:
    """Printing's rows of the bell for the person of ``ctx``, by key, as the SPA receives them."""
    return {row["key"]: row for row in bell_read(ctx, **read)["counters"] if row["app"] == "printing"}


def counted(ctx=None) -> dict[str, int]:
    return {key: row["count"] for key, row in bell(ctx or ctx_for("hub_employee")).items()}


# ── «Set up your printer» ────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_hub_without_a_receipt_printer_has_set_up_your_printer_pending_and_it_leads_to_the_devices():
    item = step(ctx_for("hub_owner"))
    assert {name: item[name] for name in ("key", "state", "level", "required", "actionable", "route", "order", "icon")} == {
        "key": STEP,
        "state": "pending",
        "level": "recommended",
        "required": False,
        "actionable": True,
        "route": "/printing/devices",
        "order": 70,
        "icon": "lucide:receipt",
    }
    assert (item["title"], item["description"]) == (
        "Set up your printer",
        "Register the device that prints your customers' receipts, so the first sale comes out on paper.",
    )


@pytest.mark.django_db
def test_in_spanish_it_says_the_old_words():
    item = step(ctx_for("hub_owner", language="es"))
    assert (item["title"], item["description"]) == (
        "Configura la impresora",
        "Da de alta el dispositivo que imprime los tiques de tus clientes, para que la primera venta salga en papel.",
    )


@pytest.mark.django_db
def test_a_receipt_printer_alone_is_not_enough_the_device_that_prints_it_ticks_it():
    till = printer("Till")
    assert step(ctx_for())["state"] == "pending"
    register(till)
    assert step(ctx_for())["state"] == "done"


@pytest.mark.django_db
def test_the_manager_who_sets_printers_up_is_told_and_the_employee_is_not():
    # Recommended, never ⛔: who cannot set a printer up is not told (base's rule; hub#435 is for the wall only).
    assert step(ctx_for("hub_manager"))["state"] == "pending"
    assert step(ctx_for("hub_employee")) is None


def unregister(till, spare):
    """The device that printed the receipts reaches another function's printer only."""
    device = register(till)
    run("printing.device.update", {"device_id": str(device.id), "printers": [str(spare.id)]})


def retire(till, spare):
    run("printing.device.retire", {"device_id": str(register(till).id)})


def switch_off(till, spare):
    register(till)
    run("printing.printer.update", {"printer_id": str(till.id), "is_active": False})


#: Each event of the step's ``refresh_on`` → a change of the step that records it (done → pending, after a device set
#: up with the receipt printer).
UNDOING = {
    "printing.device.updated": unregister,
    "printing.device.retired": retire,
    "printing.printer.updated": switch_off,
}


@pytest.mark.django_db
@pytest.mark.parametrize("event", list(UNDOING))
def test_each_change_of_the_step_records_an_event_that_refreshes_it(event):
    till, spare = printer("Till"), printer("Kitchen", usage="kitchen", address="10.0.0.2")
    seen = set(OutboxEvent.objects.values_list("id", flat=True))
    UNDOING[event](till, spare)
    recorded = set(OutboxEvent.objects.exclude(id__in=seen).values_list("name", flat=True))
    assert step(ctx_for())["state"] == "pending"
    assert recorded & set(printing().setup[0].refresh_on) == {"printing.device.registered", event}


@pytest.mark.django_db
def test_setting_the_device_up_by_printing_from_it_records_the_event_that_ticks_it():
    # PRINTING-F18: whoever sets printers up pairs the device by printing from it.
    till = printer("Till")
    seen = set(OutboxEvent.objects.values_list("id", flat=True))
    run("printing.job.claim", {"printers": [str(till.id)], "device": TILL_ID}, ctx=ctx_for("hub_manager"))
    recorded = set(OutboxEvent.objects.exclude(id__in=seen).values_list("name", flat=True))
    assert step(ctx_for())["state"] == "done"
    assert recorded & set(printing().setup[0].refresh_on) == {"printing.device.registered"}


def test_the_step_is_refreshed_on_nothing_else():
    assert set(printing().setup[0].refresh_on) == {"printing.device.registered", *UNDOING}


# ── «Nothing is printing “…”» ────────────────────────────────────────────────────────────────────────────────────


def printing():
    return apps.get_app_config("printing")


@pytest.mark.django_db
def test_receipts_waiting_for_a_printer_no_device_reaches_ring_the_bell_and_lead_to_the_printers():
    # gh:hub#800: the owner is told that nobody is printing, and which function (gh:hub#2016: where it is fixed).
    printer("Till")
    enqueue()
    enqueue(job_key="sale:2")
    assert bell(ctx_for("hub_employee")) == {
        "printing.stalled_receipt": {
            "key": "printing.stalled_receipt",
            "app": "printing",
            "count": 2,
            "route": "/printing/printers",
            "label": "Nothing is printing “Receipt”",
            "icon": "lucide:receipt",
        }
    }


@pytest.mark.django_db
def test_in_spanish_the_row_names_the_function_as_printing_does():
    printer("Kitchen", usage="kitchen", address="10.0.0.2")
    enqueue(usage="kitchen", job_key="kitchen:1")
    assert [row["label"] for row in bell(ctx_for("hub_employee", language="es")).values()] == [
        "Nadie está imprimiendo «Cocina»"
    ]


@pytest.mark.django_db
def test_a_device_that_prints_them_quiets_the_bell_and_at_zero_nothing_shows():
    till = printer("Till")
    enqueue()
    register(till)
    assert bell(ctx_for()) == {}


@pytest.mark.django_db
def test_a_device_set_up_but_off_rings_the_bell_once_the_receipt_waited_a_minute():
    # FIX-HUB-PRINTING-BELL-SILENT-WITH-DEVICE-OFF: the till set up for the receipts went off (no news for 90 s, the old
    # hub's HOST_TTL_SECONDS); a minute after a receipt is queued (UNDRAINED_ALERT_SECONDS), nobody is printing it.
    till = printer("Till")
    register(till)
    PrintDevice.objects.update(last_seen_at=timezone.now() - dt.timedelta(seconds=95))
    job = enqueue().job
    assert bell(ctx_for("hub_employee"), waited=None) == {}, "not before the minute"
    PrintJob.objects.filter(pk=job.id).update(created_at=timezone.now() - dt.timedelta(seconds=65))
    assert counted() == {"printing.stalled_receipt": 1}
    assert step(ctx_for("hub_owner"))["state"] == "done", "the step asks set up only: off is not undone"

    # The till says it is there (base's /ws/print, at its hello and its beats): nobody waits for it any more.
    run("printing.device.seen", {"device": TILL_ID}, ctx=ctx_for("hub_employee"))
    assert bell(ctx_for("hub_employee"), waited=None) == {}


@pytest.mark.django_db
def test_the_bell_reads_its_rows_again_every_30_seconds_for_whoever_sees_printing():
    # Nothing records an event when a minute passes or a till goes quiet: the SPA's bell asks again (HubBell.vue).
    assert bell_read(ctx_for("hub_employee"))["refresh_every"] == 30
    # Printing is the only app whose bell moves with the clock: whoever cannot see it is not asked again.
    who_sees_the_home_only = dataclasses.replace(ctx_for("hub_employee"), permissions=frozenset({VIEW_HOME}))
    assert bell_read(who_sees_the_home_only)["refresh_every"] is None


@pytest.mark.django_db
def test_each_function_is_its_own_row():
    printer("Till")
    printer("Kitchen", usage="kitchen", address="10.0.0.2")
    enqueue()
    enqueue(usage="kitchen", job_key="kitchen:1")
    enqueue(usage="kitchen", job_key="kitchen:2")
    assert counted() == {"printing.stalled_receipt": 1, "printing.stalled_kitchen": 2}


@pytest.mark.django_db
def test_without_a_permission_of_printing_there_is_no_row():
    printer("Till")
    enqueue()
    who_sees_the_home_only = dataclasses.replace(ctx_for("hub_employee"), permissions=frozenset({VIEW_HOME}))
    assert bell(who_sees_the_home_only) == {}


# ── What refreshes it: every change of the number records one of its events ──────────────────────────────────────


def nothing(till, spare):
    return None


def queue_one(till, spare):
    enqueue(printer=str(spare.id), job_key="sale:new")


def cancel_one(till, spare):
    run("printing.job.cancel", {"job_id": str(PrintJob.objects.get(printer=spare.id).id)})


def hold_one_and_move_away(till, spare):
    # A device holds a receipt of the till; meanwhile it is moved to the other printer.
    device = register(till, spare)
    enqueue(printer=str(till.id), job_key="sale:held")
    take(till)
    run("printing.device.update", {"device_id": str(device.id), "printers": [str(spare.id)]})


def fail_it(till, spare):
    # It fails it: the receipt goes back to the queue, on the till no device reaches now.
    answer("printing.job.fail", PrintJob.objects.get(printer=till.id).id)


def set_up(till, spare):
    register(spare)


def set_up_the_till(till, spare):
    register(till)


def move_it(till, spare):
    device_id = run("printing.device.list").rows[0].id
    run("printing.device.update", {"device_id": str(device_id), "printers": [str(spare.id)]})


def set_up_the_spare(till, spare):
    register(spare, device=SPARE_ID)


def retire_it(till, spare):
    run("printing.device.retire", {"device_id": str(run("printing.device.list").rows[0].id)})


def orphan_one(till, spare):
    # A receipt queued while no receipt printer is on waits without one.
    register(till)
    run("printing.printer.update", {"printer_id": str(till.id), "is_active": False})
    run("printing.printer.update", {"printer_id": str(spare.id), "is_active": False})
    enqueue(job_key="sale:orphan")


def switch_on(till, spare):
    # The till a device reaches comes back on: the receipts that wait without a printer are its.
    run("printing.printer.update", {"printer_id": str(till.id), "is_active": True})


#: Each event of the counters' ``refresh_on`` → (what comes before, the change of the number that records it). A retry
#: and a job back from a device that never answered record ``queued`` too; a claim changes it only when it sets the
#: device up (``registered`` or ``updated``).
CHANGES = {
    "printing.job.queued": (nothing, queue_one),
    "printing.job.cancelled": (nothing, cancel_one),
    "printing.job.failed": (hold_one_and_move_away, fail_it),
    "printing.device.registered": (nothing, set_up),
    "printing.device.updated": (set_up_the_till, move_it),
    "printing.device.retired": (set_up_the_spare, retire_it),
    "printing.printer.updated": (orphan_one, switch_on),
}


@pytest.mark.django_db
@pytest.mark.parametrize("event", list(CHANGES))
def test_each_change_of_the_number_records_an_event_that_refreshes_the_bell(event):
    """A receipt waits on «Spare», which no device reaches, before each change (the till is the first by name)."""
    till, spare = printer("A till"), printer("Spare", address="10.0.0.9")
    enqueue(printer=str(spare.id))
    arrange, change = CHANGES[event]
    arrange(till, spare)
    before = counted()
    seen = set(OutboxEvent.objects.values_list("id", flat=True))

    change(till, spare)

    recorded = set(OutboxEvent.objects.exclude(id__in=seen).values_list("name", flat=True))
    assert counted() != before
    assert recorded & set(printing().bell[0].refresh_on) == {event}


def test_every_event_it_is_refreshed_on_changes_the_number():
    """Not one more: the counters are re-run on what changes them, and nothing else."""
    counters = printing().bell
    assert len(counters) == 4
    assert all(set(counter.refresh_on) == set(CHANGES) for counter in counters)


def test_base_re_runs_the_home_on_them():
    assert set(CHANGES) <= set(live_registry.subscribable["base.bell.counters"])
    assert set(UNDOING) | {"printing.device.registered"} <= set(live_registry.subscribable["base.setup.status"])


# ── Two hubs ─────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=WAIT):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout)]


# Transactional: the notice leaves after a real COMMIT.
@pytest.mark.django_db(transaction=True)
def test_a_receipt_waiting_in_hub_b_re_runs_the_home_of_b_and_tells_a_nothing(listen):
    on_a, on_b = listen(A), listen(B)
    run("printing.printer.create", {"name": "Till", "kind": "network", "address": "10.0.0.1", "usage": "receipt"}, ctx_for(scope=B))
    run("printing.job.create", {"document_type": "receipt", "document": {"receipt_id": "T-1", "items": []}}, ctx_for(scope=B))

    notes = received(on_b)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    events = {event for _, payload in notes for event in payload["events"]}
    assert "base.bell.counters" in live_registry.affected(events)
    assert received(on_a, timeout=QUIET) == []
