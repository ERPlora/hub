"""Who may drain through ``/ws/print``: a session of this hub that is still open, from an address that has not tried
too many, for a device that reaches an active printer of this hub."""

import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import login
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory

from base.models import Membership
from base.tenancy.tests.business import A, B, HUB_DB_COMMITTED, in_business_a
from base.tests.print_socket import db, fresh_live, printer, ready_socket, refused_at_hello, run, session, sockets

__all__ = ["fresh_live", "in_business_a", "session", "sockets"]
pytestmark = HUB_DB_COMMITTED


async def test_hello_without_a_session_is_refused_and_the_socket_closed(sockets):
    till = await db(printer)
    none = sockets()
    assert (await none.connect())["type"] == "websocket.accept"
    refused = await none.hello("till-1", [till])
    assert refused["type"] == "error" and refused["code"] == "unauthenticated"
    assert await none.closed() == 4401

    bogus = sockets(cookie="not-a-session-of-this-hub")
    await bogus.connect()
    invalid = await bogus.hello("till-1", [till])
    assert invalid["code"] == "unauthenticated"
    assert invalid["message"] != refused["message"], "«you sent none» and «yours is not valid» are different facts"
    assert await bogus.closed() == 4401


async def test_a_session_opened_on_another_hub_is_no_session_here_even_for_a_member_of_both(sockets, django_user_model, hub_b):
    """The session notes the host it was opened on (``base.session_host.SessionHostMiddleware``); the print
    socket reads the session itself, so it applies the same rule: B's session on A's socket is 4401."""

    def opened_on_b() -> str:
        user = django_user_model.objects.create_user(username="bea", password="pw")
        for host in (A.key, B.key):
            Membership.objects.create(user=user, host=host, role=Membership.Role.OWNER)
        request = RequestFactory().get("/auth/callback")
        request.session, request.hub = SessionStore(), hub_b
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        request.session.save()
        return request.session.session_key

    cookie = await db(opened_on_b)
    till = await db(printer)
    socket = sockets(cookie=cookie)
    await socket.connect()

    frame = await socket.hello("till-1", [till])

    assert frame["type"] == "error" and frame["code"] == "unauthenticated"
    assert await socket.closed() == 4401


async def test_a_session_of_another_hub_drains_nothing_here(sockets, session):
    frame = await refused_at_hello(sockets, await db(session, "bea", host=B.key))

    assert frame["code"] == "permission_denied"


async def test_a_session_that_ends_closes_the_socket_at_its_next_frame(sockets, session):
    cookie = await db(session)
    till = await db(printer)
    socket = await ready_socket(sockets, cookie, [till])

    await sync_to_async(SessionStore(cookie).delete)()
    await socket.send({"type": "beat"})

    frame = await socket.receive()
    assert frame["type"] == "error" and frame["code"] == "unauthenticated"
    assert await socket.closed() == 4401


# Attempts: past 10 sessions refused from an address in 5 minutes, its next refused one is closed 4429 until the window
# of the first one ends; a valid session always prints (the kitchen's printer is never locked out by a tablet next to it)


REFUSED_SESSIONS = 10


async def refused_sessions(sockets, times: int = REFUSED_SESSIONS, **socket) -> None:
    """``times`` sockets whose ``hello`` carries a session that is not valid here (each one closed 4401)."""
    for _ in range(times):
        guess = sockets(cookie="not-a-session-of-this-hub", **socket)
        await guess.connect()
        assert (await guess.hello("till-1", []))["code"] == "unauthenticated"
        assert await guess.closed() == 4401


async def test_past_ten_refused_sessions_the_next_refused_one_is_closed_4429(sockets):
    await refused_sessions(sockets)

    socket = sockets(cookie="not-a-session-of-this-hub", language="es")
    assert (await socket.connect())["type"] == "websocket.accept"
    frame = await socket.hello("till-1", [])

    assert frame["type"] == "error" and frame["code"] == "base.rate_limited"
    assert frame["message"] == "Demasiados intentos fallidos de entrar desde esta conexión. Vuelve a intentarlo en 5 minutos."
    assert await socket.closed() == 4429


async def test_a_valid_session_prints_while_the_address_is_past_the_limit(sockets, session):
    # One tablet with an expired session reconnects over and over: the kitchen's printer, same public address, keeps
    # printing with its own session.
    cookie = await db(session)
    till = await db(printer)
    await refused_sessions(sockets)
    tablet = sockets(cookie="not-a-session-of-this-hub")
    await tablet.connect()
    assert (await tablet.hello("till-1", []))["code"] == "base.rate_limited"
    assert await tablet.closed() == 4429

    kitchen = sockets(cookie=cookie)
    await kitchen.connect()
    assert (await kitchen.hello("till-1", [till]))["type"] == "ready"


async def test_a_hello_without_any_session_is_not_counted(sockets, session):
    # Nothing was tried: a print host that has not signed in yet keeps asking without counting against its neighbours.
    for _ in range(REFUSED_SESSIONS + 2):
        none = sockets()
        await none.connect()
        assert (await none.hello("till-1", []))["code"] == "unauthenticated"
        assert await none.closed() == 4401
    await refused_sessions(sockets, REFUSED_SESSIONS)


@pytest.mark.parametrize(
    ("caller", "same", "neighbour"),
    [("203.0.113.7", "203.0.113.7", "203.0.113.8"), ("2001:db8:1:2::7", "2001:db8:1:2:ffff::1", "2001:db8:1:3::7")],
)
async def test_the_refused_sessions_count_per_address_as_the_proxies_saw_it(sockets, settings, caller, same, neighbour):
    settings.TRUSTED_PROXY_HOPS = 1
    await refused_sessions(sockets, forwarded_for=caller)

    blocked = sockets(cookie="not-a-session-of-this-hub", forwarded_for=same)
    await blocked.connect()
    assert (await blocked.hello("till-1", []))["code"] == "base.rate_limited"
    assert await blocked.closed() == 4429
    await refused_sessions(sockets, 1, forwarded_for=neighbour)


async def test_hello_without_a_device_is_refused(sockets, session):
    cookie = await db(session)
    till = await db(printer)
    socket = sockets(cookie=cookie)
    await socket.connect()

    frame = await socket.hello("   ", [till])

    assert frame["code"] == "print.device_required"
    assert await socket.closed() == 4400


async def test_a_device_that_reaches_no_active_printer_of_this_hub_is_refused(sockets, session):
    cookie = await db(session)
    retired = await db(printer, "Old")
    await db(run, "printing.printer.update", {"printer_id": retired, "is_active": False})
    for printers in ([], [retired], [str(uuid.uuid7())]):
        socket = sockets(cookie=cookie)
        await socket.connect()
        frame = await socket.hello("till-1", printers)
        assert frame["code"] == "print.host_not_registered", printers
        assert await socket.closed() == 4403
        await socket.disconnect()
