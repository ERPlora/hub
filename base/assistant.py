"""The Hub's assistant (APP-BASE-9; PLAN §30, ronda 2026-10-22b): chat and voice in the Hub against erplora.com's AI
gateway (``saas`` ``assistant/internal.py``), without the ORM.

- **Its tools** (``catalog``) are the operations of the apps on in this business that this person may run (the
  operation's own permission), told to the assistant by their ``ai=`` description: never one that says «Not an
  assistant tool» or «System only», one without a permission (the system's), the assistant's own, nor what is never
  done from the chat (``NOT_FROM_CHAT``: emptying the business, a file to download). A turn offers only the few of
  what was asked (``relevant``, at most ``MAX_TOOLS``), never the whole catalogue. A tool runs as the person, by its
  own operation (``run_tool``): the same permission, transaction and refusals as the button on the screen.
- **A write never runs without the person's yes**: its card (``card``) says what it will send, each datum by its name
  in the person's language (the name its app's models give it: their metadata, no query); ``risk="high"`` asks
  to type a word in the person's language (``CONFIRM_WORD``) or, over records named by ``ids``, how many; such a write
  that names no record is not done from the chat (``blocked``).
- **The gateway**: every door is a signed POST (``base.signing``, the secret of every ``/internal`` call) naming this
  business by its host (``scope.key``); the browser never talks to it. ``stream_turn`` relays a turn as the Hub's own
  frames (``text``, ``usage``, ``error``, ``done``); its refusals become one of ours (``assistant.quota_exceeded``,
  ``assistant.unavailable``…), and what never reached it is ``assistant.unreachable``.
"""

import json
import re
import time
import unicodedata
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from functools import cache
from typing import Any

import httpx
import pydantic
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.http import StreamingHttpResponse
from django.utils import translation
from django.utils.text import capfirst
from django.utils.translation import get_language_info, gettext, pgettext_lazy
from live.context import OperationContext, Scope
from live.errors import AppInactive, OperationError, PermissionDenied, Unauthorized
from live.meta import LiveAppConfig, all_live_app_configs
from live.operations import Operation, registry

from base import approvals, entitlement, signing
from base.auth import saas_internal_url
from base.operations import HostScopeResolver

#: The tools a turn offers at most: the gateway takes 256, the model chooses better among a few.
MAX_TOOLS = 40
#: Rounds of tools of one request of the person (the old hub's guard against a loop, not an allowance).
MAX_ROUNDS = 6
#: Always offered when the person may read them: the checklist and the business's own data.
ALWAYS = ("base.setup.status", "base.business.get")
#: Never from the chat (the old hub's «destructive actions of the hub itself»): emptying the business; a file.
NOT_FROM_CHAT = frozenset({"base.hub.reset", "base.blueprint.export"})
NOT_A_TOOL = ("Not an assistant tool", "System only")
SEPARATOR = "__"
#: What a dangerous write asks to type, in the person's language.
CONFIRM_WORD = pgettext_lazy("base", "CONFIRM")
#: A tool's result told back to the model: no more (a list of a hundred rows fits).
MAX_RESULT_CHARS = 60_000

TURN_PATH = "/internal/assistant/chat/stream"
USAGE_PATH = "/internal/assistant/usage"
REPORT_PATH = "/internal/assistant/report"
TRANSCRIBE_PATH = "/internal/speech/transcribe"
#: A door that answers at once; the turn waits longer for its model, piece by piece.
TIMEOUT_SECONDS = 15
TURN_TIMEOUT = httpx.Timeout(15.0, read=120.0)


# ── Tools ────────────────────────────────────────────────────────────────────────────────────────────────────────


def tool_name(operation_name: str) -> str:
    """The operation's name as a tool's (the gateway's function names take no dots)."""
    return operation_name.replace(".", SEPARATOR)


def operation_of(name: str, tools: dict[str, Operation]) -> Operation | None:
    """The operation of the tool ``name`` among ``tools``; ``None`` for one it was not offered."""
    for op in tools.values():
        if tool_name(op.name) == name:
            return op
    return None


def named(name: str) -> Operation | None:
    """The registered operation the tool ``name`` stands for, offered or not: only to name it in a receipt (BASE-G118:
    «Not done, not allowed: Create in Demo»); it never runs from here."""
    return operation_of(name, registry)


