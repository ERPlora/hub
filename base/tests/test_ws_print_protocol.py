"""The refusals of the ``/ws/print`` protocol itself: a frame before ``hello``, no ``hello`` at all, a frame too
large and a malformed one."""

import uuid

import pytest

from base import ws_print
from base.tenancy.tests.business import HUB_DB_COMMITTED, in_business_a
from base.tests.print_socket import db, fresh_live, printer, session, sockets

__all__ = ["fresh_live", "in_business_a", "session", "sockets"]
pytestmark = HUB_DB_COMMITTED


@pytest.mark.parametrize(
    "frame",
    [
        {"type": "claim", "role": "receipt"},
        {"type": "done", "jobId": str(uuid.uuid7())},
        {"type": "failed", "jobId": str(uuid.uuid7()), "error": "x"},
        {"type": "beat"},
    ],
)
async def test_no_frame_works_before_hello(sockets, session, frame):
    cookie = await db(session)
    socket = sockets(cookie=cookie)
    await socket.connect()

    await socket.send(frame)

    refused = await socket.receive()
    assert refused["code"] == "print.not_ready"
    assert await socket.closed() == 4400


async def test_a_socket_that_never_says_hello_is_closed(sockets, monkeypatch):
    monkeypatch.setattr(ws_print.protocol, "HELLO_TIMEOUT_SECONDS", 0.2)
    socket = sockets()
    await socket.connect()

    frame = await socket.receive()

    assert frame["code"] == "print.not_ready"
    assert await socket.closed() == 4400


async def test_an_oversized_frame_is_refused_before_it_is_parsed(sockets):
    socket = sockets()
    await socket.connect()

    await socket.send("x" * (ws_print.protocol.MAX_FRAME_BYTES + 1))

    frame = await socket.receive()
    assert frame["code"] == "print.frame_too_large"
    assert await socket.closed() == 4413


async def test_a_malformed_frame_answers_invalid_payload_and_the_socket_stays(sockets, session):
    cookie = await db(session)
    till = await db(printer)
    socket = sockets(cookie=cookie)
    await socket.connect()

    for bad in ("not json", "[1, 2]", {"type": "please-print-everything"}, b"\x00\x01", {"type": "hello", "deviceId": "t", "printers": "all"}):
        await socket.send(bad)
        frame = await socket.receive()
        assert frame["type"] == "error" and frame["code"] == "invalid_payload", bad

    assert (await socket.hello("till-1", [till]))["type"] == "ready", "the socket is still usable"


def test_the_socket_logs_under_the_channels_name():
    assert ws_print.protocol.logger.name == "base.ws_print"
