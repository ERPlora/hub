"""Who prints through ``/ws/print``: the devices set up in printing (PRINTING-F18), and printing off."""

import pytest
from live.context import Scope
from live.errors import AppInactive
from live.operations import registry

from base import ws_print
from base.models import Membership
from base.tenancy.tests.business import A, HUB_DB_COMMITTED, in_business_a
from base.tests.print_socket import (
    db,
    enqueue,
    fresh_live,
    printer,
    ready_socket,
    refused_at_hello,
    run,
    session,
    set_up,
    sockets,
    status_of,
)

__all__ = ["fresh_live", "in_business_a", "session", "sockets"]
pytestmark = HUB_DB_COMMITTED


def registered_printers(device_id: str, scope: Scope = A) -> list[str] | None:
    """The printers of the registration of ``device_id`` (``printing.device.get``); none = not set up (or retired)."""
    device = run("printing.device.get", {"device": device_id}, scope).device
    return None if device is None else sorted(str(printer.id) for printer in device.printers)


async def test_hello_of_a_device_nobody_set_up_is_refused_at_once(sockets, session):
    """A device nobody set up in printing is no print host here, whatever printers it names: it is told at its
    hello (the old hub's ``print.host_not_registered``, a refusal it does not retry), not with a ``ready`` and then
    a ``printing.device_not_registered`` at every claim."""
    frame = await refused_at_hello(sockets, await db(session, "eva", role=Membership.Role.EMPLOYEE))

    assert frame["code"] == "print.host_not_registered", frame
    assert await db(registered_printers, "till-1") is None, "a refused hello set the device up"

    owners = await db(session, "ana")
    unchosen = sockets(cookie=owners)
    await unchosen.connect()
    no_printer = await unchosen.hello("till-1", [])
    assert no_printer["code"] == "print.host_not_registered"
    assert no_printer["message"] != frame["message"], "«not set up here» and «no printer chosen» are different facts"


async def test_hello_of_a_retired_device_is_refused_at_once_also_with_the_session_that_pairs(sockets, session):
    """A retired device prints nothing until somebody sets it up again: it is refused at its hello like one nobody
    set up, also with the session of whoever sets up the printers (which pairs a device new here), not with a
    ``ready`` and then a ``printing.device_not_registered`` at every claim."""
    cookie = await db(session, "ana")
    till = await db(printer)
    registration = await db(set_up, "till-1", till)
    await db(run, "printing.device.retire", {"device_id": registration})
    job = await db(enqueue, till)
    socket = sockets(cookie=cookie)
    await socket.connect()

    frame = await socket.hello("till-1", [till])

    assert frame["type"] == "error" and frame["code"] == "print.host_not_registered", frame
    assert await socket.closed() == 4403
    assert await db(status_of, job.id) == "pending"
    assert await db(registered_printers, "till-1") is None, "a refused hello set the retired device up again"
    stranger = sockets(cookie=await db(session, "eva", role=Membership.Role.EMPLOYEE))
    await stranger.connect()
    unregistered = await stranger.hello("kiosk-9", [till])
    assert frame["message"] == unregistered["message"], "retired is told as «not set up here», not «no printer chosen»"


@pytest.mark.parametrize("declares", ["nothing", "another printer"])
async def test_a_device_set_up_in_printing_prints_the_printers_of_its_registration(sockets, session, declares):
    """What a device reaches is its registration, not what its hello names: with anybody's session (an employee's)
    it prints for the active printers it was set up with, and a printer that is not on it is not its own."""
    cookie = await db(session, "eva", role=Membership.Role.EMPLOYEE)
    till = await db(printer, "Till")
    kitchen = await db(printer, "Kitchen", "kitchen")
    bar = await db(printer, "Bar", "bar")
    await db(set_up, "till-1", till, kitchen)
    queued = await db(enqueue, till)
    socket = sockets(cookie=cookie)
    await socket.connect()

    frame = await socket.hello("till-1", [] if declares == "nothing" else [bar])

    assert frame == {
        "type": "ready",
        "deviceId": "till-1",
        "roles": ["kitchen", "receipt"],
        "heartbeatSeconds": ws_print.HEARTBEAT_SECONDS,
    }
    await socket.send({"type": "claim", "role": "receipt"})
    assert (await socket.receive())["jobId"] == str(queued.id)
    await socket.send({"type": "claim", "role": "bar"})
    assert (await socket.receive())["code"] == "print.role_not_hosted"