def description(op: Operation) -> str:
    ai = op.ai if isinstance(op.ai, dict) else None
    return str(ai.get("description", "")).strip() if ai else ""


def risk(op: Operation) -> str:
    ai = op.ai if isinstance(op.ai, dict) else {}
    return "high" if ai.get("risk") == "high" else "normal"


def is_tool(op: Operation) -> bool:
    text = description(op)
    return (
        bool(text)
        and op.permission is not None
        and not text.startswith(NOT_A_TOOL)
        and op.name not in NOT_FROM_CHAT
        and not op.name.startswith("base.assistant.")
    )


def active_apps(scope: Scope) -> dict[str, LiveAppConfig]:
    """The apps on in ``scope``'s business: every app of ours but the paid ones it has no right to."""
    blocked = entitlement.blocked_apps(scope)
    return {config.label: config for config in all_live_app_configs() if config.label not in blocked}


def catalog(ctx: OperationContext) -> dict[str, Operation]:
    """The tools of ``ctx``'s person: by name, in name order. A write a manager may approve is theirs too, as its
    button on the screen is (APP-BASE-5): running it asks for the approval (BASE-G118)."""
    on = active_apps(ctx.scope)
    return {
        name: op
        for name, op in sorted(registry.items())
        if op.app_label in on and is_tool(op) and (ctx.has(op.permission) or approvals.label_of(op) is not None)
    }


#: What a person says (Spanish or English) → the verbs of the operations' names that do it.
VERBS = {
    "create": ("crea", "crear", "creame", "alta", "añade", "añadir", "anade", "nuevo", "nueva", "add", "create", "new"),
    "update": ("cambia", "cambiar", "modifica", "actualiza", "edita", "pon", "update", "change", "edit", "set"),
    "delete": ("borra", "borrar", "elimina", "quita", "delete", "remove"),
    "list": ("lista", "listar", "muestra", "ver", "dime", "cuantos", "cuantas", "cuales", "busca", "list", "show", "find",
             "search", "how", "which"),
    "get": ("dame", "datos", "detalle", "get", "detail"),
    "complete": ("cobra", "cobrar", "charge", "pay"),
    "void": ("anula", "anular", "void", "cancel"),
    "close": ("cierra", "cerrar", "close"),
    "open": ("abre", "abrir", "open"),
}
_WORD = re.compile(r"[a-z0-9]+")


def _stems(text: str) -> set[str]:
    """The words of ``text`` without accents, lowercase, cut to five letters (a cheap stem that joins «servicio» and
    «service», «clientes» and «client»); shorter than three letters, none."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return {word[:5] for word in _WORD.findall(plain) if len(word) >= 3}


def _asked(texts: Iterable[str]) -> tuple[set[str], set[str]]:
    """The stems of what was asked and the verbs (``VERBS``) it names."""
    words = set()
    for text in texts:
        plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
        words |= set(_WORD.findall(plain))
    verbs = {verb for verb, said in VERBS.items() if words & {word for word in said}}
    return {word[:5] for word in words if len(word) >= 3}, verbs


@cache
def _app_words(label: str, language: str) -> frozenset[str]:
    """How a person names the app ``label``: its id, its name and its menu, in English and in ``language``."""
    config = next((c for c in all_live_app_configs() if c.label == label), None)
    words = _stems(label.replace("_", " "))
    if config is None:
        return frozenset(words)
    for lang in ("en", language):
        with translation.override(lang):
            words |= _stems(str(config.verbose_name))
            for nav in getattr(config, "navigation", []) or []:
                words |= _stems(str(nav.label))
    return frozenset(words)


def relevant(tools: dict[str, Operation], texts: Iterable[str], language: str) -> list[Operation]:
    """The tools of what ``texts`` ask, best first, at most ``MAX_TOOLS``: the app named (in either language) weighs
    most, then the verb asked of the operation's own action, then the words of its description; ``ALWAYS`` first."""
    asked, verbs = _asked(texts)

    def score(op: Operation) -> int:
        app, entity, action = op.name.split(".")
        points = 4 * len(asked & _app_words(app, language))
        points += 3 * (action in verbs or any(action.startswith(verb) for verb in verbs))
        points += 2 * len(asked & _stems(entity.replace("_", " ")))
        points += len(asked & _stems(description(op)))
        return points

    always = [tools[name] for name in ALWAYS if name in tools]
    ranked = sorted((op for op in tools.values() if op.name not in ALWAYS), key=lambda op: (-score(op), op.name))
    return [*always, *ranked][:MAX_TOOLS]


