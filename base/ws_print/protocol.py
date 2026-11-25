"""One connection of a print host to ``/ws/print``: the ASGI application, its loop and the frames it answers."""

import asyncio
import json
import logging
import re
import uuid
from collections.abc import Callable
from contextlib import nullcontext
from typing import Any

from asgiref.sync import ThreadSensitiveContext, sync_to_async
from django.conf import settings
from django.db import close_old_connections
from django.http import HttpRequest
from django.utils import translation
from django.utils.translation import gettext, gettext_noop
from live.context import get_builder
from live.errors import OperationError
from live.executor import BYE_FRAME, Stream

from base.tenancy.context import use_hub
from base.ws_print.access import AccessMixin
from base.ws_print.devices import Device, DevicesMixin
from base.ws_print.handshake import HandshakeMixin
from base.ws_print.presence import HEARTBEAT_SECONDS, PresenceMixin
from base.ws_print.printing import JOB_CLAIM, JOB_COMPLETE, JOB_FAIL, _not_taken, _validated
from base.ws_print.refusals import FATAL_OPERATION_CODES, Refusal, _refusal_of
from base.ws_print.wake import WakeMixin, _decode_frame, _waiting

# Its lines keep the name the channel always logged under, whichever module of the package writes them.
logger = logging.getLogger("base.ws_print")

PATH = "/ws/print"
#: Longest client→server frame accepted. These frames carry ids and a role, never a document, and the socket
#: reads them before anybody has proved who they are (the old hub's ``MAX_FRAME_BYTES``).
MAX_FRAME_BYTES = 8 * 1024
#: Seconds a socket may stay silent before saying ``hello``: one that never does is no print host.
HELLO_TIMEOUT_SECONDS = 15.0
#: Close code of a refusal before the handshake: Daphne answers the handshake 403.
HANDSHAKE_REFUSED = 4403
#: Close code when the channel itself fails.
INTERNAL_ERROR_CLOSE = 1011

_CAMEL = re.compile(r"_([a-z])")


async def print_socket(scope: dict, receive: Callable, send: Callable) -> None:
    """The ASGI application of ``/ws/print`` (``config.asgi`` routes the WebSocket scope here)."""
    await PrintSocket(scope, receive, send).run()


class PrintSocket(HandshakeMixin, AccessMixin, DevicesMixin, WakeMixin, PresenceMixin):
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

    # ── The loop ──────────────────────────────────────────────────────────────────────────────────

    async def _serve(self) -> None:  # noqa: C901
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
            # The old hub's wake is «a job was just queued for a role you host»: a job waiting that the last result
            # did not show. A claim, a confirmation or a failure of this very device queues nothing new for it, and
            # its wake came late (the re-run is grouped), between a later claim and its idle.
            device = self.device
            waiting = {_waiting(row) for row in (data.get("data") or {}).get("rows", [])}
            known = device.waiting.get(role)
            device.waiting[role] = waiting
            news = set() if known is None else waiting - known
            ours = news & device.sent_back
            device.sent_back -= ours
            if news - ours and role in device.roles:
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
        # Connecting is news: the device is there (the old hub's heartbeat at hello).
        await self._sync(self._announce)
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
        if requeued:
            device.sent_back.add(_waiting(answer["job"]))
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
        """The printers the device still prints for; when there are any, the beat is news that it is there."""
        device = self.device
        printers = self._reached(self._fresh_context(), device.device_id, device.declared) or {}
        if printers:
            self._announce()
        return printers

    # ── Plumbing ──────────────────────────────────────────────────────────────────────────────────

    async def _sync(self, fn: Callable, *args: Any) -> Any:
        """Run the synchronous ``fn`` in a thread of its own, as Django runs a request's sync code, in the
        socket's language and, once admitted, in its hub's database (``use_hub``); the database
        connection it used is released after it (there is no request_finished)."""
        hub = getattr(self.request, "hub", None)

        def call():
            try:
                with translation.override(self.language), (use_hub(hub) if hub is not None else nullcontext()):
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
