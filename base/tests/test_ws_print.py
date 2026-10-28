"""``/ws/print``, the print host's channel (PLAN-HUB §5; the old hub's ``print_ws.rs``, hub#343): ``base.ws_print``.

Driven through ``config.asgi.application`` the way Daphne drives it, on the real database and the real printing
operations, without mocks: the handshake is answered (it was a 500), ``hello`` → ``ready``, ``claim`` hands the
oldest job of the device's printers, ``done``/``failed`` close it, a job queued after the COMMIT wakes the device
of its hub and not another hub's, and every refusal has its own code: a host that is no hub, a foreign origin,
no session, a session that ended, printing off, a frame before ``hello``, a frame too large.

Phase 1 has one database for every hub (PLAN §16): the hub is the Host's first label, the same scope the HTTP
doors take, and the wake travels on that scope's channel only.
"""

import asyncio
import dataclasses
import json
import logging
import uuid
from collections import defaultdict
from collections.abc import Callable

import pytest
from asgiref.sync import sync_to_async
from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth import login
from django.contrib.sessions.backends.db import SessionStore
from django.core import checks
from django.db import close_old_connections
from django.test import Client, RequestFactory
from live.broker import broker
from live.context import OperationContext, Scope
from live.errors import AppInactive
from live.executor import executor
from live.meta import all_live_app_configs
from live.operations import Operation, get, registry
from ninja import Schema

from apps.printing.models import PrintJob
from base import ws_print
from base.models import Hub, Membership
from config.asgi import application

pytestmark = pytest.mark.django_db(transaction=True)

HUB_HOST = "a.localhost:8000"
OTHER_HOST = "b.localhost:8000"
A = Scope("host", "a")
B = Scope("host", "b")
#: How long a test waits for a frame that should come; one that must not come is waited for this long too.
WAIT = 5.0
QUIET = 1.0
RECEIPT = {"business_name": "Salón Ana", "receipt_id": "T-000123", "items": [], "total": 18.0}


