"""The device's presence through base's /ws/print, for real (FIX-HUB-PRINTING-BELL-SILENT-WITH-DEVICE-OFF; the old hub's
``print_hosts::heartbeat``): Printing declares ``printing.device.seen`` as ``print_presence``, and the socket runs it at
the device's hello and at its beats as the device's user, with the permissions that user really has. Whoever is signed
in at the till prints, an employee too: its till is seen, and the bell stops ringing for it.

Driven through ``config.asgi.application`` with base's own socket client (``base/tests/test_ws_print.py``).
"""

import datetime as dt
import logging

import pytest
from django.utils import timezone

from apps.printing.models import PrintDevice
from base import ws_print
from base.models import Membership
from base.tests.test_ws_print import (  # noqa: F401 (fresh_live, session and sockets are fixtures)
    db,
    fresh_live,
    printer,
    ready_socket,
    session,
    set_up,
    sockets,
)

pytestmark = pytest.mark.django_db(transaction=True)

DEVICE = "till-1"


def seen_at(device_id: str = DEVICE):
    return PrintDevice.objects.get(key=PrintDevice.key_of(device_id)).last_seen_at


def went_quiet(minutes: int = 10):
    """The device last gave news ``minutes`` ago; that instant."""
    instant = timezone.now() - dt.timedelta(minutes=minutes)
    PrintDevice.objects.update(last_seen_at=instant)
    return instant


async def test_an_employees_till_is_seen_at_its_hello_and_at_every_beat(sockets, session, monkeypatch, caplog):
    monkeypatch.setattr(ws_print, "PRESENCE_SECONDS", 0)
    cookie = await db(session, "eva", role=Membership.Role.EMPLOYEE)
    till = await db(printer)
    await db(set_up, DEVICE, till)
    quiet = await db(went_quiet)

    with caplog.at_level(logging.WARNING, logger="base.ws_print"):
        socket = await ready_socket(sockets, cookie, [till])
        assert await db(seen_at) > quiet, "its hello is news"

        quiet = await db(went_quiet)
        await socket.send({"type": "beat"})
        assert (await socket.receive())["refreshed"] == 1
        assert await db(seen_at) > quiet, "so is every beat"

    assert not [record for record in caplog.records if "presence" in record.getMessage()], "the presence landed"


async def test_a_till_seen_by_the_socket_quiets_the_bell(sockets, session):
    from apps.printing.tests.conftest import ctx_for, run

    cookie = await db(session, "eva", role=Membership.Role.EMPLOYEE)
    till = await db(printer)
    await db(set_up, DEVICE, till)
    await db(went_quiet)

    def queued_a_minute_ago():
        from apps.printing.models import PrintJob

        run("printing.job.create", {"document_type": "receipt", "document": {"receipt_id": "T-1", "items": []}})
        PrintJob.objects.update(created_at=timezone.now() - dt.timedelta(seconds=65))

    def count():
        return run("printing.device.coverage", {"usage": "receipt"}, ctx=ctx_for("hub_employee")).count

    await db(queued_a_minute_ago)
    assert await db(count) == 1, "the till is off: nobody is printing the receipt"
    await ready_socket(sockets, cookie, [till])
    assert await db(count) == 0, "the till is back"
