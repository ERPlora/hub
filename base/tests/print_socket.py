"""A client of ``/ws/print``, the print host's channel (the old hub's ``print_ws.rs``): ``base.ws_print``, and the
printing helpers its tests share.

The socket is driven through ``config.asgi.application`` the way Daphne drives it, on the real database and the real
printing operations, without mocks.
"""

import asyncio
import dataclasses
import json

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections
from django.test import Client, RequestFactory
from live.broker import broker
from live.context import OperationContext, Scope
from live.executor import executor
from live.meta import all_live_app_configs
from live.operations import get

from apps.printing.models import PrintJob
from base.models import Membership
from base.tenancy.tests.business import A, B
from base.tests.businesses import without_a_business
from config.asgi import application

HUB_HOST = f"{A.key}.localhost:8000"
OTHER_HOST = f"{B.key}.localhost:8000"
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
        self.task = without_a_business(application(self.scope, self.inbox.get, self.outbox.put))
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
async def sockets(live_runs_ended):
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

    def make(username: str = "ana", *, host: str | None = A.key, role: str = Membership.Role.OWNER) -> str:
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


async def refused_at_hello(sockets, cookie: str) -> dict:
    """The frame that refuses the hello of the till's device with ``cookie`` while a job waits: the socket is closed
    4403 and the job still waits."""
    till = await db(printer)
    job = await db(enqueue, till)
    socket = sockets(cookie=cookie)
    await socket.connect()
    frame = await socket.hello("till-1", [till])
    assert frame["type"] == "error", frame
    assert await socket.closed() == 4403
    assert await db(status_of, job.id) == "pending"
    return frame
