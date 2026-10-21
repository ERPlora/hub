"""``/ws/print``: the print host's channel, the Hub's only WebSocket (PLAN-HUB §5; the old hub's
``crates/server/src/print_ws.rs``, hub#343).

The device next to a printer (the ERPlora app) opens ``wss://<hub>/ws/print`` and drains the print queue of the
printers it reaches: it is told when a job arrives (``wake``), takes it (``claim`` → ``job``), prints it and says
how it went (``done``/``failed`` → ``ack``). The queue is printing's: this channel only calls its operations by
name (``printing.device.get``, ``printing.printer.get``, ``printing.job.claim``, ``printing.job.complete``,
``printing.job.fail``, ``printing.job.list``) with the context of the device's session, the same functions,
permissions and scope as the HTTP doors (``/api/printing/jobs/claim``…), and touches no model itself.

The wire is the old hub's, its messages and fields unchanged (the native app and its print host are published,
working-rules §12)::

    client                                                      hub
      {"type":"hello","session":…,"deviceId":…,"printers":[…]}  →
                     ← {"type":"ready","deviceId":…,"roles":[…],"heartbeatSeconds":30}
      {"type":"claim","role":"kitchen"}                         →
                     ← {"type":"job","jobId":…,"role":…,"documentType":…,"document":{…},"format":…,"attempts":1,…}
                     ← {"type":"idle","role":"kitchen"}       nothing waiting
      {"type":"done","jobId":…}                                 →  ← {"type":"ack","jobId":…,"confirmed":true}
      {"type":"failed","jobId":…,"error":…}                     →  ← {"type":"ack","jobId":…,"requeued":true}
      {"type":"beat"}                                           →  ← {"type":"beat","refreshed":2,"heartbeatSeconds":30}
                     ← {"type":"wake","role":"kitchen"}       a job is waiting for a role it prints
                     ← {"type":"error","code":…,"message":…}

What the new Hub changed, and nothing else:

- **The credential is the Hub's session cookie of the handshake**, the one every HTTP door takes (the Hub's
  login is the SaaS's and its session an HttpOnly cookie, PLAN-SAAS §3.1): ``hello.session`` is accepted and not
  read. It is checked at ``hello`` and again at every frame, so a session that ended (a logout) closes the socket
  at the device's next beat at the latest.
- **Who prints is printing's** (``PrintDevice``, the old hub's ``_print_host``, PRINTING-F18): ``hello`` reads the
  device's registration by its ``deviceId`` (``printing.device.get``), and the printers it reaches are the active
  ones of that registration, as in the old hub (``ready``'s roles come from the registry, never from the client). A
  device not set up here (or retired) is refused at its ``hello``. ``printers`` (ids it knows from
  ``printing.printer.list``) is what the session of whoever sets up the printers adds: with it, a device new here
  or a printer not on its registration is taken, and its first claim of that role pairs them (printing's
  WORKBOOK, «Lo que hace ``base`` con ``/ws/print``»); with anybody else's, it changes nothing. The ``roles`` of
  ``ready`` are the functions of those printers (``receipt``, ``kitchen``, ``bar``, ``label``: the old stations),
  and ``claim`` takes the oldest job of that role's printers. A ``beat`` reads the registration again: a device
  retired, or whose printers were switched off, answers ``refreshed: 0`` and prints for nothing.
- **``job`` keeps every old field** and adds the rest of printing's hand-out, camelCased (``kind``,
  ``printerId``, ``target``, ``paperWidth``, ``copyDocument``, ``copies``, ``openDrawer``, ``html``…), which
  the app's print commands take.

Refusals, each with its own code. The fatal ones close the socket with ``4000 +`` their HTTP status; the rest
answer ``error`` and the socket stays:

==============================  =====  ==========================================================================
code                            close  when
==============================  =====  ==========================================================================
``not_found``                   4404   the Host is no hub's (the platform host included)
``base.hub_gone``               4410   the hub ended
``base.hub_preparing``          4503   the hub is still being prepared
``base.hub_suspended``          4402   the business is suspended for an unpaid invoice
``print.not_ready``             4400   a frame before ``hello``, or no ``hello`` within 15 s
``print.frame_too_large``       4413   a frame over 8 KiB (before anything is parsed)
``unauthenticated``             4401   no session, one that is not valid here, or one that ended
``print.device_required``       4400   ``hello`` without ``deviceId``
``print.host_not_registered``   4403   ``hello`` of a device not set up in printing (or retired), or that reaches
                                       no active printer of this hub
``permission_denied``           4403   the user may not print here (a session of another hub's member)
``app_inactive``                4404   printing is not on in this hub
``invalid_payload``             —      a frame that is not JSON, not of this protocol, or with a bad field
``print.role_not_hosted``       —      ``claim`` of a role this device does not print
``internal_error``              —      the hub failed; a job handed out comes back when its lease runs out
==============================  =====  ==========================================================================

A ``done`` or ``failed`` the queue does not take (another device has the job, or it is gone) is a plain
``confirmed: false`` / ``requeued: false``, as in the old hub: the device forgets it. A ``done`` re-sent after a
reconnect is taken from the device that held the job, whatever hand-out it was.

**Tenancy** (phase 1, PLAN §16): the hub is the Host's first label, checked against the registry by the gate the
HTTP doors pass (``base.middleware.HubHostRequiredMiddleware``), and every operation runs in its scope with the
session's user. The gate is heard again before every frame and every wake (the context's refresh,
``base.operations.HostClosed``): a hub that stops serving while the socket is open closes it with the same code; phase 2 swaps the context builder for ``use_hub`` and this module does not change. The ``Origin``
must be the hub's own (cross-site WebSocket hijacking): anything else is refused at the handshake (Daphne answers
it 403).

**The wake** opens no ``LISTEN`` of its own: the socket keeps a stream of the process's live broker (the single
``LISTEN`` on the control database that ``/api/live`` uses) with one subscription per role to that role's first
waiting job (``printing.job.list``). A job queued, retried or sent back to the queue changes it after the COMMIT,
and a changed result that still shows a waiting job becomes a ``wake`` for that role: as the device's user (its permissions re-read every time),
on its hub's channel only, and never carrying the document, which travels only in the answer to ``claim``.
"""

