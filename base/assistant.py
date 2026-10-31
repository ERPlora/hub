"""The Hub's assistant (APP-BASE-9; PLAN §30, ronda 2026-10-22b): chat and voice in the Hub against erplora.com's AI
gateway (``saas`` ``assistant/internal.py``), without the ORM.

The mechanics that do not depend on the gateway are ``live.assistant``'s, shared with the SaaS's panel
(docs/plans/2026-10-30-asistente-saas.md §2) and re-exported here; this module gives them the Hub's own:

- **Its tools** (``catalog``) are the operations of the apps on in this business (``active_apps``: its right and its
  switch) that this person may run, by their ``ai=`` (``live.assistant.is_tool``: an ``AI``; ``INTERNAL``, a «Not an
  assistant tool»/«System only» dictionary or one on what only the platform runs never), never the assistant's own
  nor what is never done from the chat (``NOT_FROM_CHAT``: emptying the business, a file to download). A write a
  manager may approve is theirs too (``approvals``). A turn offers only the few of what was asked (``relevant``, with
  ``ALWAYS`` first).
- **A write never runs without the person's yes**: its card (``card``) says each datum in the Hub's words
  (``_Words``) — a moment as their language writes it (CLDR, as the screens' ``formatDateTime``), at the business's
  hour; a record by its name, as the read its schema marks answers it to them (``REFERS``), or not at all: never by
  its id; an amount in the currency the write names (``CURRENCY``) or the business's —; ``risk="high"`` asks to type
  a word in the person's language (``CONFIRM_WORD``) or, over records named by ``ids``, how many. Its preview
  (``preview``) says the amounts of its read in the currency it answers. A platform action is named by the screen
  where the person would do it (``screen``, ``app_name``).
- **The gateway**: every door is a signed POST (``base.signing``, the secret of every ``/internal`` call) naming this
  business by its host (``scope.key``); the browser never talks to it. ``stream_turn`` relays a turn as the Hub's own
  frames (``text``, ``usage``, ``error``, ``done``); its refusals become one of ours (``assistant.quota_exceeded``,
  ``assistant.unavailable``…), and what never reached it is ``assistant.unreachable``.
"""

import contextlib
import dataclasses
import datetime as dt
import json
import time
from contextvars import ContextVar
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import pydantic
import pycountry
from asgiref.sync import sync_to_async
from babel.dates import format_date, format_time, get_datetime_format
from django.conf import settings
from django.core import checks
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.translation import get_language_info, pgettext_lazy
from live import assistant as shared

# Re-exported: the Hub's services, routes, apps and tests read the shared mechanics here, as always.
from live.assistant import (
    LEFT_OUT,
    MAX_ROUNDS,
    MAX_TOOLS,
    REFERS,
    ToolOutcome,
    confirmed,
    description,
    error_content,
    named,
    operation_of,
    preview_of,
    refers_of,
    risk,
    rounds,
    run_tool,
    tool_name,
    tool_spec,
)
from live.context import OperationContext, Scope, get_builder
from live.errors import Conflict, OperationError
from live.meta import LiveAppConfig, all_live_app_configs
from live.operations import Operation, get, registry

from base import activation, approvals, entitlement, signing
from base.auth import saas_internal_url
from base.business import babel_locale, currency_decimals
from base.operations import HostScopeResolver

# The card's helpers by the names this module and the apps' tests have always read them by (``live.assistant``'s).
_LEFT_OUT = LEFT_OUT
_choice_label = shared.choice_label
_field = shared.field
_generated_title = shared.generated_title
_is_money = shared.is_money
_is_signed = shared.is_signed
_label = shared.label
_output_schema = shared.output_schema
_own_title = shared.own_title
_resolved = shared.resolved
_run = shared.run
_schema = shared.input_schema
_sends_amount = shared.sends_amount
_verbose_name = shared.verbose_name

#: The search in ERPlora's documentation (saas ASSISTANT-F28): how ERPlora works is answered from it, never from memory.
DOCS_SEARCH = "base.docs.search"
#: Always offered when the person may read them: the checklist, the business's own data and the documentation (a
#: how-to question, «¿cómo abro la caja?», shares no word with its tool).
ALWAYS = ("base.setup.status", "base.business.get", DOCS_SEARCH)
#: Never from the chat (the old hub's «destructive actions of the hub itself»): emptying the business; a file.
NOT_FROM_CHAT = frozenset({"base.hub.reset", "base.blueprint.export"})

