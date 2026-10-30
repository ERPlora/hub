"""The Hub's assistant (APP-BASE-9; PLAN §30, ronda 2026-10-22b): chat and voice in the Hub against erplora.com's AI
gateway (``saas`` ``assistant/internal.py``), without the ORM.

- **Its tools** (``catalog``) are the operations of the apps on in this business that this person may run (the
  operation's own permission), told to the assistant by their ``ai=`` description: never one that says «Not an
  assistant tool» or «System only», one without a permission (the system's), one only the platform runs (a permission
  no app declares, whatever its ``ai=`` says), the assistant's own, nor what is never done from the chat
  (``NOT_FROM_CHAT``: emptying the business, a file to download). A turn offers only the few of
  what was asked (``relevant``, at most ``MAX_TOOLS``), never the whole catalogue. A tool runs as the person, by its
  own operation (``run_tool``): the same permission, transaction and refusals as the button on the screen.
- **A write never runs without the person's yes**: its card (``card``) says what it will send, each datum by its name
  in the person's language (the name its app's models give it: their metadata, no query) and in words — a moment as
  their language writes it, at the business's hour; a value of a closed list by its label; a record by its name, as
  the read its schema marks answers it to them, or not at all: never by its id —; ``risk="high"`` asks
  to type a word in the person's language (``CONFIRM_WORD``) or, over records named by ``ids``, how many; such a write
  that names no record is not done from the chat (``blocked``). Such a write may show what it will do (``preview``):
  a read of its own app its ``ai=`` names, run as the person before the card; one that cannot be read shows no card.
- **The gateway**: every door is a signed POST (``base.signing``, the secret of every ``/internal`` call) naming this
  business by its host (``scope.key``); the browser never talks to it. ``stream_turn`` relays a turn as the Hub's own
  frames (``text``, ``usage``, ``error``, ``done``); its refusals become one of ours (``assistant.quota_exceeded``,
  ``assistant.unavailable``…), and what never reached it is ``assistant.unreachable``.
"""

import datetime as dt
import json
import re
import time
import unicodedata
import uuid
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from functools import cache
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import pydantic
from babel.dates import format_date, format_time, get_datetime_format
from django.conf import settings
from django.core import checks
from django.core.exceptions import FieldDoesNotExist
from django.http import StreamingHttpResponse
from django.utils import timezone, translation
from django.utils.text import capfirst
from django.utils.translation import get_language_info, gettext, pgettext_lazy
from live.context import OperationContext, Scope
from live.errors import AppInactive, OperationError, PermissionDenied, Unauthorized
from live.meta import LiveAppConfig, all_live_app_configs
from live.operations import Operation, registry

from base import activation, approvals, entitlement, signing
from base.auth import saas_internal_url
from base.business import babel_locale, currency_decimals
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


@cache
def declared_permissions() -> frozenset[str]:
    """Every permission an app declares: all the owner and the admin of a business hold, and the most a role is
    given. One no app declares (``<app>.system``, ``system.<app>``: the platform's reactions and scheduled tasks) only
    «*» reaches: a superuser and the system."""
    return frozenset(permission for config in all_live_app_configs() for permission in config.permissions)


def is_tool(op: Operation) -> bool:
    text = description(op)
    return (
        bool(text)
        and op.permission is not None
        # Only the platform runs it, whatever its ``ai=`` says («Platform reaction…»): no tool, even of a superuser.
        and op.permission in declared_permissions()
        and not text.startswith(NOT_A_TOOL)
        and op.name not in NOT_FROM_CHAT
        and not op.name.startswith("base.assistant.")
    )


def active_apps(scope: Scope) -> dict[str, LiveAppConfig]:
    """The apps on in ``scope``'s business: every app of ours but the paid ones it has no right to and the ones it
    turned off (``base.activation``)."""
    left_out = entitlement.blocked_apps(scope) | activation.off_apps(scope)
    return {config.label: config for config in all_live_app_configs() if config.label not in left_out}


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


def _is_signed(prop: dict) -> bool:
    """Whether the schema declares the datum signed (``json_schema_extra={"signed": True}``): an amount that says over
    or short, as Cash register's difference, which the card writes with its sign («+» over)."""
    return prop.get("signed") is True