@cache
def _schema(op: Operation) -> dict:
    return op.input.model_json_schema()


def tool_spec(op: Operation) -> dict:
    """``op`` as the gateway takes a tool (OpenAI's ``function``)."""
    return {"type": "function", "name": tool_name(op.name), "description": description(op), "parameters": _schema(op)}


# ── The card of a write (BASE-G115, G116) ────────────────────────────────────────────────────────────────────────


def _resolved(prop: dict, defs: dict) -> dict:
    for branch in prop.get("anyOf", []):
        if branch.get("type") != "null":
            return _resolved({**branch, **{k: v for k, v in prop.items() if k != "anyOf"}}, defs)
    ref = prop.get("$ref")
    return {**defs.get(ref.rsplit("/", 1)[-1], {}), **prop} if ref else prop


def _is_money(name: str, prop: dict) -> bool:
    return name.endswith("_cents") or "in cents" in str(prop.get("description", "")).lower()


def _generated_title(name: str) -> str:
    """The title pydantic makes up for a field without one (``closing_balance`` → «Closing Balance»)."""
    return name.title().replace("_", " ").strip()


def _in_code_language() -> bool:
    """Whether the active language is the one the code's texts are written in (and fall back to): English."""
    return (translation.get_language() or settings.LANGUAGE_CODE).split("-")[0] == settings.LANGUAGE_CODE.split("-")[0]


@cache
def _verbose_name(app_label: str, entity: str, name: str) -> Any:
    """The name the models of the app ``app_label`` give their field ``name`` (lazy: said in the active language), the
    model of the operation's ``entity`` first — another may mean something else by it —, or ``None``. Their metadata
    only: no query."""
    config = active_apps_label(app_label)
    if config is None:
        return None
    own = entity.replace("_", "")
    models = sorted(config.get_models(), key=lambda model: not model._meta.model_name.endswith(own))
    for model in models:
        try:
            verbose = getattr(model._meta.get_field(name), "verbose_name", None)
        except FieldDoesNotExist:
            continue
        if verbose:
            return verbose
    return None


def _label(op: Operation, name: str, title: str | None) -> str:
    """How the card names the datum ``name``, in the active language and never by a technical name (gh:hub#1040): by the
    title its schema gives it when a catalog translates it, or as written when the person reads the code's language;
    else by the name its app's models give that field, the one its screens show; else by its title, through the
    catalogs. One way for every app: nothing to list here by hand."""
    if title and title != _generated_title(name):
        translated = gettext(title)
        if translated != title or _in_code_language():
            return translated
    verbose = _verbose_name(op.app_label, op.name.split(".")[1], name)
    if verbose is not None:
        return capfirst(str(verbose))
    return gettext(title or _generated_title(name))


def _field(name: str, label: str, prop: dict, value: Any) -> dict:
    if value is None or value == "" or value == []:
        kind = "empty"
    elif isinstance(value, bool):
        kind = "bool"
    elif isinstance(value, int) and _is_money(name, prop):
        kind = "money"
    elif isinstance(value, list):
        kind = "list"
    elif isinstance(value, dict):
        kind = "object"
    else:
        kind = "text"
    return {"name": name, "label": label, "kind": kind, "value": value}


def card(op: Operation, arguments: dict, language: str) -> dict:
    """What the person sees before ``op`` runs with ``arguments``: its app, its action, each datum it sends by its name
    in ``language`` (``_label``; an amount in cents marked ``money``), its risk and, for a dangerous one, what to type
    (``confirm_word``) — how many records when it names them by ``ids``, and ``blocked`` when it names none (not from
    the chat)."""
    schema = _schema(op)
    defs = schema.get("$defs", {})
    props = schema.get("properties", {})
    level = risk(op)
    count: int | None = None
    blocked = False
    if level == "high" and _resolved(props.get("ids", {}), defs).get("type") == "array":
        ids = arguments.get("ids")
        if isinstance(ids, list) and ids:
            count = len(ids)
        else:
            blocked = True
    with translation.override(language):
        fields = [
            # The title of the property itself: a ``$ref``'s own is its schema class's name.
            _field(name, _label(op, name, prop.get("title")), _resolved(prop, defs), arguments[name])
            for name, prop in props.items()
            if name in arguments
        ]
        word = str(count) if count else str(CONFIRM_WORD)
        app = app_name(op)
    return {
        "operation": op.name,
        "app": op.app_label,
        "app_name": app,
        "action": op.name.rsplit(".", 1)[-1],
        "risk": level,
        "fields": fields,
        "count": count,
        "confirm_word": word if level == "high" else "",
        "blocked": blocked,
    }