TURN_PATH = "/internal/assistant/chat/stream"
USAGE_PATH = "/internal/assistant/usage"
REPORT_PATH = "/internal/assistant/report"
DOCS_PATH = "/internal/assistant/docs/search"
TRANSCRIBE_PATH = "/internal/speech/transcribe"
#: A door that answers at once; the turn waits longer for its model, piece by piece.
TIMEOUT_SECONDS = 15
TURN_TIMEOUT = httpx.Timeout(15.0, read=120.0)


# ── Tools ────────────────────────────────────────────────────────────────────────────────────────────────────────


def is_tool(op: Operation) -> bool:
    """Whether ``op`` is a tool of the Hub's assistant: its ``ai=`` says so (``live.assistant.is_tool``) and it is
    neither done never from the chat (``NOT_FROM_CHAT``) nor the assistant's own."""
    return shared.is_tool(op, not_from_chat=NOT_FROM_CHAT) and not op.name.startswith("base.assistant.")


def active_apps(scope: Scope) -> dict[str, LiveAppConfig]:
    """The apps on in ``scope``'s business: every app of ours but the paid ones it has no right to and the ones it
    turned off (``base.activation``)."""
    left_out = entitlement.blocked_apps(scope) | activation.off_apps(scope)
    return {config.label: config for config in all_live_app_configs() if config.label not in left_out}


def catalog(ctx: OperationContext) -> dict[str, Operation]:
    """The tools of ``ctx``'s person: by name, in name order. A write a manager may approve is theirs too, as its
    button on the screen is (APP-BASE-5): running it asks for the approval (BASE-G118)."""
    tools = shared.catalog(
        ctx,
        active_labels=active_apps(ctx.scope),
        not_from_chat=NOT_FROM_CHAT,
        approvable=lambda op: approvals.label_of(op) is not None,
    )
    return {name: op for name, op in tools.items() if is_tool(op)}


def relevant(tools: dict[str, Operation], texts: Iterable[str], language: str) -> list[Operation]:
    """The tools of what ``texts`` ask, best first, at most ``MAX_TOOLS`` (``live.assistant.relevant``): ``ALWAYS``
    first."""
    return shared.relevant(tools, texts, language, always=ALWAYS)


# ── The card of a write in the Hub's words (BASE-G115, G116) ─────────────────────────────────────────────────────

#: The mark of the datum that names the currency of the amounts beside it, at any depth below it: a payment in dollars.
#: ``True`` on a text, an ISO 4217 code; on a datum that names a record in a currency of its own (a cart, a price list),
#: the read of its app that answers it — ``{"read": "<a query>", "by": "<its input>", "code": "<the datum of its
#: answer that gives the currency>"}`` (``base.schemas.in_currency_of``) —, run as the person, as a record's name
#: (``REFERS``). Without one, or empty, the business's. As Stripe, Square or Shopify show an amount: in the currency of
#: its operation, with that currency's decimals. ``base.E011`` checks it at start.
CURRENCY = "currency"


def _named_currency(value: Any, props: dict, defs: dict, words: "_Words") -> tuple[bool, str | None]:
    """The currency the first datum its schema marks ``CURRENCY`` among ``props`` that ``value`` (an object) sends
    names — as the writes take a code (``_currency_code``), or as its record's read answers it to the person
    (``_record_currency``) —: ``(True, <code>)``; ``(True, None)`` when none names one (no such datum, or empty: the
    business's); ``(False, None)`` when it names one that is none, or a record whose currency cannot be read (not there,
    not theirs to read, no person at hand), which its write refuses or decides: its amounts are said as sent, never in
    a currency made up. A record is read only when ``value`` sends an amount."""
    if not isinstance(value, dict):
        return True, None
    for name, prop in props.items():
        declared = _resolved(prop, defs).get(CURRENCY)
        sent = value.get(name)
        if sent is None or sent == "":
            continue
        if declared is True:
            return _currency_code(sent)
        if isinstance(declared, dict):
            if not _sends_amount(value, {"properties": props}, defs, ""):
                return True, None
            _, code = _currency_code(_record_currency(sent, declared, words))
            return (True, code) if code else (False, None)
    return True, None


def _currency_code(sent: Any) -> tuple[bool, str | None]:
    """``sent`` as the writes take a currency — spaces and case aside, an ISO 4217 code —: ``(True, <code>)``;
    ``(True, None)`` when empty; ``(False, None)`` when it is none: a code no currency has, or no text at all (a
    number), which the write refuses as well — never the business's in its place."""
    if sent is not None and not isinstance(sent, str):
        return False, None
    code = sent.strip().upper() if isinstance(sent, str) else ""
    if not code:
        return True, None
    known = len(code) == 3 and pycountry.currencies.get(alpha_3=code) is not None
    return (True, code) if known else (False, None)


