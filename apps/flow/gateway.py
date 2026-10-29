"""erplora.com's assistant door for an automation's «Ask the assistant» step (FLOW-F38, F39), without the ORM.

The step's turn goes to ``POST /internal/assistant/chat`` (``saas`` ``assistant/internal.py``, ASSISTANT-F13: the
turn answered at once, for what nobody watches), signed as every ``/internal`` call (``base.signing``) and naming the
business by its host. erplora.com counts it in the same monthly messages as the chat (the first round of a step is
one message; a round that answers its tools with the ``continuation`` it got costs none) and keeps nothing of it.

A failure the SaaS says waiting may mend (``retriable``, a 5xx without a word, a rate limit, a door not reached) is
tried again after ``PAUSES`` (three tries in all, as the old hub's step); anything else is final. Retrying a turn
never repeats a read or an action of the business: the Hub runs them, not the gateway.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from django.conf import settings

from base import signing
from base.auth import saas_internal_url

PATH = "/internal/assistant/chat"
#: The seconds before the second and the third try.
PAUSES = (1, 3)
#: A turn waits for its model: up to a minute to read the answer.
TIMEOUT = httpx.Timeout(15.0, read=60.0)


class Failed(Exception):
    """The turn did not come back: the gateway's code (or ours) and whether waiting may mend it."""

    def __init__(self, code: str, retriable: bool, status: int = 0):
        super().__init__(code)
        self.code, self.retriable, self.status = code, retriable, status


@dataclass(frozen=True)
class Answer:
    text: str
    calls: list[dict] = field(default_factory=list)
    continuation: str | None = None


def _answer(body: Any) -> Answer:
    items = body.get("output") if isinstance(body, dict) else None
    texts: list[str] = []
    calls: list[dict] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            texts += [str(part.get("text") or "") for part in item.get("content") or [] if isinstance(part, dict)]
        elif item.get("type") == "function_call":
            calls.append(
                {"call_id": str(item.get("call_id")), "name": str(item.get("name")), "arguments": str(item.get("arguments") or "{}")}
            )
    token = body.get("continuation") if isinstance(body, dict) else None
    return Answer("".join(texts).strip(), calls, str(token) if token else None)


def _once(payload: dict) -> Answer:
    body = json.dumps(payload, ensure_ascii=False).encode()
    headers = {
        "Content-Type": "application/json",
        **signing.signed_headers("POST", PATH, body, int(time.time()), settings.INTERNAL_SHARED_SECRET),
    }
    try:
        response = httpx.post(saas_internal_url(PATH), content=body, headers=headers, timeout=TIMEOUT)
    except httpx.HTTPError:
        raise Failed("assistant.unreachable", True) from None
    try:
        answer = response.json()
    except ValueError:
        answer = None
    if response.status_code < 300:
        return _answer(answer)
    error = answer.get("error") if isinstance(answer, dict) and isinstance(answer.get("error"), dict) else {}
    code = str(error.get("code") or "assistant.unavailable")
    if "retriable" in error:
        retriable = bool(error["retriable"])
    else:
        retriable = response.status_code >= 500 or code == "rate_limited"
    raise Failed(code, retriable, response.status_code)


def turn(hub: str, *, messages: list[dict], tools: list[dict], instructions: str, continuation: str | None = None) -> Answer:
    """One turn of the step's conversation: its words, the tools the model asks for and their ``continuation``."""
    payload: dict[str, Any] = {"hub": hub, "messages": messages, "tools": tools, "instructions": instructions}
    if continuation:
        payload["continuation"] = continuation
    for pause in PAUSES:
        try:
            return _once(payload)
        except Failed as failed:
            if not failed.retriable:
                raise
            time.sleep(pause)
    return _once(payload)
