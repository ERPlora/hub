"""The handshake of ``/ws/print``: it is answered (it was a 500) and ``hello`` → ``ready``; a host that is no hub, a
foreign origin or a business that does not serve closes the socket with its own code. The hub is the Host's first
label, the same scope the HTTP doors take."""

import pytest

from base import ws_print
from base.models import Hub
from base.tenancy.tests.business import A, HUB_DB_COMMITTED, in_business_a
from base.tests.print_socket import (
    HUB_HOST,
    OTHER_HOST,
    db,
    enqueue,
    fresh_live,
    printer,
    ready_socket,
    session,
    sockets,
)

__all__ = ["fresh_live", "in_business_a", "session", "sockets"]
pytestmark = HUB_DB_COMMITTED


async def test_the_handshake_is_accepted_and_hello_answers_ready(sockets, session):
    cookie = await db(session)
    till = await db(printer, "Till")
    kitchen = await db(printer, "Kitchen", "kitchen")
    socket = sockets(cookie=cookie)

    assert (await socket.connect())["type"] == "websocket.accept"
    frame = await socket.hello("till-1", [till, kitchen])

    assert frame == {
        "type": "ready",
        "deviceId": "till-1",
        "roles": ["kitchen", "receipt"],
        "heartbeatSeconds": ws_print.HEARTBEAT_SECONDS,
    }


async def test_a_foreign_origin_is_refused_before_the_handshake(sockets, session):
    cookie = await db(session)
    for origin in ("http://evil.example", f"http://{OTHER_HOST}", None):
        socket = sockets(cookie=cookie, origin=origin)
        first = await socket.connect()
        assert first["type"] == "websocket.close", f"{origin!r} was let in"
        await socket.disconnect()


@pytest.mark.parametrize(
    ("host", "status", "code"),
    [
        ("zz.localhost:8000", None, "not_found"),
        ("hub.localhost:8000", None, "not_found"),
        ("hubs.localhost:8000", None, "not_found"),
        ("gone.localhost:8000", Hub.Status.CANCELLED, "base.hub_gone"),
        ("soon.localhost:8000", Hub.Status.REQUESTED, "base.hub_preparing"),
    ],
)
async def test_a_host_that_is_no_hub_closes_the_socket_with_its_code(sockets, host, status, code):
    if status is not None:
        await db(Hub.objects.create, slug=host.split(".", 1)[0], status=status)
    expected = {"not_found": 4404, "base.hub_gone": 4410, "base.hub_preparing": 4503}[code]
    socket = sockets(host)

    assert (await socket.connect())["type"] == "websocket.accept"
    frame = await socket.receive()
    assert frame["type"] == "error" and frame["code"] == code
    assert await socket.closed() == expected


async def test_a_suspended_business_closes_the_socket_with_its_402(sockets):
    # The SaaS's photo says suspended for an unpaid invoice (base.middleware): the print host hears why and is closed.
    await db(Hub.objects.filter(slug=A.key).update, state={"status": "suspended"})
    socket = sockets(HUB_HOST)

    assert (await socket.connect())["type"] == "websocket.accept"
    frame = await socket.receive()
    assert frame["type"] == "error" and frame["code"] == "base.hub_suspended"
    assert await socket.closed() == 4402


@pytest.mark.parametrize(
    ("change", "code", "close"),
    [
        ({"state": {"status": "suspended"}}, "base.hub_suspended", 4402),
        ({"status": Hub.Status.CANCELLED}, "base.hub_gone", 4410),
        ({"status": Hub.Status.REQUESTED}, "base.hub_preparing", 4503),
    ],
)
async def test_a_business_that_stops_serving_while_the_socket_is_open_closes_it_at_the_next_beat(
    sockets, session, change, code, close
):
    # The handshake heard the gate; an open socket hears it again before every frame (base.operations' refresh).
    cookie = await db(session)
    till = await db(printer)
    socket = await ready_socket(sockets, cookie, [till])
    await db(Hub.objects.filter(slug=A.key).update, **change)

    await socket.send({"type": "beat"})

    frame = await socket.receive()
    assert frame["type"] == "error" and frame["code"] == code
    assert await socket.closed() == close


async def test_the_wake_of_a_business_suspended_while_the_socket_is_open_closes_it(sockets, session):
    """A job queued after the suspension wakes the device's live stream, which ends (``bye``) because the hub no
    longer serves: the socket closes with the gate's 402 instead of following the stream again and again."""
    cookie = await db(session)
    till = await db(printer)
    socket = await ready_socket(sockets, cookie, [till])
    await db(Hub.objects.filter(slug=A.key).update, state={"status": "suspended"})

    await db(enqueue, till)

    frame = await socket.receive()
    assert frame["type"] == "error" and frame["code"] == "base.hub_suspended"
    assert await socket.closed() == 4402
