"""The device's presence through ``/ws/print``: the command its app declares is told at the device's hello and at
its beats, and checked at start."""

import logging

import pytest
from django.apps import apps as django_apps
from django.core import checks
from live.errors import AppInactive
from live.operations import Operation, registry
from ninja import Schema

from base import ws_print
from base.tenancy.tests.business import HUB_DB_COMMITTED, in_business_a
from base.tests.print_socket import db, enqueue, fresh_live, printer, ready_socket, run, session, sockets

__all__ = ["fresh_live", "in_business_a", "session", "sockets"]
pytestmark = HUB_DB_COMMITTED


#: The print hosts' presence (``print_presence``): printing declares its own under this name, which a test stands in for
#: with a command that records who it was told about.
SEEN = "printing.device.seen"


class SeenIn(Schema):
    device: str


class SeenOut(Schema):
    seen: bool


@pytest.fixture
def presence(monkeypatch):
    """Declares ``SEEN`` as the presence of printing's config and registers it as a command that records who it was
    told about, and by whom; ``fails`` makes it raise instead; ``declared=False`` takes printing's own declaration away.
    Returns the list of ``(device, actor)`` told."""
    told: list[tuple[str, str]] = []

    def declare(*, fails: BaseException | None = None, declared: bool = True) -> list[tuple[str, str]]:
        def seen(ctx, data):
            if fails is not None:
                raise fails
            told.append((data.device, ctx.actor.username))
            return {"seen": True}

        op = Operation(
            name=SEEN, kind="command", permission=None, input=SeenIn, output=SeenOut, expose_api=False, ai=None, fn=seen
        )
        monkeypatch.setitem(registry, SEEN, op)
        monkeypatch.setattr(django_apps.get_app_config("printing"), "print_presence", SEEN if declared else None)
        return told

    return declare


async def test_a_device_that_prints_tells_its_presence_at_hello_and_at_every_beat(sockets, session, presence, monkeypatch):
    """The old hub's heartbeat (``print_hosts::heartbeat``): connecting and every beat are news that the device is
    there, told to the command its app declares, with the device's id and as the device's user."""
    monkeypatch.setattr(ws_print.presence, "PRESENCE_SECONDS", 0)
    told = presence()
    cookie = await db(session)
    till = await db(printer)

    socket = await ready_socket(sockets, cookie, [till])
    assert told == [("till-1", "ana")]

    await socket.send({"type": "beat"})
    assert await socket.receive() == {"type": "beat", "refreshed": 1, "heartbeatSeconds": ws_print.presence.HEARTBEAT_SECONDS}
    await socket.send({"type": "beat"})
    await socket.receive()
    assert told == [("till-1", "ana")] * 3


async def test_without_a_declared_presence_the_socket_tells_nobody(sockets, session, presence, monkeypatch):
    monkeypatch.setattr(ws_print.presence, "PRESENCE_SECONDS", 0)
    told = presence(declared=False)
    cookie = await db(session)
    till = await db(printer)

    socket = await ready_socket(sockets, cookie, [till])
    await socket.send({"type": "beat"})

    assert await socket.receive() == {"type": "beat", "refreshed": 1, "heartbeatSeconds": ws_print.presence.HEARTBEAT_SECONDS}
    assert told == []


async def test_the_presence_is_told_once_per_interval_however_fast_the_device_beats(sockets, session, presence):
    """``HEARTBEAT_SECONDS`` × devices writes at the rate a device is told to beat; one that beats faster writes no
    more than once every ``PRESENCE_SECONDS``."""
    assert 0 < ws_print.presence.PRESENCE_SECONDS < ws_print.presence.HEARTBEAT_SECONDS
    told = presence()
    cookie = await db(session)
    till = await db(printer)

    socket = await ready_socket(sockets, cookie, [till])
    for _ in range(3):
        await socket.send({"type": "beat"})
        assert (await socket.receive())["refreshed"] == 1

    assert told == [("till-1", "ana")]


async def test_a_device_that_prints_for_nothing_tells_no_presence(sockets, session, presence, monkeypatch):
    monkeypatch.setattr(ws_print.presence, "PRESENCE_SECONDS", 0)
    told = presence()
    cookie = await db(session)
    till = await db(printer)
    socket = await ready_socket(sockets, cookie, [till])

    await db(run, "printing.printer.update", {"printer_id": till, "is_active": False})
    await socket.send({"type": "beat"})

    assert (await socket.receive())["refreshed"] == 0
    assert told == [("till-1", "ana")], "only its hello, when it still printed"


@pytest.mark.parametrize("failure", [RuntimeError("the disk is full"), AppInactive("Printing is off.")])
async def test_a_failed_presence_is_logged_and_the_socket_goes_on(sockets, session, presence, monkeypatch, caplog, failure):
    monkeypatch.setattr(ws_print.presence, "PRESENCE_SECONDS", 0)
    presence(fails=failure)
    cookie = await db(session)
    till = await db(printer)

    with caplog.at_level(logging.WARNING, logger="base.ws_print"):
        socket = await ready_socket(sockets, cookie, [till])
        await socket.send({"type": "beat"})
        assert await socket.receive() == {"type": "beat", "refreshed": 1, "heartbeatSeconds": ws_print.presence.HEARTBEAT_SECONDS}

    await db(enqueue, till)
    assert (await socket.receive())["type"] == "wake", "the socket still drains"
    assert [r for r in caplog.records if "presence" in r.getMessage() and "till-1" in r.getMessage()]


def presence_errors(monkeypatch, declarations: dict[str, object]) -> list[str]:
    """The ``base.E006`` the startup check says with ``declarations`` (app label → its ``print_presence``)."""
    for label, name in declarations.items():
        monkeypatch.setattr(django_apps.get_app_config(label), "print_presence", name, raising=False)
    return [m.msg for m in checks.run_checks(tags=["base"]) if m.id == "base.E006"]


def test_the_declared_presence_is_checked_at_start(monkeypatch, presence):
    presence(declared=False)
    assert presence_errors(monkeypatch, {"printing": SEEN}) == []

    assert len(presence_errors(monkeypatch, {"printing": "printing.device.nothing"})) == 1  # no such operation
    assert len(presence_errors(monkeypatch, {"printing": "printing.device.get"})) == 1  # a query, not a write
    assert len(presence_errors(monkeypatch, {"printing": "printing.printer.create"})) == 1  # takes no device
    assert len(presence_errors(monkeypatch, {"printing": 7})) == 1
    monkeypatch.setattr(django_apps.get_app_config("printing"), "print_presence", None)
    assert len(presence_errors(monkeypatch, {"sale": SEEN})) == 1  # another app's command


def test_one_app_at_most_declares_the_presence(monkeypatch, presence):
    presence(declared=False)
    other = Operation(**{**registry[SEEN].__dict__, "name": "sale.device.seen"})
    monkeypatch.setitem(registry, "sale.device.seen", other)

    errors = presence_errors(monkeypatch, {"printing": SEEN, "sale": "sale.device.seen"})

    assert len(errors) == 1 and "printing" in errors[0] and "sale" in errors[0]


def test_a_failed_presence_logs_under_the_channels_name():
    assert ws_print.presence.logger.name == "base.ws_print"