import asyncio
import io
import json
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any
from urllib.parse import urlsplit

import pydantic
from asgiref.sync import ThreadSensitiveContext, sync_to_async
from django.conf import settings
from django.contrib import auth
from django.core.exceptions import NON_FIELD_ERRORS, SuspiciousOperation
from django.core.handlers.asgi import ASGIRequest
from django.db import close_old_connections
from django.http import Http404, HttpRequest
from django.utils import translation
from django.utils.translation import gettext, gettext_noop
from live.broker import broker
from live.context import OperationContext, get_builder
from live.errors import NotFound, OperationError
from live.executor import BYE_FRAME, Stream, Subscription, executor
from live.operations import UnknownOperation, get

from base.middleware import HubHostRequiredMiddleware
from base.operations import HostClosed

logger = logging.getLogger(__name__)

PATH = "/ws/print"
#: Longest client→server frame accepted. These frames carry ids and a role, never a document, and the socket
#: reads them before anybody has proved who they are (the old hub's ``MAX_FRAME_BYTES``).
MAX_FRAME_BYTES = 8 * 1024
#: Seconds a socket may stay silent before saying ``hello``: one that never does is no print host.
HELLO_TIMEOUT_SECONDS = 15.0
#: How often a connected device beats, told in ``ready`` and ``beat`` (the old hub's ``HEARTBEAT_SECONDS``).
HEARTBEAT_SECONDS = 30

DEVICE_GET = "printing.device.get"
PRINTER_GET = "printing.printer.get"
JOB_CLAIM = "printing.job.claim"
JOB_COMPLETE = "printing.job.complete"
JOB_FAIL = "printing.job.fail"
JOB_LIST = "printing.job.list"
#: The queue's answer when the job is another device's now: a plain no, never an error (as a job it no longer has).
NOT_YOURS = "printing.job_not_yours"
#: Whoever sets up the printers pairs a device by printing from it: its claim sets up a device new here, or adds the
#: printer it names, instead of refusing it (printing's WORKBOOK, PRINTING-F18).
PAIRS = "printing.manage_settings"
#: Refusals no retry fixes: the socket is closed after them.
FATAL_OPERATION_CODES = frozenset({"permission_denied", "app_inactive", "app_entitlement_blocked"})
#: Close code of a refusal before the handshake: Daphne answers the handshake 403.
HANDSHAKE_REFUSED = 4403
#: Close code when the channel itself fails.
INTERNAL_ERROR_CLOSE = 1011