def _record_currency(sent: Any, declared: dict, words: "_Words") -> Any:
    """The currency the read ``declared`` answers to the person for the record ``sent`` names (``CURRENCY``), or
    ``None``: no person at hand (an automation's card reads nothing for somebody else) or a read that fails."""
    read = registry.get(declared.get("read"))
    if read is None or words.ctx is None:
        return None
    failure, answer = _run(words.ctx, read, {declared.get("by"): sent})
    return None if failure is not None else answer.model_dump(mode="json").get(declared.get("code"))


@dataclass
class _Words:
    """The Hub's words of a card (``live.assistant.Words``): the person's language and the person (``ctx``: to read a
    record's name and its currency as them, and the business's zone; ``None`` for an automation's card, which reads no
    record); ``currency``, the one its amounts are in when it is not the business's (the one a write names, the one of
    the record it names, or a preview's read answers, with the decimals it answers: ``answered``); ``priced`` false
    when the write names one that is none, or a record whose currency cannot be read: its amounts go as sent."""

    op: Operation
    language: str
    ctx: OperationContext | None
    currency: str | None = None
    priced: bool = True
    answered: dict | None = None
    _business: Any = None

    @classmethod
    def of_answer(cls, read: Operation, ctx: OperationContext, answer: dict) -> "_Words":
        """The words of a preview's read: in the currency it answers (``_answer_money``), else the business's."""
        money = _answer_money(answer)
        return cls(read, ctx.language, ctx, currency=money["currency"] if money else None, answered=money)

    def within(self, value: Any, props: dict, defs: dict) -> "_Words":
        """The words of the data of the object ``value``: in the currency it names (``CURRENCY``), else in this one."""
        priced, currency = _named_currency(value, props, defs, self)
        if priced and currency is None:
            return self
        return dataclasses.replace(self, currency=currency, priced=priced, answered=None)

    def _currency_money(self) -> dict | None:
        return {"currency": self.currency, "decimals": currency_decimals(self.currency)} if self.currency else None

    def money(self) -> dict | None:
        """The currency of its amounts as the card's screen takes it, when it is not the business's: as a preview's
        read answers it, else as the currency says it."""
        return self.answered if self.answered is not None else self._currency_money()

    def business(self) -> Any:
        """Settings › Business, read as the person once per card and only when a datum needs it; ``False`` when it
        cannot be read (no person at hand, or a refusal)."""
        if self._business is None:
            failure, answer = (True, None) if self.ctx is None else _run(self.ctx, registry["base.business.get"], {})
            self._business = answer if failure is None else False
        return self._business

    def zone(self) -> Any:
        """The business's zone or else the deployment's, the one every app reads a wall-clock time in."""
        business = self.business()
        return (_zone_named(business.timezone) if business else None) or timezone.get_current_timezone()

    def amount(self, value: int) -> Any:
        """``value``, an amount in the minor unit of its currency, as the card's screen writes one on top
        (``{"kind": "money", "value": …}``, with its ``money`` when it is in a currency of its own): every amount of a
        card in one format, the screen's, nested or not; as sent when its write names a currency that is none."""
        if not self.priced:
            return value
        money = self._currency_money()
        return {"kind": "money", "value": value, **({"money": money} if money else {})}

    def moment(self, value: str, kind: str) -> str | None:
        return _moment(value, kind, self)

    def reference(self, value: Any, prop: dict) -> Any:
        return _reference(value, prop, self)

    def app_name(self) -> str:
        return app_name(self.op)


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
    said = answer.model_dump(mode="json")
    names = [said.get(field) for field in _names(declared)]
    return next((name for name in names if isinstance(name, str) and name.strip()), _LEFT_OUT)


def _names(declared: dict) -> list:
    """The data of the read's answer that name the record, in the order the mark gives them."""
    name = declared.get("name")
    return [name] if isinstance(name, str) else name if isinstance(name, list) else []


def card(op: Operation, arguments: dict, language: str, ctx: OperationContext | None = None) -> dict:
    """What the person sees before ``op`` runs with ``arguments`` (``live.assistant.card``), in the Hub's words: a
    moment at the business's hour, a record by its name read as ``ctx``'s person, an amount in the currency the write
    names (``CURRENCY``) or the business's; its app by its name, a platform action by its screen (``app_name``)."""
    return shared.card(op, arguments, language, _Words(op, language, ctx))


