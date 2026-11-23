"""erplora.com's AI gateway for the Hub's assistant: every door is a signed POST (``base.signing``, the secret of every
``/internal`` call) naming this business by its host (``scope.key``); the browser never talks to it. ``stream_turn``
relays a turn as the Hub's own frames (``text``, ``usage``, ``error``, ``done``); its refusals become one of ours
(``assistant.quota_exceeded``, ``assistant.unavailable``…), and what never reached it is ``assistant.unreachable``.
"""

import contextlib
import dataclasses
import json
import logging
import time
from collections.abc import AsyncIterator, Callable, Iterable
from contextvars import ContextVar
from typing import Any

import httpx
from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import StreamingHttpResponse
from live.assistant import tool_name
from live.context import OperationContext, Scope, get_builder
from live.operations import get

from base import signing
from base.auth import saas_internal_url
from base.operations import HostScopeResolver

from .relevance import DOCS_SEARCH

#: This month's messages of the assistant, the read «Usage and plan» makes; a tool too.
USAGE = "base.assistant.usage"

TURN_PATH = "/internal/assistant/chat/stream"
USAGE_PATH = "/internal/assistant/usage"
REPORT_PATH = "/internal/assistant/report"
DOCS_PATH = "/internal/assistant/docs/search"
TRANSCRIBE_PATH = "/internal/speech/transcribe"
SYNTHESIZE_PATH = "/internal/speech/synthesize"
#: A door that answers at once; the turn waits longer for its model, piece by piece.
TIMEOUT_SECONDS = 15
TURN_TIMEOUT = httpx.Timeout(15.0, read=120.0)
#: Reading aloud waits for erplora.com's engine, up to a minute like its other services (saas ``assistant.media``): a
#: little longer here, so a slow one comes back as erplora.com's own refusal, never as the Hub hanging up first.
SPEECH_TIMEOUT = httpx.Timeout(15.0, read=65.0)


#: Each failed call to the gateway leaves one line here: its door, the business, the HTTP status and the
#: gateway's code, or that it never got there and how. The panel says every failure in a few words of its own, so the
#: reason lives only in this log, under the assistant's name. Never what the person said, dictated or was answered.
logger = logging.getLogger("base.assistant")


def _log_refused(path: str, hub: Any, status: int, error: dict) -> None:
    logger.warning(
        "base.assistant.gateway_refused path=%s hub=%s status=%s code=%s", path, hub, status, error.get("code") or "-"
    )


def _log_unreachable(path: str, hub: Any, problem: Exception) -> None:
    logger.warning("base.assistant.gateway_unreachable path=%s hub=%s kind=%s", path, hub, type(problem).__name__)


class GatewayError(Exception):
    """A door of the gateway that did not answer what was asked: its code (ours or the gateway's) and details."""

    def __init__(self, code: str, status: int = 0, details: dict | None = None):
        super().__init__(code)
        self.code, self.status, self.details = code, status, details or {}


def _signed(path: str, payload: dict) -> tuple[str, bytes, dict[str, str]]:
    body = json.dumps(payload, ensure_ascii=False).encode()
    headers = {
        "Content-Type": "application/json",
        **signing.signed_headers("POST", path, body, int(time.time()), settings.INTERNAL_SHARED_SECRET),
    }
    return saas_internal_url(path), body, headers


def _error_of(status: int, body: Any) -> dict:
    error = body.get("error") if isinstance(body, dict) else None
    return error if isinstance(error, dict) else {}


def _send(path: str, payload: dict, timeout: float | httpx.Timeout) -> httpx.Response:
    """``payload`` signed to ``path``: erplora.com's answer, or a ``GatewayError`` (logged) when it never got there or
    refused it."""
    url, body, headers = _signed(path, payload)
    try:
        response = httpx.post(url, content=body, headers=headers, timeout=timeout)
    except httpx.HTTPError as problem:
        _log_unreachable(path, payload.get("hub"), problem)
        raise GatewayError("assistant.unreachable") from None
    if response.status_code >= 300:
        error = _error_of(response.status_code, _json_of(response))
        _log_refused(path, payload.get("hub"), response.status_code, error)
        raise GatewayError(str(error.get("code") or "assistant.unavailable"), response.status_code, error)
    return response