def _generated_title(name: str) -> str:
    """The title pydantic makes up for a field without one (``closing_balance`` → «Closing Balance»)."""
    return name.title().replace("_", " ").strip()


def _in_code_language() -> bool:
    """Whether the active language is the one the code's texts are written in (and fall back to): English."""
    return (translation.get_language() or settings.LANGUAGE_CODE).split("-")[0] == settings.LANGUAGE_CODE.split("-")[0]


@cache
def _model_fields(app_label: str, entity: str, name: str) -> tuple:
    """The fields ``name`` of the models of the app ``app_label``, the model of the operation's ``entity`` first —
    another may mean something else by it. Their metadata only: no query."""
    config = active_apps_label(app_label)
    if config is None:
        return ()
    own = entity.replace("_", "")
    found = []
    for model in sorted(config.get_models(), key=lambda model: not model._meta.model_name.endswith(own)):
        try:
            found.append(model._meta.get_field(name))
        except FieldDoesNotExist:
            continue
    return tuple(found)


def _verbose_name(app_label: str, entity: str, name: str) -> Any:
    """The name the models of the app ``app_label`` give their field ``name`` (lazy: said in the active language), or
    ``None``."""
    named = (getattr(field, "verbose_name", None) for field in _model_fields(app_label, entity, name))
    return next((verbose for verbose in named if verbose), None)


def _choice_label(app_label: str, entity: str, name: str, value: Any) -> Any:
    """The label the models of the app ``app_label`` give the value ``value`` of their field ``name`` — its
    ``choices``, the ones its screens show (lazy: said in the active language) —, or ``None``."""
    for field in _model_fields(app_label, entity, name):
        labels = dict(getattr(field, "flatchoices", None) or ())
        if value in labels:
            return labels[value]
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


#: What a card shows of a secret instead of its value: the same in every language.
HIDDEN = "••••••••"


def _is_secret(prop: dict) -> bool:
    """Whether the schema declares the datum secret: a password, a certificate, a key (pydantic's ``SecretStr``:
    ``format: password``, ``writeOnly``)."""
    return prop.get("format") == "password" or prop.get("writeOnly") is True


def _hidden(value: Any, prop: dict, defs: dict) -> Any:
    """``value`` with each secret its schema ``prop`` declares, at any depth, as ``HIDDEN``; an empty one hides
    nothing. A card never carries a secret as typed: neither on the screen nor in what the browser receives."""
    if value is None or value == "":
        return value
    ref = prop.get("$ref")
    if ref:
        prop = {**defs.get(ref.rsplit("/", 1)[-1], {}), **{key: inner for key, inner in prop.items() if key != "$ref"}}
    if _is_secret(prop):
        return HIDDEN
    # Each branch of a union hides its own: what any of them declares secret is hidden.
    for branch in [*prop.get("anyOf", []), *prop.get("oneOf", []), *prop.get("allOf", [])]:
        value = _hidden(value, branch, defs)
    if isinstance(value, dict):
        props = prop.get("properties", {})
        extra = prop.get("additionalProperties")
        extra = extra if isinstance(extra, dict) else {}
        return {key: _hidden(inner, props.get(key, extra), defs) for key, inner in value.items()}
    if isinstance(value, list):
        items, prefix = prop.get("items"), prop.get("prefixItems", [])
        items = items if isinstance(items, dict) else {}
        return [_hidden(item, prefix[i] if i < len(prefix) else items, defs) for i, item in enumerate(value)]
    return value


# ── Each datum in words: a moment, a value of a list, a record (FIX-HUB-BASE-ASSISTANT-CARD-SHOWS-RAW-VALUES) ──

#: The mark of a datum that names a record (``json_schema_extra={"refers": {"read": "<a query>", "by": "<its input>",
#: "name": "<the datum of its answer that names it>"}}``): the card names it by that read, run as the person. A datum
#: the schema says is an id (``format: uuid``) without it is left out of the card. ``base.E009`` checks it at start.
REFERS = "refers"

#: The moments a schema declares (``format``), said as the person's language writes them.
MOMENTS = ("date-time", "date", "time")


def refers_of(prop: dict) -> dict | None:
    """The read the schema ``prop`` marks to name its record (``REFERS``), or ``None``."""
    declared = prop.get(REFERS)
    return declared if isinstance(declared, dict) else None


