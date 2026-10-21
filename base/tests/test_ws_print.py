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
import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.db import close_old_connections
from django.test import Client
from live.broker import broker
from live.context import OperationContext, Scope
from live.errors import AppInactive
from live.executor import executor
from live.meta import all_live_app_configs
from live.operations import get, registry

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

    def __init__(self, host: str = HUB_HOST, *, cookie: str | None = None, origin: str | None = "same", path="/ws/print", language: str | None = None):
        headers = [(b"host", host.encode())]
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