_CAMEL = re.compile(r"_([a-z])")


class Refusal(Exception):
    """A refusal sent as an ``error`` frame; a fatal one closes the socket with ``4000 + status``."""

    def __init__(self, code: str, message: str, *, status: int, fatal: bool = True, fields: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.status, self.fatal, self.fields = code, message, status, fatal, fields

    def frame(self) -> dict:
        frame = {"type": "error", "code": self.code, "message": self.message}
        if self.fields:
            frame["fields"] = self.fields
        return frame


@dataclass(eq=False)
class Device:
    """The device behind a socket that said ``hello``."""

    ctx: OperationContext
    device_id: str
    #: The printer ids its ``hello`` named: what a session that pairs adds to its registration.
    declared: list[str]
    #: The active printers it prints for, re-read with its registration on every beat: id → function.
    printers: dict[str, str]
    #: Hand-out of each job given on this socket (``failed`` must name the hand-out it answers).
    attempts: dict[str, int] = field(default_factory=dict)
    stream: Stream | None = None

    @property
    def roles(self) -> list[str]:
        return sorted(set(self.printers.values()))


async def print_socket(scope: dict, receive: Callable, send: Callable) -> None:
    """The ASGI application of ``/ws/print`` (``config.asgi`` routes the WebSocket scope here)."""
    await PrintSocket(scope, receive, send).run()


class PrintSocket:
    """One connection of a print host."""

    def __init__(self, scope: dict, receive: Callable, send: Callable) -> None:
        self.scope, self.receive, self.send = scope, receive, send
        self.request: HttpRequest | None = None
        self.language = settings.LANGUAGE_CODE
        self.device: Device | None = None

    async def run(self) -> None:
        if (await self.receive())["type"] != "websocket.connect":
            return
        try:
            admitted = await self._sync(self._admit)
            if admitted is False:
                await self.send({"type": "websocket.close", "code": HANDSHAKE_REFUSED})
                return
            await self.send({"type": "websocket.accept"})
            if isinstance(admitted, Refusal):
                await self._refuse(admitted)
                return
            await self._serve()
        except Exception:
            logger.exception("The print channel failed (%s).", self.scope.get("path"))
            await self.send({"type": "websocket.close", "code": INTERNAL_ERROR_CLOSE})
        finally:
            self._unfollow()

    # ── The handshake ─────────────────────────────────────────────────────────────────────────────

    def _admit(self) -> Refusal | bool:
        """``False``: refuse the handshake (a foreign origin, a host Django refuses); a ``Refusal``: accept it and
        say why it ends at once (no hub); ``True``: a hub's own page is calling."""
        request = _http_request(self.scope)
        try:
            if not _same_origin(request):
                return False
        except SuspiciousOperation:
            return False
        self.language = translation.get_language_from_request(request)
        with translation.override(self.language):
            try:
                answer = HubHostRequiredMiddleware(_no_view).process_request(request)
            except Http404:
                return Refusal("not_found", gettext("Not found"), status=404)
            if getattr(request, "platform_host", False):
                return Refusal("not_found", gettext("Not found"), status=404)
            if answer is not None:
                error = json.loads(answer.content)["error"]
                return Refusal(error["code"], error["message"], status=answer.status_code)
        request.LANGUAGE_CODE = self.language
        self.request = request
        return True

    # ── The loop ──────────────────────────────────────────────────────────────────────────────────

    async def _serve(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + HELLO_TIMEOUT_SECONDS
        receiving = asyncio.ensure_future(self.receive())
        waking: asyncio.Future | None = None
        waking_stream: Stream | None = None
        try:
            while True:
                stream = self.device.stream if self.device else None
                if waking is not None and waking_stream is not stream:
                    waking.cancel()
                    waking = None
                if waking is None and stream is not None:
                    waking, waking_stream = asyncio.ensure_future(stream.queue.get()), stream
                timeout = None if self.device else max(0.0, deadline - loop.time())
                waits = {receiving} if waking is None else {receiving, waking}
                done, _ = await asyncio.wait(waits, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    message = self._t(gettext_noop("No hello within %(seconds)s seconds.")) % {"seconds": HELLO_TIMEOUT_SECONDS}
                    await self._refuse(Refusal("print.not_ready", message, status=400))
                    return
                if waking in done:
                    item, waking = waking.result(), None
                    if not await self._on_stream(item):
                        return
                if receiving in done:
                    message = receiving.result()
                    if message["type"] == "websocket.disconnect":
                        return
                    if message["type"] == "websocket.receive" and not await self._on_message(message):
                        return
                    receiving = asyncio.ensure_future(self.receive())
        finally:
            receiving.cancel()
            if waking is not None:
                waking.cancel()

    async def _on_message(self, message: dict) -> bool:
        """Handle one client frame; ``False`` once the socket is closed."""
        try:
            frame = self._parse(message)
            kind = frame["type"]
            if self.device is None and kind != "hello":
                raise Refusal(
                    "print.not_ready", self._t(gettext_noop("Say hello with a deviceId before draining.")), status=400
                )
            if kind != "hello":
                # Every frame, not only the hello: a session that ended (a logout) ends the socket here.
                await self._sync(self._authenticate)
            handler = {
                "hello": self._hello,
                "claim": self._claim,
                "done": self._done,
                "failed": self._failed,
                "beat": self._beat,
            }[kind]
            reply = await handler(frame)
        except Refusal as refusal:
            return await self._refuse(refusal)
        except OperationError as exc:
            return await self._refuse(_refusal_of(exc))
        await self._send(reply)
        return True

    async def _on_stream(self, item: bytes) -> bool:
        """A frame of the wake stream: a changed result is a ``wake``; ``False`` once the socket is closed."""
        if item == BYE_FRAME:
            # The broker ended the stream (its queue overflowed, its user is gone, or the hub stopped serving): follow
            # again if the session and the hub still hold, which the next frame checks anyway.
            try:
                await self._sync(self._authenticate)
                await self._sync(self._fresh_context)
            except Refusal as refusal:
                return await self._refuse(refusal)
            except OperationError as exc:
                return await self._refuse(_refusal_of(exc))
            self._unfollow()
            await self._follow()
            return True
        event, data = _decode_frame(item)
        role = data.get("id")
        if event == "result":
            # A result that changed because this device took the last job shows no job: no wake (the old hub's
            # wake is «a job was just queued for a role you host», never a claim → idle).
            waiting = bool((data.get("data") or {}).get("rows"))
            if waiting and data.get("rev", 0) > 1 and self.device is not None and role in self.device.roles:
                await self._send({"type": "wake", "role": role})
            return True
        error = data.get("error") or {}
        code = error.get("code", "internal_error")
        if code in FATAL_OPERATION_CODES:
            status = 402 if code == "app_entitlement_blocked" else 404 if code == "app_inactive" else 403
            return await self._refuse(Refusal(code, error.get("message", ""), status=status))
        logger.warning("The wake of print host %s failed: %s.", self.device and self.device.device_id, error)
        return await self._refuse(Refusal(code, error.get("message", ""), status=500, fatal=False))

    # ── The frames ────────────────────────────────────────────────────────────────────────────────

    def _parse(self, message: dict) -> dict:
        text = message.get("text")
        if text is None:
            raise self._invalid(self._t(gettext_noop("This channel speaks JSON text frames: hello, claim, done, failed and beat.")))
        size = len(text.encode())
        if size > MAX_FRAME_BYTES:
            raise Refusal(
                "print.frame_too_large",
                self._t(gettext_noop("A frame of %(size)s bytes is over this channel's cap of %(cap)s bytes."))
                % {"size": size, "cap": MAX_FRAME_BYTES},
                status=413,
            )
        try:
            frame = json.loads(text)
        except ValueError:
            frame = None
        if not isinstance(frame, dict) or frame.get("type") not in ("hello", "claim", "done", "failed", "beat"):
            raise self._invalid(self._t(gettext_noop("This channel speaks hello, claim, done, failed and beat.")))
        return frame

    async def _hello(self, frame: dict) -> dict:
        device = await self._sync(self._register, frame)
        self._unfollow()
        self.device = device
        await self._follow()
        return {"type": "ready", "deviceId": device.device_id, "roles": device.roles, "heartbeatSeconds": HEARTBEAT_SECONDS}

    def _register(self, frame: dict) -> Device:
        user = self._authenticate()
        device_id = _text(frame, "deviceId", self).strip()
        if not device_id:
            raise Refusal(
                "print.device_required", gettext("This channel drains for one device: send its deviceId."), status=400
            )
        declared = frame.get("printers", [])
        if not isinstance(declared, list) or not all(isinstance(printer, str) for printer in declared):
            raise self._invalid(gettext("printers is the list of the ids of the printers this device reaches."))
        self.request.user = user
        ctx = get_builder().from_request(self.request)
        if declared:
            # printing's own input decides what a device and a list of printers are (ids, how many, how long).
            _validated(JOB_CLAIM, {"printers": declared, "device": device_id})
        printers = self._reached(ctx, device_id, declared)
        if printers is None:
            raise Refusal(
                "print.host_not_registered",
                gettext(
                    "This device is not set up to print in this hub: someone who manages the printers sets it up in "
                    "Printing → Devices."
                ),
                status=403,
            )
        if not printers:
            raise Refusal(
                "print.host_not_registered",
                gettext("This device reaches no active printer of this hub: choose its printers before printing."),
                status=403,
            )
        return Device(ctx=ctx, device_id=device_id, declared=declared, printers=printers)

    async def _claim(self, frame: dict) -> dict:
        device = self.device
        role = _text(frame, "role", self).strip()
        if role not in device.roles:
            raise Refusal(
                "print.role_not_hosted",
                self._t(gettext_noop("This device does not print «%(role)s» for this hub.")) % {"role": role},
                status=403,
                fatal=False,
            )
        printers = [printer for printer, usage in device.printers.items() if usage == role]
        answer = await self._sync(self._run, JOB_CLAIM, {"printers": printers, "device": device.device_id})
        job = answer["job"]
        if job is None:
            return {"type": "idle", "role": role}
        device.attempts[job["id"]] = job["attempts"]
        return _job_frame(job, role)

    async def _done(self, frame: dict) -> dict:
        device = self.device
        job_id = self._job_id(frame)
        # A confirmation re-sent after a reconnect names no hand-out: the first one, which the queue takes from the
        # device that held the job whatever its hand-out (the paper came out).
        attempt = device.attempts.get(job_id, 1)
        data = {"job_id": job_id, "device": device.device_id, "attempt": attempt}
        try:
            confirmed = (await self._sync(self._run, JOB_COMPLETE, data))["confirmed"]
        except OperationError as exc:
            if not _not_taken(exc):
                raise
            confirmed = False
        device.attempts.pop(job_id, None)
        return {"type": "ack", "jobId": job_id, "confirmed": confirmed}

    async def _failed(self, frame: dict) -> dict:
        device = self.device
        job_id = self._job_id(frame)
        error = _text(frame, "error", self)
        attempt = device.attempts.get(job_id)
        if attempt is None:
            # Not handed out on this socket: the report is not taken, the job comes back when its lease runs out.
            return {"type": "ack", "jobId": job_id, "requeued": False}
        data = {"job_id": job_id, "device": device.device_id, "attempt": attempt, "error": error}
        try:
            answer = await self._sync(self._run, JOB_FAIL, data)
            requeued = answer["confirmed"] and answer["job"]["status"] == "pending"
        except OperationError as exc:
            if not _not_taken(exc):
                raise
            requeued = False
        device.attempts.pop(job_id, None)
        return {"type": "ack", "jobId": job_id, "requeued": requeued}

    async def _beat(self, frame: dict) -> dict:
        device = self.device
        printers = await self._sync(self._still_reached)
        if printers != device.printers:
            self._unfollow()
            device.printers = printers
            await self._follow()
        # refreshed 0 = this device prints for no active printer any more (or it was retired): it stops, as when it
        # was never one.
        return {"type": "beat", "refreshed": len(printers), "heartbeatSeconds": HEARTBEAT_SECONDS}

    def _still_reached(self) -> dict[str, str]:
        device = self.device
        return self._reached(self._fresh_context(), device.device_id, device.declared) or {}

    # ── Session, context and the operations ───────────────────────────────────────────────────────

    def _authenticate(self):
        """The session's user; refused when there is none, it is not valid here or it is not the ``hello``'s."""
        key = self.request.COOKIES.get(settings.SESSION_COOKIE_NAME)
        if not key:
            raise Refusal("unauthenticated", gettext("Sign in to this hub to print: this connection has no session."), status=401)
        self.request.session = import_module(settings.SESSION_ENGINE).SessionStore(key)
        user = auth.get_user(self.request)
        held = self.device.ctx.actor if self.device is not None else None
        if not user.is_authenticated or (held is not None and user.pk != held.pk):
            raise Refusal(
                "unauthenticated",
                gettext("This connection's session is not valid on this hub: sign in again."),
                status=401,
            )
        return user

    def _fresh_context(self) -> OperationContext:
        """The ``hello``'s context with its permissions read again, as the live executor does before every run."""
        self.device.ctx = get_builder().refresh(self.device.ctx)
        return self.device.ctx

    def _run(self, name: str, data: dict) -> dict:
        """Run printing's operation ``name`` as the device's user (its session was checked for the frame)."""
        op = _operation(name)
        try:
            return op(self._fresh_context(), _validated(name, data)).model_dump(mode="json")
        except OperationError as exc:
            refusal = _refusal_of(exc)
            if refusal.fatal:
                raise refusal from exc
            raise

    def _reached(self, ctx: OperationContext, device_id: str, declared: list[str]) -> dict[str, str] | None:
        """The active printers the device prints for: id → function. Those of its registration in printing
        (``printing.device.get``), whatever ``declared`` says; with the session of whoever sets up the printers, the
        active ones among ``declared`` too, which its claim pairs. ``None``: a device not set up here (or retired)
        that this session does not pair."""
        op = _operation(DEVICE_GET)
        try:
            registration = op(ctx, _validated(DEVICE_GET, {"device": device_id})).device
        except OperationError as exc:
            raise _refusal_of(exc) from exc
        pairs = ctx.has(PAIRS)
        if registration is None and not pairs:
            return None
        printers = {} if registration is None else {str(p.id): p.usage for p in registration.printers if p.is_active}
        if pairs:
            printers.update(self._declared(ctx, declared))
        return printers

    def _declared(self, ctx: OperationContext, declared: list[str]) -> dict[str, str]:
        """The active printers of this hub among ``declared``: id → function."""
        op = _operation(PRINTER_GET)
        printers = {}
        for printer_id in declared:
            try:
                printer = op(ctx, _validated(PRINTER_GET, {"printer_id": printer_id}))
            except NotFound:
                continue  # not a printer of this hub
            except OperationError as exc:
                raise _refusal_of(exc) from exc
            if printer.is_active:
                printers[str(printer.id)] = printer.usage
        return printers

    # ── The wake ──────────────────────────────────────────────────────────────────────────────────

    async def _follow(self) -> None:
        """Subscribe the device's roles to the live broker: one subscription per role, its first waiting job."""
        device = self.device
        if not device.roles:
            return
        stream = Stream(device.ctx)
        op = _operation(JOB_LIST)
        for role in device.roles:
            params = {"status": "pending", "usage": role, "limit": 1, "sort": "created_at", "dir": "asc"}
            stream.subs[role] = Subscription(id=role, op=op, params=op.input.model_validate(params))
        device.stream = stream
        # Listening before the first run: no COMMIT after ``ready`` is missed (live.broker.Broker.register).
        await broker.register(stream)
        await executor.run_all(stream)

    def _unfollow(self) -> None:
        device = self.device
        if device is None or device.stream is None:
            return
        stream, device.stream = device.stream, None
        stream.closed = True
        broker.unregister(stream)
        executor.forget(stream)

    # ── Plumbing ──────────────────────────────────────────────────────────────────────────────────

    async def _sync(self, fn: Callable, *args: Any) -> Any:
        """Run the synchronous ``fn`` in a thread of its own, as Django runs a request's sync code, in the
        socket's language; the database connection it used is released after it (there is no request_finished)."""

        def call():
            try:
                with translation.override(self.language):
                    return fn(*args)
            finally:
                close_old_connections()

        async with ThreadSensitiveContext():
            return await sync_to_async(call)()

    async def _send(self, frame: dict) -> None:
        await self.send({"type": "websocket.send", "text": json.dumps(frame, ensure_ascii=False, separators=(",", ":"))})

    async def _refuse(self, refusal: Refusal) -> bool:
        """Send the refusal; close the socket if it is fatal. ``False`` once closed."""
        await self._send(refusal.frame())
        if not refusal.fatal:
            return True
        await self.send({"type": "websocket.close", "code": 4000 + refusal.status})
        return False

    def _t(self, message: str) -> str:
        """``message`` (marked with ``gettext_noop``) in the socket's language, for the async parts."""
        with translation.override(self.language):
            return gettext(message)

    def _invalid(self, message: str, fields: dict | None = None) -> Refusal:
        return Refusal("invalid_payload", message, status=422, fatal=False, fields=fields)

    def _job_id(self, frame: dict) -> str:
        job_id = _text(frame, "jobId", self).strip()
        try:
            return str(uuid.UUID(job_id))
        except ValueError:
            raise self._invalid(self._t(gettext_noop("jobId is the id of a job this hub handed out."))) from None


def _http_request(scope: dict) -> HttpRequest:
    """The handshake as a Django request: the Host, the cookies and the headers the HTTP doors read."""
    scheme = "https" if scope.get("scheme") == "wss" else "http"
    return ASGIRequest({**scope, "type": "http", "method": "GET", "scheme": scheme}, io.BytesIO())


def _same_origin(request: HttpRequest) -> bool:
    """Whether the handshake comes from a page of this very host (a browser always sends ``Origin``)."""
    origin = request.headers.get("Origin")
    if not origin:
        return False
    parts = urlsplit(origin)
    scheme = "https" if request.is_secure() else "http"
    return parts.scheme == scheme and parts.netloc.lower() == request.get_host().lower()


def _no_view(request: HttpRequest) -> None:
    """The gate is asked for its decision only; nothing comes after it."""
    raise AssertionError("The print channel runs no view.")


def _operation(name: str):
    try:
        return get(name)
    except UnknownOperation:
        raise Refusal("app_inactive", gettext("Printing is not on in this hub."), status=404) from None


def _validated(name: str, data: dict):
    op = _operation(name)
    try:
        return op.input.model_validate(data)
    except pydantic.ValidationError as exc:
        fields = {}
        for error in exc.errors():
            fields.setdefault(".".join(str(part) for part in error["loc"]) or NON_FIELD_ERRORS, error["msg"])
        raise Refusal("invalid_payload", gettext("Invalid frame."), status=422, fatal=False, fields=fields) from None


def _refusal_of(exc: OperationError) -> Refusal:
    """An operation's refusal as a frame, with the code it carries over HTTP (``unauthenticated`` for 401, the old
    hub's); a refusal no retry fixes closes the socket, as a hub that stopped serving does (the gate's code)."""
    error = exc.envelope()["error"]
    if exc.status == 401:
        return Refusal("unauthenticated", str(error["message"]), status=401)
    return Refusal(
        error["code"],
        str(error["message"]),
        status=exc.status,
        fatal=isinstance(exc, HostClosed) or error["code"] in FATAL_OPERATION_CODES,
        fields=error.get("fields"),
    )


def _not_taken(exc: OperationError) -> bool:
    """Whether the queue did not take the answer because the job is not this device's (any more)."""
    return isinstance(exc, NotFound) or exc.code == NOT_YOURS


def _text(frame: dict, key: str, socket: PrintSocket) -> str:
    value = frame.get(key, "")
    if not isinstance(value, str):
        raise socket._invalid(socket._t(gettext_noop("%(field)s is text.")) % {"field": key})
    return value


def _job_frame(job: dict, role: str) -> dict:
    """printing's hand-out as the old ``job`` frame, the rest of its fields camelCased after it."""
    frame = {
        "type": "job",
        "jobId": job["id"],
        "role": role,
        "documentType": job["document_type"],
        "document": job["document"],
        "format": job["format"],
        "attempts": job["attempts"],
    }
    for key, value in job.items():
        if key != "id":
            frame.setdefault(_CAMEL.sub(lambda match: match.group(1).upper(), key), value)
    return frame


def _decode_frame(item: bytes) -> tuple[str, dict]:
    """The event and the data of one frame of a live stream (``live.sse.frame``)."""
    event, data = "", {}
    for line in item.decode().splitlines():
        if line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif line.startswith("data: "):
            data = json.loads(line.removeprefix("data: "))
    return event, data
