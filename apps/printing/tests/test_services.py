"""What the tests of the printing app's writes share: the events in the outbox, the device's calls to the queue and
the devices the business sets up. Each module of ``services/`` has its own tests, in ``test_services_<module>.py``."""

import dataclasses
import datetime as dt

from django.test import RequestFactory
from django.utils import timezone
from live.models import OutboxEvent

from apps.printing.models import PrintDevice, Printer, PrintJob
from apps.printing.tests.conftest import HUB_DB, RECEIPT, ctx_for, run

pytestmark = HUB_DB

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


STAMPED = {**RECEIPT, "locale": "en", "decimals": 2}


# ── PRINTING-F18 Only a device the business set up prints ─
# A session with «print» must not take the jobs of any printer by naming it, nor confirm or fail them by naming the
# device that had them (shown in the queue). The device is the one that prints: whoever sets up printers registers it
# with the printers it reaches; then only it, with any session that prints, takes, confirms or fails their jobs.

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


def seen_at(device_id: str = TILL_ID):
    return PrintDevice.objects.get(key=PrintDevice.key_of(device_id)).last_seen_at