def active_apps_label(label: str) -> LiveAppConfig | None:
    return shared.config_of(label)


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
#: ERPlora's documentation (``base.docs.search``), as the panel of erplora.com names its receipt: no screen of the Hub.
HELP = pgettext_lazy("base", "Help")

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
    "help": HELP,
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
    # The shared image library opens from the form of a product, a service or a menu: no screen of the platform.
    "catalog_image": "home",
    "dataset": "settings",
    "device": "settings",
    "docs": "help",
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

# ── What a dangerous write will do, on its card (BASE-F98) ───────────────────────────────────────────────────────


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
    """What the dangerous write ``op`` will do with ``arguments`` (``live.assistant.preview``: the read its ``ai=``
    names, run as ``ctx``'s person), in the Hub's words: its amounts in the currency the read answers
    (``_answer_money``), else the business's; ``signed`` when its schema declares it so. ``base.E005`` checks the
    declaration at start. A record named as the person says it that fits several (``_ambiguous``) is the write's
    outcome instead, with no card: nothing is confirmed blind, and the model asks which one."""
    ambiguous = _ambiguous(ctx, op, arguments)
    if ambiguous is not None:
        return ambiguous, None
    return shared.preview(ctx, op, arguments, words_of_answer=_Words.of_answer)


def _ambiguous(ctx: OperationContext, op: Operation, arguments: dict) -> ToolOutcome | None:
    """Why ``op`` cannot be put on a card yet when a datum of ``arguments`` names its record as the person says it (no
    id) and the read its schema marks (``REFERS``) finds several (``Conflict``: «reserva» is Reservas and Reservas
    online, hub#539); its message names them, in the person's language. ``None`` otherwise: what the read cannot find or
    may not show is the write's own answer, as before."""
    props = shared.input_schema(op).get("properties", {})
    for name, value in arguments.items():
        declared = refers_of(props.get(name, {}))
        read = registry.get(declared.get("read")) if declared else None
        if read is None or not isinstance(value, str) or shared.is_uuid(value):
            continue
        try:
            read(ctx, read.input.model_validate({declared.get("by"): value}))
        except Conflict as exc:
            return ToolOutcome("error", exc.code, error_content(exc.code, str(exc)))
        except (pydantic.ValidationError, OperationError):
            continue
    return None