class Socket:
    """A WebSocket client of ``config.asgi.application``, sending what Daphne sends for a browser."""

    def __init__(
        self,
        host: str = HUB_HOST,
        *,
        cookie: str | None = None,
        origin: str | None = "same",
        path="/ws/print",
        language: str | None = None,
        forwarded_for: str | None = None,
    ):
        headers = [(b"host", host.encode())]
        if forwarded_for is not None:
            headers.append((b"x-forwarded-for", forwarded_for.encode()))
        if language is not None:
            headers.append((b"accept-language", language.encode()))
        if origin == "same":
            origin = f"http://{host}"
        if origin is not None:
            headers.append((b"origin", origin.encode()))
        if cookie is not None:
            headers.append((b"cookie", f"{settings.SESSION_COOKIE_NAME}={cookie}".encode()))
        self.scope = {
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", 8000),
            "subprotocols": [],
        }
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.outbox: asyncio.Queue = asyncio.Queue()
        self.task: asyncio.Task | None = None
        self.close_code: int | None = None

    async def connect(self) -> dict:
        """Open the socket; the application's first answer (``websocket.accept`` or ``websocket.close``)."""
        self.task = asyncio.create_task(application(self.scope, self.inbox.get, self.outbox.put))
        await self.inbox.put({"type": "websocket.connect"})
        return await self._next()

    async def send(self, frame: dict | str | bytes) -> None:
        if isinstance(frame, bytes):
            await self.inbox.put({"type": "websocket.receive", "bytes": frame})
        else:
            text = frame if isinstance(frame, str) else json.dumps(frame)
            await self.inbox.put({"type": "websocket.receive", "text": text})

    async def receive(self, timeout: float = WAIT) -> dict:
        """The next frame the hub sends; fails if the socket is closed instead."""
        message = await self._next(timeout)
        assert message["type"] == "websocket.send", f"expected a frame, got {message}"
        return json.loads(message["text"])

    async def closed(self, timeout: float = WAIT) -> int:
        """Wait for the hub to close the socket; its close code."""
        message = await self._next(timeout)
        assert message["type"] == "websocket.close", f"expected the socket closed, got {message}"
        self.close_code = message.get("code", 1000)
        return self.close_code

    async def silent(self, timeout: float = QUIET) -> bool:
        """Whether the hub sends nothing for ``timeout`` seconds."""
        try:
            message = await asyncio.wait_for(self.outbox.get(), timeout)
        except TimeoutError:
            return True
        await self.outbox.put(message)
        return False

    async def hello(self, device_id: str = "till-1", printers: list | None = None, **more) -> dict:
        await self.send({"type": "hello", "session": "", "deviceId": device_id, "printers": printers or [], **more})
        return await self.receive()

    async def disconnect(self) -> None:
        if self.task is None:
            return
        if not self.task.done():
            await self.inbox.put({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(self.task, WAIT)

    async def _next(self, timeout: float = WAIT) -> dict:
        getter = asyncio.ensure_future(self.outbox.get())
        done, _ = await asyncio.wait({getter, self.task}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        if getter in done:
            return getter.result()
        getter.cancel()
        if self.task in done:
            self.task.result()  # raises what the application raised
            raise AssertionError("the application ended without answering")
        raise TimeoutError(f"nothing from the hub in {timeout} s")


@pytest.fixture(autouse=True)
async def fresh_live():
    """The live broker and executor are the process's: each test (each event loop) starts and ends them clean."""
    await broker.reset()
    executor.reset()
    yield
    await broker.reset()
    executor.reset()


@pytest.fixture
async def sockets():
    """Sockets opened by a test; those still open are disconnected after it (a failed test included)."""
    opened: list[Socket] = []

    def make(*args, **kwargs) -> Socket:
        socket = Socket(*args, **kwargs)
        opened.append(socket)
        return socket

    yield make
    for socket in opened:
        await socket.disconnect()


@pytest.fixture
def handled(monkeypatch):
    """The wake results each socket handled, in order, by its device: the ids of the waiting jobs each one shows. A
    test waits for the result that follows a change and then reads what the socket sent, instead of waiting for a
    silence a loaded runner may not keep (the live re-run is grouped 150 ms, hub#135)."""
    results: defaultdict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
    handle = ws_print.PrintSocket._on_stream

    async def recorded(self, item):
        try:
            return await handle(self, item)
        finally:
            event, data = ws_print._decode_frame(item)
            if event == "result":
                results[self.device.device_id].put_nowait({row["id"] for row in data["data"]["rows"]})

    monkeypatch.setattr(ws_print.PrintSocket, "_on_stream", recorded)
    return results


async def handled_until(results: asyncio.Queue, check: Callable[[set[str]], bool]) -> None:
    """Wait until the socket handled a wake result whose waiting jobs pass ``check``."""
    while not check(await asyncio.wait_for(results.get(), WAIT)):
        pass


@pytest.fixture
def session(django_user_model):
    """The Hub's session cookie of a new user with ``role`` on ``host`` (``None``: no membership)."""

    def make(username: str = "ana", *, host: str | None = "a", role: str = Membership.Role.OWNER) -> str:
        user = django_user_model.objects.create_user(username=username, password="pw")
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        client = Client()
        client.force_login(user)
        return client.cookies[settings.SESSION_COOKIE_NAME].value

    return make


def owner(scope: Scope = A) -> OperationContext:
    permissions = frozenset(p for config in all_live_app_configs() for p in config.permissions)
    return OperationContext(scope=scope, actor="tester", permissions=permissions, language="en")


def run(name: str, data: dict, scope: Scope = A):
    op = get(name)
    return op(owner(scope), op.input.model_validate(data))


def printer(name: str = "Till", usage: str = "receipt", scope: Scope = A) -> str:
    row = run(
        "printing.printer.create",
        {"name": name, "kind": "network", "address": "192.168.1.50", "usage": usage},
        scope,
    )
    return str(row.id)


def enqueue(printer_id: str | None = None, scope: Scope = A, **more):
    """Queues a receipt through ``printing.job.create`` (on ``printer_id``, if given); the job queued."""
    data = {"document_type": "receipt", "document": RECEIPT, **more}
    if printer_id is not None:
        data["printer"] = printer_id
    return run("printing.job.create", data, scope).job


def status_of(job_id) -> str:
    return PrintJob.objects.get(pk=job_id).status


def set_up(device_id: str, *printers: str, scope: Scope = A) -> str:
    """Sets the device ``device_id`` up to print on ``printers`` the way printing does it, from the device itself
    (``printing.device.register``; the SPA sends its id in ``X-Device-Id``); its registration id."""
    op = get("printing.device.register")
    request = RequestFactory().post("/api/printing/devices", HTTP_X_DEVICE_ID=device_id)
    ctx = dataclasses.replace(owner(scope), request=request)
    return str(op(ctx, op.input.model_validate({"name": "Till", "printers": list(printers)})).id)


def registered_printers(device_id: str, scope: Scope = A) -> list[str] | None:
    """The printers of the registration of ``device_id`` (``printing.device.get``); none = not set up (or retired)."""
    device = run("printing.device.get", {"device": device_id}, scope).device
    return None if device is None else sorted(str(printer.id) for printer in device.printers)


async def db(fn, *args, **kwargs):
    """Run the synchronous ``fn`` off the event loop, releasing its database connection after it (a pooled
    connection left checked out in asgiref's thread would outlive the test database)."""

    def call():
        try:
            return fn(*args, **kwargs)
        finally:
            close_old_connections()

    return await sync_to_async(call)()


async def ready_socket(sockets, cookie: str, printers: list[str], host: str = HUB_HOST, device_id: str = "till-1"):
    socket = sockets(host, cookie=cookie)
    assert (await socket.connect())["type"] == "websocket.accept"
    frame = await socket.hello(device_id, printers)
    assert frame["type"] == "ready", frame
    return socket


# ── The handshake ─────────────────────────────────────────────────────────────────────────────────


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
    for origin in ("http://evil.example", "http://b.localhost:8000", None):
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
    await db(Hub.objects.create, slug="late", status=Hub.Status.READY, state={"status": "suspended"})
    socket = sockets("late.localhost:8000")

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
    await db(Hub.objects.filter(slug="a").update, **change)

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
    await db(Hub.objects.filter(slug="a").update, state={"status": "suspended"})

    await db(enqueue, till)

    frame = await socket.receive()
    assert frame["type"] == "error" and frame["code"] == "base.hub_suspended"
    assert await socket.closed() == 4402

# ── Who may drain ─────────────────────────────────────────────────────────────────────────────────


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


async def test_a_session_opened_on_another_hub_is_no_session_here_even_for_a_member_of_both(sockets, django_user_model):
    """Phase 2, S1: the session notes the host it was opened on (``base.middleware.SessionHostMiddleware``); the print
    socket reads the session itself, so it applies the same rule: B's session on A's socket is 4401."""

    def opened_on_b() -> str:
        user = django_user_model.objects.create_user(username="bea", password="pw")
        for host in ("a", "b"):
            Membership.objects.create(user=user, host=host, role=Membership.Role.OWNER)
        request = RequestFactory().get("/auth/callback")
        request.session, request.hub = SessionStore(), Hub.objects.get(slug="b")
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
    cookie = await db(session, "bea", host="b")
    till = await db(printer)
    job = await db(enqueue, till)
    socket = sockets(cookie=cookie)
    await socket.connect()

    frame = await socket.hello("till-1", [till])

    assert frame["type"] == "error" and frame["code"] == "permission_denied"
    assert await socket.closed() == 4403
    assert await db(status_of, job.id) == "pending"


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


# ── Who prints: the devices set up in printing (PRINTING-F18) ─────────────────────────────────────


async def test_hello_of_a_device_nobody_set_up_is_refused_at_once(sockets, session):
    """A device nobody set up in printing is no print host here, whatever printers it names: it is told at its
    hello (the old hub's ``print.host_not_registered``, a refusal it does not retry), not with a ``ready`` and then
    a ``printing.device_not_registered`` at every claim."""
    cookie = await db(session, "eva", role=Membership.Role.EMPLOYEE)
    till = await db(printer)
    job = await db(enqueue, till)
    socket = sockets(cookie=cookie)
    await socket.connect()

    frame = await socket.hello("till-1", [till])

    assert frame["type"] == "error" and frame["code"] == "print.host_not_registered", frame
    assert await socket.closed() == 4403
    assert await db(status_of, job.id) == "pending"
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
        # Phase 2: the operation refuses an app that is off (live's app check), whatever it is asked.
        real = registry["printing.printer.get"]

        def off(ctx, data):
            raise AppInactive("Printing is off.")

        monkeypatch.setitem(registry, "printing.printer.get", type(real)(**{**real.__dict__, "fn": off}))
    socket = sockets(cookie=cookie)
    await socket.connect()

    frame = await socket.hello("till-1", [till])

    assert frame["type"] == "error" and frame["code"] == "app_inactive"
    assert await socket.closed() == 4404


# ── The protocol's own refusals ───────────────────────────────────────────────────────────────────


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
    monkeypatch.setattr(ws_print, "HELLO_TIMEOUT_SECONDS", 0.2)
    socket = sockets()
    await socket.connect()

    frame = await socket.receive()

    assert frame["code"] == "print.not_ready"
    assert await socket.closed() == 4400


async def test_an_oversized_frame_is_refused_before_it_is_parsed(sockets):
    socket = sockets()
    await socket.connect()

    await socket.send("x" * (ws_print.MAX_FRAME_BYTES + 1))

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


# ── Draining ──────────────────────────────────────────────────────────────────────────────────────


async def test_claim_hands_the_oldest_job_of_its_printers_and_done_closes_it(sockets, session):
    cookie = await db(session)
    till = await db(printer, "Till")
    other = await db(printer, "Front desk")
    first = await db(enqueue, till)
    elsewhere = await db(enqueue, other)
    second = await db(enqueue, till)
    socket = await ready_socket(sockets, cookie, [till])

    await socket.send({"type": "claim", "role": "receipt"})
    job = await socket.receive()

    assert job["type"] == "job"
    assert job["jobId"] == str(first.id)
    assert job["role"] == "receipt"
    assert job["documentType"] == "receipt"
    assert job["document"]["receipt_id"] == "T-000123"
    assert job["format"] == "receipt"
    assert job["attempts"] == 1
    assert job["kind"] == "document"
    assert job["printerId"] == till
    assert job["target"] == "network:192.168.1.50:9100"
    assert job["copies"] == 1
    assert {"paperWidth", "copyDocument", "openDrawer", "html"} <= job.keys()

    await socket.send({"type": "done", "jobId": job["jobId"]})
    assert await socket.receive() == {"type": "ack", "jobId": str(first.id), "confirmed": True}
    assert await db(status_of, first.id) == "done"

    await socket.send({"type": "claim", "role": "receipt"})
    assert (await socket.receive())["jobId"] == str(second.id)
    await socket.send({"type": "done", "jobId": str(second.id)})
    await socket.receive()
    await socket.send({"type": "claim", "role": "receipt"})
    assert await socket.receive() == {"type": "idle", "role": "receipt"}
    assert await db(status_of, elsewhere.id) == "pending", "a printer this device does not reach"


async def test_a_reported_failure_puts_the_job_back_in_the_queue(sockets, session):
    cookie = await db(session)
    till = await db(printer)
    queued = await db(enqueue, till)
    socket = await ready_socket(sockets, cookie, [till])
    await socket.send({"type": "claim", "role": "receipt"})
    await socket.receive()

    await socket.send({"type": "failed", "jobId": str(queued.id), "error": "out of paper"})

    assert await socket.receive() == {"type": "ack", "jobId": str(queued.id), "requeued": True}
    assert await db(status_of, queued.id) == "pending"


async def test_a_confirmation_resent_after_a_reconnect_is_taken(sockets, session):
    cookie = await db(session)
    till = await db(printer)
    queued = await db(enqueue, till)
    before = await ready_socket(sockets, cookie, [till])
    await before.send({"type": "claim", "role": "receipt"})
    await before.receive()
    await before.disconnect()

    after = await ready_socket(sockets, cookie, [till])
    await after.send({"type": "done", "jobId": str(queued.id)})

    assert await after.receive() == {"type": "ack", "jobId": str(queued.id), "confirmed": True}
    assert await db(status_of, queued.id) == "done"


async def test_another_devices_job_is_not_confirmed_by_this_one(sockets, session):
    cookie = await db(session)
    till = await db(printer)
    queued = await db(enqueue, till)
    holder = await ready_socket(sockets, cookie, [till], device_id="till-1")
    await holder.send({"type": "claim", "role": "receipt"})
    await holder.receive()

    stranger = await ready_socket(sockets, cookie, [till], device_id="till-2")
    await stranger.send({"type": "done", "jobId": str(queued.id)})

    assert await stranger.receive() == {"type": "ack", "jobId": str(queued.id), "confirmed": False}
    assert await db(status_of, queued.id) == "sent"


async def test_a_role_the_device_does_not_print_is_refused_and_the_socket_stays(sockets, session):
    cookie = await db(session)
    till = await db(printer)
    await db(enqueue, usage="kitchen", document_type="kitchen_order", document={"items": []})
    socket = await ready_socket(sockets, cookie, [till])

    await socket.send({"type": "claim", "role": "kitchen"})

    frame = await socket.receive()
    assert frame["code"] == "print.role_not_hosted"
    await socket.send({"type": "claim", "role": "receipt"})
    assert (await socket.receive())["type"] == "idle", "it is still the receipt's printing device"


async def test_a_beat_counts_the_printers_the_device_still_reaches(sockets, session):
    cookie = await db(session)
    till = await db(printer, "Till")
    kitchen = await db(printer, "Kitchen", "kitchen")
    socket = await ready_socket(sockets, cookie, [till, kitchen])

    await socket.send({"type": "beat"})
    assert await socket.receive() == {"type": "beat", "refreshed": 2, "heartbeatSeconds": ws_print.HEARTBEAT_SECONDS}

    for printer_id in (till, kitchen):
        await db(run, "printing.printer.update", {"printer_id": printer_id, "is_active": False})
    await socket.send({"type": "beat"})
    assert (await socket.receive())["refreshed"] == 0


# ── The device's presence (FIX-HUB-BASE-PRINT-BELL-IGNORES-DEVICE-PRESENCE) ──────────────────────────────


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
    monkeypatch.setattr(ws_print, "PRESENCE_SECONDS", 0)
    told = presence()
    cookie = await db(session)
    till = await db(printer)

    socket = await ready_socket(sockets, cookie, [till])
    assert told == [("till-1", "ana")]

    await socket.send({"type": "beat"})
    assert await socket.receive() == {"type": "beat", "refreshed": 1, "heartbeatSeconds": ws_print.HEARTBEAT_SECONDS}
    await socket.send({"type": "beat"})
    await socket.receive()
    assert told == [("till-1", "ana")] * 3


async def test_without_a_declared_presence_the_socket_tells_nobody(sockets, session, presence, monkeypatch):
    monkeypatch.setattr(ws_print, "PRESENCE_SECONDS", 0)
    told = presence(declared=False)
    cookie = await db(session)
    till = await db(printer)

    socket = await ready_socket(sockets, cookie, [till])
    await socket.send({"type": "beat"})

    assert await socket.receive() == {"type": "beat", "refreshed": 1, "heartbeatSeconds": ws_print.HEARTBEAT_SECONDS}
    assert told == []


async def test_the_presence_is_told_once_per_interval_however_fast_the_device_beats(sockets, session, presence):
    """``HEARTBEAT_SECONDS`` × devices writes at the rate a device is told to beat; one that beats faster writes no
    more than once every ``PRESENCE_SECONDS``."""
    assert 0 < ws_print.PRESENCE_SECONDS < ws_print.HEARTBEAT_SECONDS
    told = presence()
    cookie = await db(session)
    till = await db(printer)

    socket = await ready_socket(sockets, cookie, [till])
    for _ in range(3):
        await socket.send({"type": "beat"})
        assert (await socket.receive())["refreshed"] == 1

    assert told == [("till-1", "ana")]


async def test_a_device_that_prints_for_nothing_tells_no_presence(sockets, session, presence, monkeypatch):
    monkeypatch.setattr(ws_print, "PRESENCE_SECONDS", 0)
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
    monkeypatch.setattr(ws_print, "PRESENCE_SECONDS", 0)
    presence(fails=failure)
    cookie = await db(session)
    till = await db(printer)

    with caplog.at_level(logging.WARNING, logger="base.ws_print"):
        socket = await ready_socket(sockets, cookie, [till])
        await socket.send({"type": "beat"})
        assert await socket.receive() == {"type": "beat", "refreshed": 1, "heartbeatSeconds": ws_print.HEARTBEAT_SECONDS}

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


# ── The nudge ─────────────────────────────────────────────────────────────────────────────────────


async def test_a_job_queued_after_the_commit_wakes_the_device_of_its_hub_and_no_other(sockets, session):
    cookie_a = await db(session, "ana", host="a")
    cookie_b = await db(session, "bea", host="b")
    till_a = await db(printer, "Till A", scope=A)
    till_b = await db(printer, "Till B", scope=B)
    in_a = await ready_socket(sockets, cookie_a, [till_a], HUB_HOST)
    in_b = await ready_socket(sockets, cookie_b, [till_b], OTHER_HOST, device_id="till-b")

    await db(enqueue, till_a, scope=A)

    assert await in_a.receive() == {"type": "wake", "role": "receipt"}
    assert await in_b.silent(), "a job of hub A woke a device of hub B"

    await db(enqueue, till_b, scope=B)
    assert await in_b.receive() == {"type": "wake", "role": "receipt"}
    assert await in_a.silent(), "a job of hub B woke a device of hub A"


async def test_a_claim_that_empties_the_queue_wakes_nobody(sockets, session):
    """The wake says a job is waiting (the old hub's: «a job was just queued for a role you host»); the queue
    changing because this device took its last job is no wake, or every job would end in a claim → idle."""
    cookie = await db(session)
    till = await db(printer)
    queued = await db(enqueue, till)
    socket = await ready_socket(sockets, cookie, [till])

    await socket.send({"type": "claim", "role": "receipt"})
    assert (await socket.receive())["jobId"] == str(queued.id)
    assert await socket.silent(QUIET), "a wake with nothing waiting (the claim emptied the queue)"

    await socket.send({"type": "done", "jobId": str(queued.id)})
    assert (await socket.receive())["type"] == "ack"
    assert await socket.silent(QUIET), "a wake with nothing waiting (after the confirmation)"

    await db(enqueue, till)
    assert await socket.receive() == {"type": "wake", "role": "receipt"}, "a job queued still wakes the device"


async def test_its_own_claim_does_not_wake_the_device_while_other_jobs_wait(sockets, session, handled):
    """A claim of this device changes the queue while other jobs of the role still wait (here one of a printer it
    does not reach): that queues nothing, so it is no wake. The live re-run is grouped, and such a wake came late,
    between a later claim and its ``idle`` (hub#135, ``test_claim_hands_the_oldest_job…``)."""
    cookie = await db(session)
    till = await db(printer, "Till")
    other = await db(printer, "Front desk")
    first = await db(enqueue, till)
    await db(enqueue, other)
    second = await db(enqueue, till)
    socket = await ready_socket(sockets, cookie, [till])

    await socket.send({"type": "claim", "role": "receipt"})
    assert (await socket.receive())["jobId"] == str(first.id)
    await handled_until(handled["till-1"], lambda waiting: str(first.id) not in waiting)
    assert socket.outbox.empty(), "a wake for this device's own claim"

    await socket.send({"type": "done", "jobId": str(first.id)})
    assert (await socket.receive())["type"] == "ack"
    await socket.send({"type": "claim", "role": "receipt"})
    assert (await socket.receive())["jobId"] == str(second.id)
    await handled_until(handled["till-1"], lambda waiting: str(second.id) not in waiting)
    assert socket.outbox.empty(), "a wake for this device's own claim"

    await db(enqueue, till)
    assert await socket.receive() == {"type": "wake", "role": "receipt"}, "a job queued still wakes the device"


async def test_a_job_queued_behind_a_backlog_of_its_function_still_wakes_the_device(sockets, session):
    """The wake watches the newest waiting jobs of the function: a job just queued is among them however many jobs of
    a printer nobody drains wait before it."""
    cookie = await db(session)
    till = await db(printer, "Till")
    unattended = await db(printer, "Front desk")
    for _ in range(ws_print.WAKE_WINDOW):
        await db(enqueue, unattended)
    socket = await ready_socket(sockets, cookie, [till])

    await db(enqueue, till)

    assert await socket.receive() == {"type": "wake", "role": "receipt"}


async def test_the_job_it_sent_back_does_not_wake_the_device_until_somebody_retries_it(sockets, session, handled):
    """A device that could not print a job sends it back and stops pulling that role, or an empty roll would burn
    the job's five hand-outs in a second (the old print host): the job waiting again is no news to it. Somebody
    retrying it is (they changed the roll)."""
    cookie = await db(session)
    till = await db(printer)
    queued = await db(enqueue, till)
    socket = await ready_socket(sockets, cookie, [till])
    await socket.send({"type": "claim", "role": "receipt"})
    assert (await socket.receive())["jobId"] == str(queued.id)
    await handled_until(handled["till-1"], lambda waiting: str(queued.id) not in waiting)

    await socket.send({"type": "failed", "jobId": str(queued.id), "error": "out of paper"})
    assert (await socket.receive())["requeued"] is True
    await handled_until(handled["till-1"], lambda waiting: str(queued.id) in waiting)
    assert socket.outbox.empty(), "a wake for the job this device sent back itself"

    await db(run, "printing.job.retry", {"job_id": str(queued.id)})
    assert await socket.receive() == {"type": "wake", "role": "receipt"}, "a retry is news"


async def test_a_job_another_device_sent_back_wakes_this_one(sockets, session, handled):
    """Sent back, the job waits for any device that prints it (the old print host's «the hub puts the ticket back
    for another host»): the other device is woken, the one that failed it is not."""
    cookie = await db(session)
    till = await db(printer)
    queued = await db(enqueue, till)
    holder = await ready_socket(sockets, cookie, [till], device_id="till-1")
    other = await ready_socket(sockets, cookie, [till], device_id="till-2")
    await holder.send({"type": "claim", "role": "receipt"})
    assert (await holder.receive())["jobId"] == str(queued.id)
    for device in ("till-1", "till-2"):
        await handled_until(handled[device], lambda waiting: str(queued.id) not in waiting)

    await holder.send({"type": "failed", "jobId": str(queued.id), "error": "out of paper"})
    assert (await holder.receive())["requeued"] is True

    assert await other.receive() == {"type": "wake", "role": "receipt"}
    await handled_until(handled["till-1"], lambda waiting: str(queued.id) in waiting)
    assert holder.outbox.empty(), "a wake for the job this device sent back itself"


async def test_the_wake_never_carries_the_document(sockets, session):
    cookie = await db(session)
    till = await db(printer)
    socket = await ready_socket(sockets, cookie, [till])

    await db(enqueue, till)

    assert set(await socket.receive()) == {"type", "role"}


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