def _json_of(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _post(path: str, payload: dict) -> dict:
    answer = _json_of(_send(path, payload, TIMEOUT_SECONDS))
    return answer if isinstance(answer, dict) else {}


def _post_audio(path: str, payload: dict) -> dict:
    """The audio a door answers (``/internal/speech/synthesize``'s mp3): ``{audio, content_type}``; an answer that is
    no audio is a refusal too."""
    response = _send(path, payload, SPEECH_TIMEOUT)
    kind = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if not kind.startswith("audio/") or not response.content:
        _log_refused(path, payload.get("hub"), response.status_code, {"code": "assistant.not_audio"})
        raise GatewayError("assistant.not_audio", response.status_code)
    return {"audio": response.content, "content_type": kind}


def usage(scope: Scope) -> dict:
    """This month's allowance of the business: ``{used, limit, resets_at, demo}`` as erplora.com counts it."""
    answer = _post(USAGE_PATH, {"hub": scope.key})
    return {key: answer.get(key) for key in ("used", "limit", "resets_at", "demo")}


def report(  # noqa: PLR0913
    scope: Scope, *, message_id: str, reason: str, comment: str, question: str, answer: str, web: bool | None = None
) -> dict:
    """Send erplora.com a bad answer of the assistant: ``{sent, duplicate}``. ``web``: whether its turn brought pages of
    the web (the turn's ``done.web``, kept by the browser), whose text erplora.com then does not mail; left
    out when the browser does not know, and erplora.com's safe default decides."""
    payload = {
        "hub": scope.key, "message_id": message_id, "reason": reason, "comment": comment, "question": question,
        "answer": answer,
    }
    if web is not None:
        payload["web"] = web
    sent = _post(REPORT_PATH, payload)
    return {"sent": bool(sent.get("sent")), "duplicate": bool(sent.get("duplicate"))}


def transcribe(scope: Scope, *, audio: str, mime_type: str, language: str) -> dict:
    """The text of a dictation (``audio`` in base64): ``{text, language}``."""
    answer = _post(TRANSCRIBE_PATH, {"hub": scope.key, "audio": audio, "mime_type": mime_type, "language": language})
    return {"text": str(answer.get("text") or ""), "language": str(answer.get("language") or language)}


def speak(scope: Scope, *, text: str, language: str, voice: str) -> dict:
    """``text`` read aloud by erplora.com in ``voice`` (a voice of its engine; none, its own for the language): the mp3 and its
    type, ``{audio, content_type}``. The voices are Spanish and English, as the documentation: any other language
    reads in English."""
    payload = {"hub": scope.key, "text": text, "language": docs_language(language)}
    if voice:
        payload["voice"] = voice
    return _post_audio(SYNTHESIZE_PATH, payload)


def docs_language(language: str) -> str:
    """The language of ERPlora's documentation a person reads: Spanish for any Spanish, else English (the two it is
    written in)."""
    return "es" if (language or "").split("-")[0].lower() == "es" else "en"


def docs_search(scope: Scope, *, query: str, language: str, limit: int) -> dict:
    """The excerpts of ERPlora's documentation nearest to ``query``, from erplora.com's one index (saas ASSISTANT-F28),
    in the documentation of ``language``: ``{results: [{source, path, heading, text, score, lang}]}``."""
    return _post(DOCS_PATH, {"hub": scope.key, "query": query, "language": docs_language(language), "limit": limit})


# ── What the turn's tools wait on erplora.com for, before the turn's transaction ─────────────────────────────────

@dataclasses.dataclass(frozen=True)
class Prepared:
    """What the tools of this request's turn wait on erplora.com for, asked before its transaction (``prepare``): the
    documentation searches by their question and limit, and this month's messages (``None`` when not asked for), each
    erplora.com's answer or its refusal."""

    docs: dict[tuple[str, int], dict | GatewayError] = dataclasses.field(default_factory=dict)
    usage: dict | GatewayError | None = None


_prepared: ContextVar[Prepared | None] = ContextVar("base_assistant_prepared", default=None)


def prepare_docs(ctx: OperationContext, pending: Iterable[Any]) -> dict[tuple[str, int], dict | GatewayError]:
    """The documentation searches among ``pending`` (the tools the model asked for), asked now for ``ctx``'s person:
    by their question and limit, erplora.com's answer or its refusal. None for whom may not run the search, and none
    whose arguments the search would refuse anyway."""
    op = get(DOCS_SEARCH)
    if ctx.actor is None or not ctx.has(op.permission):
        return {}
    name = tool_name(DOCS_SEARCH)
    prepared: dict[tuple[str, int], dict | GatewayError] = {}
    for call in pending:
        if call.name != name:
            continue
        try:
            data = op.input.model_validate_json(call.arguments or "{}")
        except ValueError:  # pydantic's ValidationError, the JSON's too: the turn refuses it as invalid_payload
            continue
        key = (data.query, data.limit)
        if key in prepared:
            continue
        try:
            prepared[key] = docs_search(ctx.scope, query=data.query, language=ctx.language, limit=data.limit)
        except GatewayError as refused:
            prepared[key] = refused
    return prepared


def prepare_usage(ctx: OperationContext, pending: Iterable[Any]) -> dict | GatewayError | None:
    """This month's messages when ``pending`` asks for them, asked now: erplora.com's answer or its refusal. ``None``
    when not asked for, or for whom may not read them."""
    if ctx.actor is None or not ctx.has(get(USAGE).permission):
        return None
    if not any(call.name == tool_name(USAGE) for call in pending):
        return None
    try:
        return usage(ctx.scope)
    except GatewayError as refused:
        return refused


@contextlib.contextmanager
def prepared(answers: Prepared):
    """While inside, ``searched_docs`` and ``month_usage`` read ``answers`` instead of asking erplora.com."""
    token = _prepared.set(answers)
    try:
        yield
    finally:
        _prepared.reset(token)


async def prepare(request: Any, data: Any) -> Prepared:
    """What the turn's tools wait on erplora.com for, asked before ``base.assistant.turn`` opens its transaction (up to
    ``TIMEOUT_SECONDS`` inside it would hold the hub's connection): the documentation searches and this month's
    messages the model asked for, for the route to hand them to the turn (``prepared``)."""
    if not {call.name for call in data.pending} & {tool_name(DOCS_SEARCH), tool_name(USAGE)}:
        return Prepared()
    ctx = await sync_to_async(get_builder().from_request)(request)
    return await sync_to_async(_prepare_now)(ctx, data.pending)


def _prepare_now(ctx: OperationContext, pending: list[Any]) -> Prepared:
    return Prepared(docs=prepare_docs(ctx, pending), usage=prepare_usage(ctx, pending))


def searched_docs(ctx: OperationContext, *, query: str, limit: int) -> dict:
    """The documentation search of ``base.docs.search``: what this request's turn asked before its transaction
    (``prepare``) or, outside a turn, erplora.com's answer now. ``GatewayError`` when it could not answer."""
    return _answered(
        (_prepared.get() or Prepared()).docs.get((query, limit)),
        lambda: docs_search(ctx.scope, query=query, language=ctx.language, limit=limit),
    )


def month_usage(scope: Scope) -> dict:
    """This month's messages of ``base.assistant.usage``: what this request's turn asked before its transaction
    (``prepare``) or, outside a turn, erplora.com's answer now. ``GatewayError`` when it could not answer."""
    return _answered((_prepared.get() or Prepared()).usage, lambda: usage(scope))


def _answered(prepared: dict | GatewayError | None, ask: Callable[[], dict]) -> dict:
    if prepared is None:
        return ask()
    if isinstance(prepared, GatewayError):
        raise prepared
    return prepared


def sse(frame: dict) -> bytes:
    """One frame of the Hub's turn as a server-sent event."""
    return f"data: {json.dumps(frame, ensure_ascii=False)}\n\n".encode()


def _refusal(status: int, error: dict, retry_after: str | None) -> dict:
    """A turn the gateway did not take, as one of ours."""
    code = str(error.get("code") or "")
    if code == "assistant.quota_exceeded":
        return {"type": "error", "code": code, **{key: error.get(key) for key in ("used", "limit", "resets_at", "demo")}}
    if status == 429:
        return {"type": "error", "code": "assistant.rate_limited", "retry_after": int(retry_after or 60)}
    if status == 413:
        return {"type": "error", "code": "assistant.too_large"}
    return {"type": "error", "code": "assistant.unavailable", "retriable": True}


def _assistant_message(text: str, calls: list[dict]) -> dict:
    message: dict[str, Any] = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = [
            {"id": call["call_id"], "type": "function", "function": {"name": call["name"], "arguments": call["arguments"]}}
            for call in calls
        ]
    return message


async def stream_turn(  # noqa: C901, PLR0912, PLR0915
    scope: Scope, *, messages: list[dict], tools: list[dict], instructions: str, continuation: str | None
) -> AsyncIterator[dict]:
    """A turn through the gateway, as the Hub's frames: ``text`` piece by piece, ``usage``, an ``error``, and ``done``
    with what the browser keeps (``append``), the tools the model asked for (``pending``), their ``continuation`` and
    whether the turn brought pages of the web (``web``: the gateway's ``{type: web}``, also before a failure; the
    browser sends it back with a report of the answer). A refusal of the gateway is a lone ``error``; a
    failure half way keeps what was said."""
    payload = {"hub": scope.key, "messages": messages, "instructions": instructions, "tools": tools}
    if continuation:
        payload["continuation"] = continuation
    url, body, headers = _signed(TURN_PATH, payload)
    text: list[str] = []
    calls: list[dict] = []
    token: str | None = None
    finished = failed = web = False
    try:
        async with httpx.AsyncClient(timeout=TURN_TIMEOUT) as client:
            async with client.stream("POST", url, content=body, headers=headers) as response:
                if response.status_code != 200:
                    await response.aread()
                    try:
                        error = _error_of(response.status_code, response.json())
                    except ValueError:
                        error = {}
                    _log_refused(TURN_PATH, scope.key, response.status_code, error)
                    yield _refusal(response.status_code, error, response.headers.get("Retry-After"))
                    return
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        finished = True
                        break
                    try:
                        frame = json.loads(data)
                    except ValueError:
                        continue
                    kind = frame.get("type") if isinstance(frame, dict) else None
                    if kind == "text_delta" and frame.get("text"):
                        text.append(str(frame["text"]))
                        yield {"type": "text", "text": str(frame["text"])}
                    elif kind == "function_call":
                        calls.append(
                            {"call_id": str(frame.get("call_id")), "name": str(frame.get("name")), "arguments": str(frame.get("arguments") or "{}")}
                        )
                    elif kind == "response":
                        token = frame.get("continuation") or None
                    elif kind == "web":
                        web = True
                    elif kind == "usage":
                        yield {"type": "usage", **{key: frame.get(key) for key in ("used", "limit", "resets_at", "demo")}}
                    elif kind == "error":
                        failed = True
                        logger.warning(
                            "base.assistant.gateway_failed path=%s hub=%s code=%s retriable=%s",
                            TURN_PATH, scope.key, frame.get("code") or "-", bool(frame.get("retriable")),
                        )
                        yield {"type": "error", "code": "assistant.provider_failed", "retriable": bool(frame.get("retriable"))}
    except httpx.HTTPError as problem:
        if not text and not calls:
            _log_unreachable(TURN_PATH, scope.key, problem)
            yield {"type": "error", "code": "assistant.unreachable", "retriable": True}
            return
        failed = True
        logger.warning("base.assistant.gateway_cut path=%s hub=%s kind=%s", TURN_PATH, scope.key, type(problem).__name__)
        yield {"type": "error", "code": "assistant.cut", "retriable": True}
    if not finished and not failed:
        failed = True
        logger.warning("base.assistant.gateway_cut path=%s hub=%s kind=no_done", TURN_PATH, scope.key)
        yield {"type": "error", "code": "assistant.cut", "retriable": True}
    said = "".join(text)
    if failed:
        kept = [_assistant_message(said, [])] if said else []
        yield {"type": "done", "append": kept, "pending": [], "continuation": None, "web": web}
        return
    yield {
        "type": "done", "append": [_assistant_message(said, calls)], "pending": calls, "continuation": token, "web": web
    }


async def turn_frames(scope: Scope, plan: dict) -> AsyncIterator[bytes]:
    """The answer of ``base.assistant.turn`` (``plan``, the operation's output) as the panel reads it: what ran
    (``executed``), then the card of a write that waits (``confirm``), why it stops (``assistant.too_many_steps``) or
    the gateway's turn; the closing ``done`` always carries the tools' results to keep before the model's message, and
    says ``web: false`` when the round never reached the gateway (no pages: without the word, the browser would not know
    where the whole answer came from)."""
    for row in plan["executed"]:
        yield sse({"type": "executed", **row})
    if plan["confirm"] is not None:
        yield sse({"type": "confirm", "card": plan["confirm"], "call": plan["pending"][0]})
        waits = {"append": plan["append"], "pending": plan["pending"], "continuation": plan["continuation"]}
        yield sse({"type": "done", **waits, "web": False})
        return
    if plan["stop"]:
        yield sse({"type": "error", "code": plan["stop"]})
        yield sse({"type": "done", "append": plan["append"], "pending": [], "continuation": None, "web": False})
        return
    closed = False
    async for frame in stream_turn(
        scope,
        messages=plan["messages"],
        tools=plan["tools"],
        instructions=plan["instructions"],
        continuation=plan["continuation"],
    ):
        if frame["type"] == "done":
            closed = True
            frame = {**frame, "append": [*plan["append"], *frame["append"]]}
        yield sse(frame)
    if not closed:
        yield sse({"type": "done", "append": plan["append"], "pending": [], "continuation": None, "web": False})


def turn_response(request: Any, plan: dict) -> StreamingHttpResponse:
    """The streamed answer of a turn: never cached nor held by a proxy, read by the panel piece by piece."""
    scope = HostScopeResolver().resolve(request)
    response = StreamingHttpResponse(turn_frames(scope, plan), content_type="text/event-stream; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