def active_apps_label(label: str) -> LiveAppConfig | None:
    return next((config for config in all_live_app_configs() if config.label == label), None)


# The screens of the platform, as its menu and the assistant's instructions name them.
HOME = pgettext_lazy("base", "Home")
EMPLOYEES = pgettext_lazy("base", "Employees")
SETTINGS = pgettext_lazy("base", "Settings")
PROFILE = pgettext_lazy("base", "My profile")
SYSTEM = pgettext_lazy("base", "System")
FILES = pgettext_lazy("base", "Files")

#: Where a person does each thing of the platform on their own, by the entity of its operation: a card or a receipt
#: names an action of base by that screen, never by the platform's internal name, «Base» (as Shopify's Sidekick and
#: Business Central's Copilot name the page of an action, and WooCommerce's assistant its area). Every tool of base and
#: what is never done from the chat has its entity here (``test_every_action_of_base_names_its_screen``).
BASE_SCREENS = {
    "access": SETTINGS,
    "api_doc": SETTINGS,
    "api_key": EMPLOYEES,
    "approval": EMPLOYEES,
    "blueprint": SETTINGS,
    "business": SETTINGS,
    "dataset": SETTINGS,
    "device": SETTINGS,
    "event": SYSTEM,
    "failed_event": SYSTEM,
    "file": FILES,
    "hub": SETTINGS,
    "import": SETTINGS,
    "location": SETTINGS,
    "person": EMPLOYEES,
    "profile": PROFILE,
    "role": EMPLOYEES,
    "setup": HOME,
    "system": SYSTEM,
}


def app_name(op: Operation) -> str:
    """Where ``op`` happens, as the person knows it, in the active language: its app by its name; one of the platform,
    the screen where they would do it themselves (``BASE_SCREENS``; another, the Home)."""
    if op.app_label == "base":
        return str(BASE_SCREENS.get(op.name.split(".")[1], HOME))
    config = active_apps_label(op.app_label)
    return str(config.verbose_name) if config is not None else op.app_label


def confirmed(card_: dict, typed: str) -> bool:
    """Whether ``typed`` is what the card asks, as the platform's ``ConfirmDialog`` compares it (``@erplora/ui``: spaces
    around and case ignored, accents not); a normal write asks nothing; a blocked one, never."""
    word = card_["confirm_word"]
    return not card_["blocked"] and (word == "" or typed.strip().casefold() == word.casefold())


# ── A tool, run as the person (BASE-G115, G118) ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ToolOutcome:
    """``outcome``: ``ok``, ``error`` (the operation refused the data or the state: the model tells it), ``refused``
    (the person may not: no permission, the app off, a manager's approval) or ``cancelled`` (the person said no)."""

    outcome: str
    code: str
    content: str


def error_content(code: str, message: str, fields: dict | None = None) -> str:
    error: dict[str, Any] = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return json.dumps({"error": error}, ensure_ascii=False)


def run_tool(ctx: OperationContext, op: Operation, arguments: str) -> ToolOutcome:
    """Run ``op`` with the model's ``arguments`` (JSON text) for ``ctx``'s person, by its own operation."""
    try:
        data = json.loads(arguments or "{}")
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return ToolOutcome("error", "invalid_payload", error_content("invalid_payload", "The arguments are not a JSON object."))
    try:
        validated = op.input.model_validate(data)
    except pydantic.ValidationError as exc:
        fields = {".".join(str(part) for part in error["loc"]) or "__all__": error["msg"] for error in exc.errors()}
        return ToolOutcome("error", "invalid_payload", error_content("invalid_payload", "Some data does not fit.", fields))
    try:
        result = op(ctx, validated)
    except (PermissionDenied, AppInactive, Unauthorized) as exc:
        return ToolOutcome("refused", exc.code, error_content(exc.code, str(exc)))
    except OperationError as exc:
        return ToolOutcome("error", exc.code, error_content(exc.code, str(exc), getattr(exc, "fields", None)))
    content = result.model_dump_json()
    if len(content) > MAX_RESULT_CHARS:
        content = content[:MAX_RESULT_CHARS] + " …(cut)"
    return ToolOutcome("ok", "", content)