async def test_the_session_of_whoever_sets_up_the_printers_pairs_the_device_by_printing(sockets, session):
    """printing's contract: with the session of whoever manages the printers, a device new here is set up (and one
    set up adds the printer it names) by printing from it, instead of being refused."""
    cookie = await db(session, "max", role=Membership.Role.MANAGER)
    till = await db(printer, "Till")
    kitchen = await db(printer, "Kitchen", "kitchen")
    receipt = await db(enqueue, till)
    order = await db(enqueue, kitchen, document_type="kitchen_order", document={"items": []})

    new = await ready_socket(sockets, cookie, [till])
    await new.send({"type": "claim", "role": "receipt"})
    assert (await new.receive())["jobId"] == str(receipt.id)
    assert await db(registered_printers, "till-1") == [till], "the first claim set the device up"
    await new.disconnect()

    again = sockets(cookie=cookie)
    await again.connect()
    ready = await again.hello("till-1", [kitchen])
    assert ready["type"] == "ready" and ready["roles"] == ["kitchen", "receipt"], "its registration and what it names"
    await again.send({"type": "claim", "role": "kitchen"})
    assert (await again.receive())["jobId"] == str(order.id)
    assert await db(registered_printers, "till-1") == sorted([till, kitchen]), "the printer it named was added"


@pytest.mark.parametrize("role", [Membership.Role.EMPLOYEE, Membership.Role.OWNER])
async def test_a_device_retired_while_connected_stops_at_its_next_beat(sockets, session, role):
    """Retiring a device is printing's decision: at its next beat it prints for nothing (``refreshed 0``, the old
    hub's «you host nothing here any more»), no job wakes it and a claim is refused, also with the session of
    whoever sets up the printers (which pairs a device new here, not a retired one)."""
    cookie = await db(session, "eva", role=role)
    till = await db(printer)
    registration = await db(set_up, "till-1", till)
    socket = await ready_socket(sockets, cookie, [till])
    await socket.send({"type": "beat"})
    assert (await socket.receive())["refreshed"] == 1

    await db(run, "printing.device.retire", {"device_id": registration})
    await socket.send({"type": "beat"})

    assert await socket.receive() == {"type": "beat", "refreshed": 0, "heartbeatSeconds": ws_print.HEARTBEAT_SECONDS}
    await db(enqueue, till)
    assert await socket.silent(), "a retired device was woken"
    await socket.send({"type": "claim", "role": "receipt"})
    assert (await socket.receive())["code"] == "print.role_not_hosted"


async def test_a_printer_of_the_registration_switched_off_is_not_reached(sockets, session):
    cookie = await db(session, "eva", role=Membership.Role.EMPLOYEE)
    till = await db(printer, "Till")
    kitchen = await db(printer, "Kitchen", "kitchen")
    await db(set_up, "till-1", till, kitchen)
    await db(run, "printing.printer.update", {"printer_id": kitchen, "is_active": False})
    socket = sockets(cookie=cookie)
    await socket.connect()

    assert (await socket.hello("till-1", []))["roles"] == ["receipt"]

    await db(run, "printing.printer.update", {"printer_id": till, "is_active": False})
    await socket.send({"type": "beat"})
    assert (await socket.receive())["refreshed"] == 0


@pytest.mark.parametrize("how", ["absent", "inactive"])
async def test_printing_off_closes_the_socket_with_app_inactive(sockets, session, monkeypatch, how):
    cookie = await db(session)
    till = await db(printer)
    if how == "absent":
        # The app is not there: none of its operations is registered (UnknownOperation).
        for name in [name for name in registry if name.startswith("printing.")]:
            monkeypatch.delitem(registry, name)
    else:
        # The operation refuses an app that is off (live's app check), whatever it is asked.
        real = registry["printing.printer.get"]

        def off(ctx, data):
            raise AppInactive("Printing is off.")

        monkeypatch.setitem(registry, "printing.printer.get", type(real)(**{**real.__dict__, "fn": off}))
    socket = sockets(cookie=cookie)
    await socket.connect()

    frame = await socket.hello("till-1", [till])

    assert frame["type"] == "error" and frame["code"] == "app_inactive"
    assert await socket.closed() == 4404


async def test_the_refusals_speak_the_language_of_the_device(sockets, session):
    cookie = await db(session)
    socket = sockets(cookie=cookie, language="es")
    await socket.connect()

    frame = await socket.hello("till-1", [])

    assert frame["code"] == "print.host_not_registered"
    assert frame["message"].startswith("Este dispositivo no llega a ninguna impresora activa")
    await socket.closed()

    employees = await db(session, "eva", role=Membership.Role.EMPLOYEE)
    unknown = sockets(cookie=employees, language="es")
    await unknown.connect()
    refused = await unknown.hello("till-1", [])
    assert refused["code"] == "print.host_not_registered"
    assert refused["message"].startswith("Este dispositivo no está dado de alta para imprimir")
    await unknown.closed()
