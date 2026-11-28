"""A device that prints whose session was closed because someone entered on another device and the business's plan
covers no more devices at a time (BASE-F57). Printing notes which of the hub's devices (the browser or app the person
entered on, its ``hub_device`` cookie) each print device prints with, so the devices list and the queue's summary say
that real cause instead of «it is off: switch it on»."""

import dataclasses
import datetime as dt

from django.test import RequestFactory
from django.utils import timezone

from apps.printing.models import PrintDevice
from apps.printing.tests.conftest import HUB_DB, ctx_for, printer, queued_ago, run
from base import access
from base.models.access import TrustedDevice

pytestmark = HUB_DB

#: The tablet's own id, as the SPA sends it in X-Device-Id.
TABLET = "7d4b1e2a-93c5-4f60-8a1e-2b6c9d0e5f37"


def hub_device() -> tuple[TrustedDevice, str]:
    """A device of the hub somebody entered on with their account: the row and the token of its cookie."""
    token = access.new_device_token()
    device = TrustedDevice.objects.create(token_digest=access.token_digest(token), last_entry_at=timezone.now())
    return device, token


def on_the_tablet(token: str | None, role: str = "hub_admin"):
    """The context of a request from the tablet: its X-Device-Id and, when given, its ``hub_device`` cookie."""
    request = RequestFactory().post("/api/printing/devices", HTTP_X_DEVICE_ID=TABLET)
    if token is not None:
        request.COOKIES[access.DEVICE_COOKIE] = token
    return dataclasses.replace(ctx_for(role), request=request)


def set_up_tablet(*printers, token: str | None):
    return run("printing.device.register", {"name": "Bar tablet", "printers": [p.id for p in printers]}, on_the_tablet(token))


def signed_out_by_the_plan(device: TrustedDevice) -> None:
    """What base does to the tablet's device when someone enters on another one past the plan's cap."""
    TrustedDevice.objects.filter(pk=device.pk).update(
        ended_reason=TrustedDevice.EndedReason.DEVICE_LIMIT, ended_at=timezone.now()
    )


def entered_again(device: TrustedDevice) -> None:
    """What base does when somebody enters on that device again: it forgets why its sessions ended."""
    TrustedDevice.objects.filter(pk=device.pk).update(ended_reason="", ended_at=None)


def went_quiet(minutes: int = 5) -> None:
    PrintDevice.objects.update(last_seen_at=timezone.now() - dt.timedelta(minutes=minutes))


def tablet() -> PrintDevice:
    return PrintDevice.objects.get(key=PrintDevice.key_of(TABLET))


def test_setting_the_tablet_up_notes_the_hub_device_it_prints_with():
    device, token = hub_device()
    set_up_tablet(printer("Till"), token=token)
    assert tablet().hub_device == device.pk


def test_its_hello_and_its_beats_note_the_hub_device_it_prints_with_now():
    till = printer("Till")
    first, first_token = hub_device()
    set_up_tablet(till, token=first_token)
    # The app was reinstalled: a new cookie, a new device of the hub, the same tablet printing.
    second, second_token = hub_device()
    run("printing.device.seen", {"device": TABLET}, ctx=on_the_tablet(second_token, role="hub_employee"))
    assert tablet().hub_device == second.pk != first.pk


def test_asking_for_a_job_notes_it_too():
    till = printer("Till")
    set_up_tablet(till, token=None)
    device, token = hub_device()
    run("printing.job.claim", {"printers": [str(till.id)], "device": TABLET}, ctx=on_the_tablet(token, role="hub_employee"))
    assert tablet().hub_device == device.pk


def test_the_devices_list_says_the_tablet_was_signed_out_by_the_plan_until_somebody_enters_on_it_again():
    device, token = hub_device()
    set_up_tablet(printer("Till"), token=token)

    def signed_out() -> tuple[bool, bool]:
        [row] = run("printing.device.list", {}, ctx_for("hub_employee")).rows
        return row.signed_out, run("printing.device.detail", {"device_id": str(row.id)}).signed_out

    assert signed_out() == (False, False)
    signed_out_by_the_plan(device)
    assert signed_out() == (True, True)
    entered_again(device)
    assert signed_out() == (False, False)


def test_the_summary_says_the_receipts_wait_for_a_device_signed_out_by_the_plan_not_for_one_switched_off():
    device, token = hub_device()
    set_up_tablet(printer("Till"), token=token)
    printer("Kitchen", usage="kitchen", address="10.0.0.2")
    went_quiet()
    queued_ago(65)

    def by_usage() -> dict:
        return {row.usage: (row.stalled, row.signed_out) for row in run("printing.job.summary").usages}

    # Switched off: the card says so, as before.
    assert by_usage()["receipt"] == (1, False)
    signed_out_by_the_plan(device)
    assert by_usage() == {"receipt": (1, True), "kitchen": (0, False), "bar": (0, False), "label": (0, False)}
    entered_again(device)
    assert by_usage()["receipt"] == (1, False)


def test_a_device_with_no_hub_device_behind_it_or_whose_hub_device_was_removed_is_never_signed_out_by_the_plan():
    till = printer("Till")
    # Set up without the cookie (an API key, a print host of an integrator): no device of the hub to lose.
    set_up_tablet(till, token=None)
    assert tablet().hub_device is None
    went_quiet()
    queued_ago(65)
    assert run("printing.job.summary").usages[0].signed_out is False
    device, token = hub_device()
    run("printing.device.seen", {"device": TABLET}, ctx=on_the_tablet(token))
    signed_out_by_the_plan(device)
    TrustedDevice.objects.filter(pk=device.pk).delete()
    [row] = run("printing.device.list", {}).rows
    assert row.signed_out is False
    assert run("printing.job.summary").usages[0].signed_out is False


def test_a_retired_tablet_signed_out_by_the_plan_says_nothing_about_the_receipts_it_printed():
    device, token = hub_device()
    row = set_up_tablet(printer("Till"), token=token)
    signed_out_by_the_plan(device)
    assert run("printing.job.summary").usages[0].signed_out is True
    # Retired, it keeps its printers by name, but it is no longer the one the receipts wait for.
    run("printing.device.retire", {"device_id": str(row.id)})
    assert run("printing.job.summary").usages[0].signed_out is False