def rounds(messages: list[dict]) -> int:
    """The rounds of tools since the person's last message: the model's messages that asked for tools."""
    count = 0
    for message in reversed(messages):
        if message.get("role") == "user":
            break
        if message.get("role") == "assistant" and message.get("tool_calls"):
            count += 1
    return count


# ── The instructions of a turn ───────────────────────────────────────────────────────────────────────────────────


def instructions(*, language: str, currency: str, business: str, screens: dict[str, str]) -> str:
    """The system message of every turn (the gateway's only one): who it serves, in which language, the rules of its
    tools and money, and the screens it may link."""
    try:
        language_name = get_language_info(language)["name"]
    except KeyError:
        language_name = language
    links = "\n".join(f"- [{name}]({path})" for path, name in screens.items())
    return f"""You are the assistant of the business «{business}» in ERPlora, its point of sale and management app.
Answer in {language_name}, short and plain, as a colleague who knows the app. Use Markdown: bold, lists and tables.

- Only help with this business and with using ERPlora. To anything else (films, general knowledge, other software),
  say kindly that you only help with the business, in one sentence, and do not answer it.
- Read before you answer: use the tools to look up records, numbers and ids. Never invent a record, an id, an amount
  or a date: if no tool returned it, say you do not know or that you could not find it.
- To change something, call its tool: the person sees a card and confirms it before it runs. If the tool comes back
  «not confirmed» or with an error, nothing changed: say so, and never say it was done.
- Amounts: fields «in cents» take whole cents (17.00 {currency} → 1700). To the person, always write amounts in
  {currency} with two decimals (17.00), never in cents.
- When the person should go to a screen, link it with its path, only one of these:
{links}
- If something cannot be done from here (you have no tool for it), say on which screen it is done."""


def setup_block(status: dict | None) -> str:
    """The checklist «Finish setting up your business» as the model reads it (BASE-G121): what is pending, what
    blocks invoicing, what is done, and what only an administrator can do. ``None``: it could not be read."""
    if status is None:
        return "The checklist of this business could not be read now: do not say the business is set up."
    lines = [
        "The person is setting up the business. Its checklist «Finish setting up your business», read now "
        f"({status['total'] - status['pending'] - status['unavailable']} of {status['total']} done):"
    ]
    for item in status["items"]:
        state = item["state"]
        if state == "done":
            lines.append(f"- Done: {item['title']}.")
            continue
        if state == "unavailable":
            lines.append(f"- Not available yet (nothing to do): {item['title']}.")
            continue
        needed = " Needed to invoice." if item["level"] == "legal" else ""
        who = "" if item["actionable"] else " Only an administrator of the business can do it."
        lines.append(f"- Pending: {item['title']} — {item['description']} Screen: {item['route']}.{needed}{who}")
    lines.append("This list is complete: never add a step that is not in it.")
    return "\n".join(lines)


# ── The gateway (erplora.com) ────────────────────────────────────────────────────────────────────────────────────


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