def _is_uuid(value: Any) -> bool:
    """Whether ``value`` is an id as a schema's ``format: uuid`` takes it."""
    try:
        uuid.UUID(value)
    except (TypeError, ValueError, AttributeError):
        return False
    return True


#: What a card leaves out: a record it cannot name.
_LEFT_OUT = object()


@dataclass
class _Words:
    """What a card needs to say ``op``'s data in words: the person's language and the person (``ctx``: to read a
    record's name as them and the business's zone; ``None`` for an automation's card, which names no record)."""

    op: Operation
    language: str
    ctx: OperationContext | None
    _zone: Any = None

    def zone(self) -> Any:
        """The business's zone (Settings › Business, read as the person) or else the deployment's, the one every app
        reads a wall-clock time in; read once per card, only when a moment needs it."""
        if self._zone is None:
            failure, answer = (True, None) if self.ctx is None else _run(self.ctx, registry["base.business.get"], {})
            business = _zone_named(answer.timezone) if failure is None else None
            self._zone = business or timezone.get_current_timezone()
        return self._zone


def _zone_named(name: str) -> ZoneInfo | None:
    """The zone ``name`` (IANA), or ``None`` when Python does not know it."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _moment(value: str, kind: str, words: _Words) -> str | None:
    """``value`` (ISO 8601: a day, a day and a time, or a time) as the person's language writes it — CLDR's medium day
    and short time, as the screens' ``formatDateTime`` (@erplora/ui) says them —; an instant of another zone at the
    business's hour, a wall-clock time as it is (the app books it at the business's hour). ``None``: it is none."""
    locale = babel_locale(words.language)
    try:
        if kind == "date":
            return format_date(dt.date.fromisoformat(value), "medium", locale=locale)
        if kind == "time":
            return format_time(dt.time.fromisoformat(value).replace(tzinfo=None), "short", locale=locale)
        moment = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(words.zone()).replace(tzinfo=None)
    day, hour = format_date(moment.date(), "medium", locale=locale), format_time(moment.time(), "short", locale=locale)
    return get_datetime_format("medium", locale=locale).replace("{1}", day).replace("{0}", hour)


def _reference(value: Any, prop: dict, words: _Words) -> Any:
    """The name of the record ``value`` names, as the read its schema marks (``REFERS``) answers it to the person; or
    ``_LEFT_OUT`` — no mark, no person at hand, or a read that fails (not there, not theirs to read, its app off):
    the card names nobody by an id, nor reads anything for somebody else."""
    declared = refers_of(prop)
    read = registry.get(declared.get("read")) if declared else None
    if read is None or words.ctx is None or not isinstance(value, str):
        return _LEFT_OUT
    failure, answer = _run(words.ctx, read, {declared.get("by"): value})
    if failure is not None:
        return _LEFT_OUT
    name = answer.model_dump(mode="json").get(declared.get("name"))
    return name if isinstance(name, str) and name.strip() else _LEFT_OUT


#: The type of a value each JSON Schema type names.
_TYPES = {"object": dict, "array": list, "string": str, "integer": int, "number": int | float, "boolean": bool}


def _fits(value: Any, branch: dict) -> bool:
    """Whether ``value`` has the shape of ``branch``: its type and, an object, no key it does not take and its
    constants (a discriminator, as an automation's trigger ``kind``)."""
    expected = _TYPES.get(branch.get("type", ""))
    if expected is not None and not isinstance(value, expected):
        return False
    if not isinstance(value, dict):
        return True
    props = branch.get("properties", {})
    if branch.get("additionalProperties") is False and not set(value) <= set(props):
        return False
    return all(value[key] == inner["const"] for key, inner in props.items() if key in value and "const" in inner)


def _referred(prop: dict, defs: dict) -> dict:
    """``prop`` with the schema its ``$ref`` names, what it says itself on top."""
    ref = prop.get("$ref")
    if not ref:
        return prop
    return {**defs.get(ref.rsplit("/", 1)[-1], {}), **{key: inner for key, inner in prop.items() if key != "$ref"}}


def _fitting(value: Any, prop: dict, defs: dict, depth: int = 0) -> dict:
    """The schema of ``value`` among the branches of the union ``prop`` declares (``anyOf``, ``oneOf``, one inside
    another as an optional automation's trigger): the first one it fits (``_fits``), with what ``prop`` itself says
    (its title, its marks); ``prop`` resolved when it is no union."""
    prop = _referred(prop, defs)
    branches = [*prop.get("anyOf", []), *prop.get("oneOf", [])]
    if not branches or depth > 8:
        return _resolved(prop, defs)
    outer = {key: inner for key, inner in prop.items() if key not in ("anyOf", "oneOf", "discriminator")}
    for branch in branches:
        branch = _referred(branch, defs)
        if branch.get("type") != "null" and _fits(value, branch):
            return _fitting(value, {**branch, **outer}, defs, depth + 1)
    return _resolved(prop, defs)


def _said(value: Any, prop: dict, defs: dict, name: str, words: _Words) -> Any:
    """``value`` in words as its schema ``prop`` declares it, at any depth: a moment as the person's language writes it
    (``_moment``), a value of a closed list by the label its app's models give it (``_choice_label``), a record by
    its name (``_reference``) or else ``_LEFT_OUT`` — left out of an object, none in a list (which still says how many
    it carries); what is none of them, or not what its schema declares (the write refuses it), as sent."""
    if value is None or value == "":
        return value
    prop = _fitting(value, prop, defs)
    if REFERS in prop or (prop.get("format") == "uuid" and _is_uuid(value)):
        return _reference(value, prop, words)
    if prop.get("format") in MOMENTS and isinstance(value, str):
        said = _moment(value, prop["format"], words)
        return value if said is None else said
    if "enum" in prop and isinstance(value, str | int) and not isinstance(value, bool):
        label = _choice_label(words.op.app_label, words.op.name.split(".")[1], name, value)
        return value if label is None else str(label)
    if isinstance(value, dict):
        props = prop.get("properties", {})
        extra = prop.get("additionalProperties")
        extra = extra if isinstance(extra, dict) else {}
        said = {
            key: _said(inner, props.get(key, extra), defs, key if key in props else name, words) for key, inner in value.items()
        }
        return {key: inner for key, inner in said.items() if inner is not _LEFT_OUT}
    if isinstance(value, list):
        items, prefix = prop.get("items"), prop.get("prefixItems", [])
        items = items if isinstance(items, dict) else {}
        said = [_said(item, prefix[i] if i < len(prefix) else items, defs, name, words) for i, item in enumerate(value)]
        return [None if item is _LEFT_OUT else item for item in said]
    return value


def _field(
    name: str, label: str, prop: dict, defs: dict, value: Any, money: dict | None = None, words: _Words | None = None
) -> dict | None:
    """One datum of a card, as its schema ``prop`` declares it: a secret hidden (``_hidden``) and, with the ``words``
    of its card, the rest in words (``_said``); ``None`` when it names a record the card cannot name. An amount
    carries ``signed`` when its schema declares it so and ``money`` when it is in a currency of its own (a preview's,
    as its read answers it): without it, the card paints it in the business's."""
    value = _hidden(value, prop, defs)
    if words is not None:
        value = _said(value, prop, defs, name, words)
    if value is _LEFT_OUT:
        return None
    prop = _resolved(prop, defs)
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
    field = {"name": name, "label": label, "kind": kind, "value": value}
    if kind == "money" and _is_signed(prop):
        field["signed"] = True
    if kind == "money" and money is not None:
        field["money"] = money
    return field


def card(op: Operation, arguments: dict, language: str, ctx: OperationContext | None = None) -> dict:
    """What the person sees before ``op`` runs with ``arguments``: its app, its action, each datum it sends by its name
    in ``language`` (``_label``) and in words (``_said``: a moment, a value of a list, a record by its name, read as
    ``ctx``'s person; an amount in cents marked ``money``, and ``signed`` when its schema declares it so), its risk
    and, for a dangerous one, what to type (``confirm_word``) — how many records when it names them by ``ids``, and
    ``blocked`` when it names none (not from the chat)."""
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
    words = _Words(op, language, ctx)
    with translation.override(language):
        said = [
            # The title of the property itself: a ``$ref``'s own is its schema class's name.
            _field(name, _label(op, name, prop.get("title")), prop, defs, arguments[name], words=words)
            for name, prop in props.items()
            if name in arguments
        ]
        fields = [field for field in said if field is not None]
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
APPS = pgettext_lazy("base", "Apps")
#: The user menu's «Report a problem» (BASE-F108), a dialog of its own.
REPORT_A_PROBLEM = pgettext_lazy("base", "Report a problem")

#: The platform's screens by their key, the one a receipt names its screen by (``screen``) and base's catalogue names it
#: by in each language (``base.assistant.screens.<key>``, the same name: ``test_each_screen_a_receipt_names_…``).
SCREEN_NAMES = {
    "home": HOME,
    "employees": EMPLOYEES,
    "settings": SETTINGS,
    "profile": PROFILE,
    "system": SYSTEM,
    "files": FILES,
    "apps": APPS,
    "report": REPORT_A_PROBLEM,
}

#: Where a person does each thing of the platform on their own, by the entity of its operation: a card or a receipt
#: names an action of base by that screen, never by the platform's internal name, «Base» (as Shopify's Sidekick and
#: Business Central's Copilot name the page of an action, and WooCommerce's assistant its area). Every tool of base and
#: what is never done from the chat has its entity here (``test_every_action_of_base_names_its_screen``).
BASE_SCREENS = {
    "access": "settings",
    "api_doc": "settings",
    "app": "apps",
    "api_key": "employees",
    "approval": "employees",
    "blueprint": "settings",
    "business": "settings",
    "dataset": "settings",
    "device": "settings",
    "event": "system",
    "failed_event": "system",
    "file": "files",
    "hub": "settings",
    "import": "settings",
    "location": "settings",
    "person": "employees",
    "profile": "profile",
    "role": "employees",
    "setup": "home",
    "support": "report",
    "system": "system",
}


def screen(op: Operation) -> str:
    """The key of the platform's screen where ``op`` happens (``BASE_SCREENS``; another, the Home), or ``""`` for an
    app's: its receipt names it in the language the person reads it in, never in the one of its turn."""
    return BASE_SCREENS.get(op.name.split(".")[1], "home") if op.app_label == "base" else ""


def app_name(op: Operation) -> str:
    """Where ``op`` happens, as the person knows it, in the active language: its app by its name; one of the platform,
    the screen where they would do it themselves (``screen``)."""
    if op.app_label == "base":
        return str(SCREEN_NAMES[screen(op)])
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


def _run(ctx: OperationContext, op: Operation, data: dict) -> tuple[ToolOutcome | None, Any]:
    """``op`` run with ``data`` for ``ctx``'s person, by its own operation: ``(None, its result)``, or why it did not
    run (``(outcome, None)``)."""
    try:
        validated = op.input.model_validate(data)
    except pydantic.ValidationError as exc:
        fields = {".".join(str(part) for part in error["loc"]) or "__all__": error["msg"] for error in exc.errors()}
        return ToolOutcome("error", "invalid_payload", error_content("invalid_payload", "Some data does not fit.", fields)), None
    try:
        return None, op(ctx, validated)
    except (PermissionDenied, AppInactive, Unauthorized) as exc:
        return ToolOutcome("refused", exc.code, error_content(exc.code, str(exc))), None
    except OperationError as exc:
        return ToolOutcome("error", exc.code, error_content(exc.code, str(exc), getattr(exc, "fields", None))), None


def run_tool(ctx: OperationContext, op: Operation, arguments: str) -> ToolOutcome:
    """Run ``op`` with the model's ``arguments`` (JSON text) for ``ctx``'s person, by its own operation."""
    try:
        data = json.loads(arguments or "{}")
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return ToolOutcome("error", "invalid_payload", error_content("invalid_payload", "The arguments are not a JSON object."))
    failure, result = _run(ctx, op, data)
    if failure is not None:
        return failure
    content = result.model_dump_json()
    if len(content) > MAX_RESULT_CHARS:
        content = content[:MAX_RESULT_CHARS] + " …(cut)"
    return ToolOutcome("ok", "", content)


# ── What a dangerous write will do, on its card (BASE-F98) ───────────────────────────────────────────────────────


def preview_of(op: Operation) -> Any:
    """What ``op``'s ``ai=`` declares as its preview (``base.E005`` checks its shape at start), or ``None``."""
    ai = op.ai if isinstance(op.ai, dict) else {}
    return ai.get("preview")


@cache
def _output_schema(op: Operation) -> dict:
    return op.output.model_json_schema()


def _answer_money(answer: dict) -> dict | None:
    """The currency a read answers its amounts in (``currency``, with its ``currency_decimals`` or else that currency's
    own: an invoice's, which keeps the one it was issued in), or ``None``: then the card paints them in the business's."""
    currency = answer.get("currency")
    if not isinstance(currency, str) or not currency:
        return None
    decimals = answer.get("currency_decimals")
    if not isinstance(decimals, int) or isinstance(decimals, bool):
        decimals = currency_decimals(currency)
    return {"currency": currency, "decimals": decimals}


def preview(ctx: OperationContext, op: Operation, arguments: dict) -> tuple[ToolOutcome | None, list[dict] | None]:
    """What the dangerous write ``op`` will do with ``arguments``, as its app says it: the read its ``ai=`` names
    (``"preview": {"operation": <a query of its app>, "fields": [<data of its answer>]}``), run as ``ctx``'s person
    — their permissions, their business — with the data of the write its input takes. The card's data, by their names
    in the person's language and an amount in cents as money (``signed`` when its schema declares it so, as a
    difference; in the currency the read answers, ``_answer_money``, when it answers one), in the order the app names
    them; what the read leaves empty or hides from this person (none: a blind count's expected cash) is not there.
    ``(None, None)`` without a preview; ``(outcome, None)`` when it cannot be read: the write is not confirmed blind."""
    declared = preview_of(op)
    if declared is None:
        return None, None
    read = registry[declared["operation"]]
    failure, result = _run(ctx, read, {name: value for name, value in arguments.items() if name in read.input.model_fields})
    if failure is not None:
        return failure, None
    answer = result.model_dump(mode="json")
    schema = _output_schema(read)
    defs = schema.get("$defs", {})
    props = schema.get("properties", {})
    money = _answer_money(answer)
    words = _Words(read, ctx.language, ctx)
    with translation.override(ctx.language):
        fields = [
            _field(
                name,
                _label(read, name, props[name].get("title")),
                props[name],
                defs,
                answer.get(name),
                money,
                words,
            )
            for name in declared["fields"]
        ]
    return None, [field for field in fields if field is not None and field["kind"] != "empty"]


@checks.register("base")
def check_previews(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """``base.E005``: a preview names a read of the write's own app, the data of its answer the card shows and nothing
    the write does not send; only a dangerous write declares one (a normal one's card is a single line), and only an
    amount in cents is declared signed."""
    errors: list[checks.CheckMessage] = []
    for op in registry.values():
        declared = preview_of(op)
        problems = [] if declared is None else _preview_problems(op, declared)
        if problems:
            errors.append(
                checks.Error(
                    f"{op.name} declares a preview that {'; '.join(problems)}.",
                    hint='Declare ai={"risk": "high", "preview": {"operation": "<app>.<entity>.<a query>", "fields": '
                    '[<data of its answer>]}} on a dangerous write, with a read whose input the write also takes.',
                    obj=op.name,
                    id="base.E005",
                )
            )
    return errors


def _preview_problems(op: Operation, declared: Any) -> list[str]:
    if not isinstance(declared, dict) or not isinstance(declared.get("operation"), str):
        return ["is not an operation and fields"]
    problems = []
    if op.kind != "command" or risk(op) != "high":
        problems.append("is never shown: it is not dangerous (risk high)")
    read = registry.get(declared["operation"])
    if read is None:
        return [*problems, f"names no operation {declared['operation']}"]
    if read.app_label != op.app_label:
        problems.append(f"names {read.name}, of another app")
    if read.kind != "query":
        problems.append(f"names {read.name}, not a read")
    fields = declared.get("fields")
    if not isinstance(fields, list) or not fields or not all(isinstance(name, str) for name in fields):
        return [*problems, "names no field of its answer"]
    schema = _output_schema(read)
    given = schema.get("properties", {})
    problems += [f"shows {name}, but {read.name} gives no field {name}" for name in fields if name not in given]
    shown = {name: _resolved(given[name], schema.get("$defs", {})) for name in fields if name in given}
    problems += [
        f"marks {name} signed, but it is no amount in cents"
        for name, prop in shown.items()
        if _is_signed(prop) and not (prop.get("type") == "integer" and _is_money(name, prop))
    ]
    problems += [
        f"reads {name}, but the write never takes {name}" for name in read.input.model_fields if name not in op.input.model_fields
    ]
    return problems


@checks.register("base")
def check_references(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """``base.E009``: a datum marked ``REFERS`` names a read of the operation's own app, of ``base`` or of one it
    requires, that takes the datum (``by``) and answers the record's name (``name``)."""
    errors: list[checks.CheckMessage] = []
    for op in registry.values():
        schema = _schema(op)
        problems = [
            f"{path} {problem}"
            for path, declared in _marks(schema, schema.get("$defs", {}))
            for problem in _reference_problems(op, declared)
        ]
        if problems:
            errors.append(
                checks.Error(
                    f"{op.name} marks a reference that {'; '.join(problems)}.",
                    hint='Mark it json_schema_extra={"refers": {"read": "<app>.<entity>.<a query>", "by": "<its input>", '
                    '"name": "<the datum of its answer that names the record>"}}.',
                    obj=op.name,
                    id="base.E009",
                )
            )
    return errors


def _marks(prop: dict, defs: dict, path: str = "", depth: int = 0) -> list[tuple[str, Any]]:
    """Each ``REFERS`` mark of the schema ``prop`` at any depth, with the path of its datum."""
    if depth > 8:  # a schema that names itself
        return []
    ref = prop.get("$ref")
    if ref:
        prop = {**defs.get(ref.rsplit("/", 1)[-1], {}), **{key: inner for key, inner in prop.items() if key != "$ref"}}
    found = [(path, prop[REFERS])] if REFERS in prop else []
    for branch in [*prop.get("anyOf", []), *prop.get("oneOf", []), *prop.get("allOf", [])]:
        found += _marks(branch, defs, path, depth + 1)
    for name, inner in prop.get("properties", {}).items():
        found += _marks(inner, defs, f"{path}.{name}" if path else name, depth + 1)
    if isinstance(prop.get("items"), dict):
        found += _marks(prop["items"], defs, f"{path}[]", depth + 1)
    return found


def _reference_problems(op: Operation, declared: Any) -> list[str]:
    if not isinstance(declared, dict) or not all(isinstance(declared.get(key), str) for key in ("read", "by", "name")):
        return ["is not a read, by and name"]
    read = registry.get(declared["read"])
    if read is None:
        return [f"names no operation {declared['read']}"]
    problems = []
    if read.kind != "query":
        problems.append(f"names {read.name}, not a read")
    own = active_apps_label(op.app_label)
    if read.app_label not in {op.app_label, "base", *(own.requires if own else ())}:
        problems.append(f"names {read.name}, of {read.app_label}, which {op.app_label} does not require")
    if declared["by"] not in read.input.model_fields:
        problems.append(f"names {read.name}, which takes no {declared['by']}")
    if declared["name"] not in _output_schema(read).get("properties", {}):
        problems.append(f"names {read.name}, which gives no {declared['name']}")
    return problems


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


def instructions(*, language: str, currency: str, decimals: int, business: str, screens: dict[str, str]) -> str:
    """The system message of every turn (the gateway's only one): who it serves, in which language, the rules of its
    tools and money (an amount in the minor unit of its currency, ``decimals`` the business's; said in the currency
    its result gives, else the business's), and the screens it may link."""
    try:
        language_name = get_language_info(language)["name"]
    except KeyError:
        language_name = language
    links = "\n".join(f"- [{name}]({path})" for path, name in screens.items())
    example = f"{17:.{decimals}f} {currency} → {17 * 10**decimals}"
    return f"""You are the assistant of the business «{business}» in ERPlora, its point of sale and management app.
Answer in {language_name}, short and plain, as a colleague who knows the app. Use Markdown: bold, lists and tables.

- Only help with this business and with using ERPlora. To anything else (films, general knowledge, other software),
  say kindly that you only help with the business, in one sentence, and do not answer it.
- Read before you answer: use the tools to look up records, numbers and ids. Never invent a record, an id, an amount
  or a date: if no tool returned it, say you do not know or that you could not find it.
- To change something, call its tool: the person sees a card and confirms it before it runs. If the tool comes back
  «not confirmed» or with an error, nothing changed: say so, and never say it was done.
- Amounts: fields «in cents» take the amount in the minor unit of the business's currency ({example}). To the
  person, write an amount in the currency its result gives (its `currency`, with `currency_decimals` decimals) when
  it gives one, else in {currency} with {decimals} decimals; never in the minor unit.
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
