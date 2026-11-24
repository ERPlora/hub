"""The devices that print (PRINTING-F18): set up, renamed and retired from any device, and seen while they are there."""

import json

import pytest
from django.utils import timezone
from live.errors import InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.printing.models import PrintDevice, PrintJob
from apps.printing.tests.conftest import HUB_DB, ctx_for, enqueue, printer, run
from apps.printing.tests.test_services import (
    EMPLOYEE,
    MANAGER,
    SPARE_ID,
    TILL_ID,
    answer,
    events,
    on_device,
    register,
    seen_at,
    take,
)

pytestmark = HUB_DB


def test_a_manager_sets_up_this_device_and_an_employee_on_it_prints_its_printers():
    till = printer("Till")
    kitchen = printer("Kitchen", usage="kitchen", address="10.0.0.2")
    device = register(till, kitchen, name="Counter till")
    assert (device.name, sorted(p.name for p in device.printers), device.this_device) == (
        "Counter till",
        ["Kitchen", "Till"],
        True,
    )
    # Set up from the device in hand, it is there (seen); asking for a job is news again.
    assert device.registered_by == "tester" and device.last_seen_at is not None
    assert events("printing.device.registered") == [{"id": str(device.id)}]
    queued = enqueue().job
    taken = take(till)
    assert taken.id == queued.id
    stored = PrintJob.objects.get(pk=queued.id)
    assert (stored.device, stored.print_device_id) == ("Counter till", device.id)
    assert PrintDevice.objects.get(pk=device.id).last_seen_at > device.last_seen_at
    ack = answer("printing.job.complete", queued.id)
    assert (ack.confirmed, ack.job.status, ack.job.device) == (True, "done", "Counter till")


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
    # An employee who read the till's id in the queue could print, confirm and fail as the till.
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


# ── The device's presence (base's /ws/print declares it ``print_presence``) ──


def test_a_device_that_says_it_is_there_is_seen_now_with_an_employees_session():
    # The socket runs it as the device's user: whoever is signed in at the till prints, an employee too (with only
    # printing.print, never printing.manage_settings, its presence would never land).
    register(printer("Till"))
    PrintDevice.objects.update(last_seen_at=None)
    before = timezone.now()
    out = run("printing.device.seen", {"device": TILL_ID}, ctx=ctx_for(EMPLOYEE))
    assert out.seen is True
    assert before <= seen_at() <= timezone.now()


def test_a_retired_device_or_one_never_set_up_here_is_not_seen():
    device = register(printer("Till"))
    run("printing.device.retire", {"device_id": str(device.id)}, ctx=ctx_for(MANAGER))
    PrintDevice.objects.update(last_seen_at=None)
    assert run("printing.device.seen", {"device": TILL_ID}, ctx=ctx_for(EMPLOYEE)).seen is False
    assert seen_at() is None
    assert run("printing.device.seen", {"device": SPARE_ID}, ctx=ctx_for(EMPLOYEE)).seen is False
    assert not PrintDevice.objects.filter(key=PrintDevice.key_of(SPARE_ID)).exists(), "being there sets nothing up"


def test_whoever_cannot_print_is_refused_and_nothing_is_seen():
    register(printer("Till"))
    PrintDevice.objects.update(last_seen_at=None)
    with pytest.raises(PermissionDenied):
        run("printing.device.seen", {"device": TILL_ID}, ctx=ctx_for("nobody"))
    assert seen_at() is None


def test_being_seen_records_no_event_so_a_beat_wakes_no_screen():
    # Every device beats every 30 s: an event would re-run the printers, the devices, the queue and the Home of every
    # client each time. The bell reads the clock instead (bell_refresh_every).
    register(printer("Till"))
    events = OutboxEvent.objects.count()
    for _ in range(3):
        run("printing.device.seen", {"device": TILL_ID}, ctx=ctx_for(EMPLOYEE))
    assert OutboxEvent.objects.count() == events


def test_setting_a_device_up_from_it_is_news_that_it_is_there():
    # A heartbeat or a re-registration both count as news: set up from the device in hand, it is there.
    before = timezone.now()
    device = register(printer("Till"))
    assert before <= seen_at() <= timezone.now()
    assert device.last_seen_at == seen_at()


def test_the_channel_reads_the_printers_of_the_device_that_says_hello():
    # base's /ws/print has the device's id in its hello, not in a header: printing.device.get by that id.
    till = printer("Till")
    printer("Kitchen", usage="kitchen", address="10.0.0.2")
    register(till)
    found = run("printing.device.get", {"device": TILL_ID}, ctx=ctx_for(EMPLOYEE)).device
    assert (found.name, [(p.id, p.usage) for p in found.printers], found.this_device) == ("Till", [(till.id, "receipt")], True)
    assert run("printing.device.get", {"device": "never-set-up"}, ctx=ctx_for(EMPLOYEE)).device is None


def test_the_channel_tells_a_retired_device_from_one_never_set_up():
    # A device new here is paired by the session of whoever sets up the printers; a retired one is not: retiring it
    # was a decision, and only setting it up again brings it back. The channel reads which one it is at the hello.
    till = printer("Till")
    device = register(till)
    never = run("printing.device.get", {"device": "never-set-up"}, ctx=ctx_for(MANAGER))
    assert (never.device, never.retired) == (None, False)
    assert run("printing.device.get", {"device": TILL_ID}, ctx=ctx_for(MANAGER)).retired is False
    run("printing.device.retire", {"device_id": str(device.id)}, ctx=ctx_for(MANAGER))
    for role in (EMPLOYEE, MANAGER):
        gone = run("printing.device.get", {"device": TILL_ID}, ctx=ctx_for(role))
        assert (gone.device, gone.retired) == (None, True), role
    register(till)
    back = run("printing.device.get", {"device": TILL_ID}, ctx=ctx_for(EMPLOYEE))
    assert (back.device.id, back.retired) == (device.id, False)