def _post(path: str, payload: dict) -> dict:
    url, body, headers = _signed(path, payload)
    try:
        response = httpx.post(url, content=body, headers=headers, timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError:
        raise GatewayError("assistant.unreachable") from None
    try:
        answer = response.json()
    except ValueError:
        answer = None
    if response.status_code >= 300:
        error = _error_of(response.status_code, answer)
        raise GatewayError(str(error.get("code") or "assistant.unavailable"), response.status_code, error)
    return answer if isinstance(answer, dict) else {}


def usage(scope: Scope) -> dict:
    """This month's allowance of the business: ``{used, limit, resets_at, demo}`` as erplora.com counts it."""
    answer = _post(USAGE_PATH, {"hub": scope.key})
    return {key: answer.get(key) for key in ("used", "limit", "resets_at", "demo")}


def report(scope: Scope, *, message_id: str, reason: str, comment: str, question: str, answer: str) -> dict:
    """Send erplora.com a bad answer of the assistant: ``{sent, duplicate}``."""
    sent = _post(
        REPORT_PATH,
        {"hub": scope.key, "message_id": message_id, "reason": reason, "comment": comment, "question": question, "answer": answer},
    )
    return {"sent": bool(sent.get("sent")), "duplicate": bool(sent.get("duplicate"))}


def transcribe(scope: Scope, *, audio: str, mime_type: str, language: str) -> dict:
    """The text of a dictation (``audio`` in base64): ``{text, language}``."""
    answer = _post(TRANSCRIBE_PATH, {"hub": scope.key, "audio": audio, "mime_type": mime_type, "language": language})
    return {"text": str(answer.get("text") or ""), "language": str(answer.get("language") or language)}


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


async def stream_turn(
    scope: Scope, *, messages: list[dict], tools: list[dict], instructions: str, continuation: str | None
) -> AsyncIterator[dict]:
    """A turn through the gateway, as the Hub's frames: ``text`` piece by piece, ``usage``, an ``error``, and ``done``
    with what the browser keeps (``append``), the tools the model asked for (``pending``) and their ``continuation``.
    A refusal of the gateway is a lone ``error``; a failure half way keeps what was said."""
    payload = {"hub": scope.key, "messages": messages, "instructions": instructions, "tools": tools}
    if continuation:
        payload["continuation"] = continuation
    url, body, headers = _signed(TURN_PATH, payload)
    text: list[str] = []
    calls: list[dict] = []
    token: str | None = None
    finished = failed = False
    try:
        async with httpx.AsyncClient(timeout=TURN_TIMEOUT) as client:
            async with client.stream("POST", url, content=body, headers=headers) as response:
                if response.status_code != 200:
                    await response.aread()
                    try:
                        error = _error_of(response.status_code, response.json())
                    except ValueError:
                        error = {}
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
                    elif kind == "usage":
                        yield {"type": "usage", **{key: frame.get(key) for key in ("used", "limit", "resets_at", "demo")}}
                    elif kind == "error":
                        failed = True
                        yield {"type": "error", "code": "assistant.provider_failed", "retriable": bool(frame.get("retriable"))}
    except httpx.HTTPError:
        if not text and not calls:
            yield {"type": "error", "code": "assistant.unreachable", "retriable": True}
            return
        failed = True
        yield {"type": "error", "code": "assistant.cut", "retriable": True}
    if not finished and not failed:
        failed = True
        yield {"type": "error", "code": "assistant.cut", "retriable": True}
    said = "".join(text)
    if failed:
        yield {"type": "done", "append": [_assistant_message(said, [])] if said else [], "pending": [], "continuation": None}
        return
    yield {"type": "done", "append": [_assistant_message(said, calls)], "pending": calls, "continuation": token}


async def turn_frames(scope: Scope, plan: dict) -> AsyncIterator[bytes]:
    """The answer of ``base.assistant.turn`` (``plan``, the operation's output) as the panel reads it: what ran
    (``executed``), then the card of a write that waits (``confirm``), why it stops (``assistant.too_many_steps``) or
    the gateway's turn; the closing ``done`` always carries the tools' results to keep before the model's message."""
    for row in plan["executed"]:
        yield sse({"type": "executed", **row})
    if plan["confirm"] is not None:
        yield sse({"type": "confirm", "card": plan["confirm"], "call": plan["pending"][0]})
        yield sse({"type": "done", "append": plan["append"], "pending": plan["pending"], "continuation": plan["continuation"]})
        return
    if plan["stop"]:
        yield sse({"type": "error", "code": plan["stop"]})
        yield sse({"type": "done", "append": plan["append"], "pending": [], "continuation": None})
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
        yield sse({"type": "done", "append": plan["append"], "pending": [], "continuation": None})


def turn_response(request: Any, plan: dict) -> StreamingHttpResponse:
    """The streamed answer of a turn: never cached nor held by a proxy, read by the panel piece by piece."""
    scope = HostScopeResolver().resolve(request)
    response = StreamingHttpResponse(turn_frames(scope, plan), content_type="text/event-stream; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