@checks.register("base")
def check_previews(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """``base.E005``: a preview names a read of the write's own app, the data of its answer the card shows and nothing
    the write does not send; only a dangerous write declares one (a normal one's card is a single line), and only an
    amount (``MONEY``, on a whole number) is declared signed."""
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
        f"marks {name} signed, but it is no amount marked money"
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


def _marks(prop: dict, defs: dict, path: str = "", depth: int = 0, mark: str = REFERS) -> list[tuple[str, Any]]:
    """Each ``mark`` (``REFERS``, else another) of the schema ``prop`` at any depth, with the path of its datum."""
    if depth > 8:  # a schema that names itself
        return []
    ref = prop.get("$ref")
    if ref:
        prop = {**defs.get(ref.rsplit("/", 1)[-1], {}), **{key: inner for key, inner in prop.items() if key != "$ref"}}
    found = [(path, prop[mark])] if mark in prop else []
    for branch in [*prop.get("anyOf", []), *prop.get("oneOf", []), *prop.get("allOf", [])]:
        found += _marks(branch, defs, path, depth + 1, mark)
    for name, inner in prop.get("properties", {}).items():
        found += _marks(inner, defs, f"{path}.{name}" if path else name, depth + 1, mark)
    if isinstance(prop.get("items"), dict):
        found += _marks(prop["items"], defs, f"{path}[]", depth + 1, mark)
    return found


@checks.register("base")
def check_currencies(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """``base.E011``: a datum marked ``CURRENCY`` is a code (``True``) or names a record by a read of the operation's
    own app, of ``base`` or of one it requires, that takes the datum (``by``) and answers its currency (``code``)."""
    errors: list[checks.CheckMessage] = []
    for op in registry.values():
        schema = _schema(op)
        problems = [
            f"{path} {problem}"
            for path, declared in _marks(schema, schema.get("$defs", {}), mark=CURRENCY)
            for problem in _currency_problems(op, declared)
        ]
        if problems:
            errors.append(
                checks.Error(
                    f"{op.name} marks a currency that {'; '.join(problems)}.",
                    hint='Mark a code json_schema_extra={"currency": True}, or the datum that names a record in a currency '
                    'of its own base.schemas.in_currency_of("<app>.<entity>.<a query>", by="<its input>", '
                    'code="<the datum of its answer that gives the currency>").',
                    obj=op.name,
                    id="base.E011",
                )
            )
    return errors


def _currency_problems(op: Operation, declared: Any) -> list[str]:
    if declared is True:
        return []
    if not isinstance(declared, dict) or not all(isinstance(declared.get(key), str) for key in ("read", "by", "code")):
        return ["is not true nor a read, by and code"]
    return _reference_problems(op, {"read": declared["read"], "by": declared["by"], "name": declared["code"]})


def _reference_problems(op: Operation, declared: Any) -> list[str]:
    if (
        not isinstance(declared, dict)
        or not all(isinstance(declared.get(key), str) for key in ("read", "by"))
        or not _names(declared)
        or not all(isinstance(name, str) for name in _names(declared))
    ):
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
    given = _output_schema(read).get("properties", {})
    problems += [f"names {read.name}, which gives no {name}" for name in _names(declared) if name not in given]
    return problems


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
- For questions about how ERPlora works (how to do something, what an option means, plans), search the documentation
  with `base__docs__search` and answer only from what it returns, citing the section; if it returns nothing, say the
  documentation does not cover it.
- To change something, call its tool: the person sees a card and confirms it before it runs. If the tool comes back
  «not confirmed» or with an error, nothing changed: say so, and never say it was done.
- Amounts: a datum a tool marks `"money": true` takes the amount in the minor unit of its currency, whatever its
  description says: the one a datum marked `"currency": true` beside it names, or the one of the record (a cart, a
  price list) a datum marked `"currency": {{"read": …}}` names, which that read gives; else the business's ({example}). To
  the person, write an amount in the currency its result gives (its `currency`, with `currency_decimals` decimals)
  when it gives one, else in {currency} with {decimals} decimals; never in the minor unit.
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


def docs_language(language: str) -> str:
    """The language of ERPlora's documentation a person reads: Spanish for any Spanish, else English (the two it is
    written in)."""
    return "es" if (language or "").split("-")[0].lower() == "es" else "en"


def docs_search(scope: Scope, *, query: str, language: str, limit: int) -> dict:
    """The excerpts of ERPlora's documentation nearest to ``query``, from erplora.com's one index (saas ASSISTANT-F28),
    in the documentation of ``language``: ``{results: [{source, path, heading, text, score, lang}]}``."""
    return _post(DOCS_PATH, {"hub": scope.key, "query": query, "language": docs_language(language), "limit": limit})


# ── What the turn's tools wait on erplora.com for, before the turn's transaction ─────────────────────────────────

#: The documentation searches of this request's turn, asked before its transaction (``prepare``): by their question
#: and limit, erplora.com's answer or its refusal.
_prepared_docs: ContextVar[dict | None] = ContextVar("base_assistant_prepared_docs", default=None)


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


@contextlib.contextmanager
def prepared_docs(prepared: dict[tuple[str, int], dict | GatewayError]):
    """While inside, ``searched_docs`` reads ``prepared`` instead of asking erplora.com."""
    token = _prepared_docs.set(prepared)
    try:
        yield
    finally:
        _prepared_docs.reset(token)


async def prepare(request: Any, data: Any) -> dict[tuple[str, int], dict | GatewayError]:
    """What the turn's tools wait on erplora.com for, asked before ``base.assistant.turn`` opens its transaction (up to
    ``TIMEOUT_SECONDS`` inside it would hold the hub's connection, PLAN §14.2): the documentation searches the model
    asked for (``prepare_docs``), for the route to hand them to the turn (``prepared_docs``)."""
    name = tool_name(DOCS_SEARCH)
    if not any(call.name == name for call in data.pending):
        return {}
    ctx = await sync_to_async(get_builder().from_request)(request)
    return await sync_to_async(prepare_docs)(ctx, data.pending)


def searched_docs(ctx: OperationContext, *, query: str, limit: int) -> dict:
    """The documentation search of ``base.docs.search``: what this request's turn asked before its transaction
    (``prepare``) or, outside a turn, erplora.com's answer now. ``GatewayError`` when it could not answer."""
    prepared = (_prepared_docs.get() or {}).get((query, limit))
    if prepared is None:
        return docs_search(ctx.scope, query=query, language=ctx.language, limit=limit)
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
