"""The card of a write of the Hub's assistant, what the person sees before it runs: a write never runs without their
yes. Its card (``card``) says each datum in the Hub's words (``_Words``) — a moment as their language writes it (CLDR,
as the screens' ``formatDateTime``), at the business's hour; a record by its name, as the read its schema marks answers
it to them (``REFERS``), or not at all: never by its id; an amount in the currency the write names (``CURRENCY``) or
the business's —; ``risk="high"`` asks to type a word in the person's language (``CONFIRM_WORD``) or, over records
named by ``ids``, how many. Its preview (``preview``) says the amounts of its read in the currency it answers. The yes
is for that card (``fingerprint``: what it showed and the ids of the records it read, by its marked data and its
check): drawn again with the yes, a card that changed runs nothing and is shown anew. A platform action is named by the
screen where the person would do it (``screen``, ``app_name``). An operation may replace the detailed fields with its
own summary (``ai={"summary": …}``), computed as the person and in their language.
"""

import dataclasses
import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from typing import Any

import pycountry
from babel.dates import format_date, format_skeleton, format_time, get_datetime_format
from django.utils import translation
from django.utils.translation import pgettext_lazy
from live import assistant as shared
from live.assistant import LEFT_OUT, ToolOutcome, refers_of
from live.context import OperationContext
from live.meta import LiveAppConfig
from live.operations import Operation, registry

from base.business import babel_locale, business_zone, currency_decimals

from . import card_marks

# The card's helpers by the names this module reads them by (``live.assistant``'s).
_LEFT_OUT = LEFT_OUT
_resolved = shared.resolved
_run = shared.run
_sends_amount = shared.sends_amount

#: The mark of the datum that names the currency of the amounts beside it, at any depth below it: a payment in dollars.
#: ``True`` on a text, an ISO 4217 code; on a datum that names a record in a currency of its own (a cart, a price list),
#: the read of its app that answers it — ``{"read": "<a query>", "by": "<its input>", "code": "<the datum of its
#: answer that gives the currency>"}`` (``base.schemas.assistant.in_currency_of``) —, run as the person, as a record's
#: name (``REFERS``). Without one, or empty, the business's. As Stripe, Square or Shopify show an amount: in the currency
#: of its operation, with that currency's decimals. ``base.E011`` checks it at start.
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
            if not _sends_amount(value, {"properties": props}, defs):
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
    record's name and its currency as them; ``None`` for an automation's card, which reads no record); ``currency``, the one its amounts are in when it is not the business's (the one a write names, the one of
    the record it names, or a preview's read answers, with the decimals it answers: ``answered``); ``priced`` false
    when the write names one that is none, or a record whose currency cannot be read: its amounts go as sent;
    ``found``, the ids of the records it read to name them, one list for all its data (hub#1208: what a yes is for);
    ``data``, the object whose data these words say, which a record said by its name inside another is read with
    (``within``, hub#1245)."""

    op: Operation
    language: str
    ctx: OperationContext | None
    currency: str | None = None
    priced: bool = True
    answered: dict | None = None
    found: list = dataclasses.field(default_factory=list)
    data: dict = dataclasses.field(default_factory=dict)

    @classmethod
    def of_answer(cls, read: Operation, ctx: OperationContext, answer: dict) -> "_Words":
        """The words of a preview's read: in the currency it answers (``_answer_money``), else the business's."""
        money = _answer_money(answer)
        return cls(read, ctx.language, ctx, currency=money["currency"] if money else None, answered=money)

    def within(self, value: Any, props: dict, defs: dict) -> "_Words":
        """The words of the data of the object ``value``: in the currency it names (``CURRENCY``), else in this one;
        beside its own data (``data``)."""
        data = value if isinstance(value, dict) else {}
        priced, currency = _named_currency(value, props, defs, self)
        if priced and currency is None:
            return dataclasses.replace(self, data=data)
        return dataclasses.replace(self, currency=currency, priced=priced, answered=None, data=data)

    def _currency_money(self) -> dict | None:
        return {"currency": self.currency, "decimals": currency_decimals(self.currency)} if self.currency else None

    def money(self) -> dict | None:
        """The currency of its amounts as the card's screen takes it, when it is not the business's: as a preview's
        read answers it, else as the currency says it."""
        return self.answered if self.answered is not None else self._currency_money()

    def amount(self, value: int) -> Any:
        """``value``, an amount in the minor unit of its currency, as the card's screen writes one on top
        (``{"kind": "money", "value": …}``, with its ``money`` when it is in a currency of its own): every amount of a
        card in one format, the screen's, nested or not; as sent when its write names a currency that is none."""
        if not self.priced:
            return value
        money = self._currency_money()
        return {"kind": "money", "value": value, **({"money": money} if money else {})}

    def moment(self, value: str, kind: str) -> str | None:
        return moment(value, kind, self.language)

    def reference(self, value: Any, prop: dict) -> Any:
        return _reference(value, prop, self)

    def app_name(self) -> str:
        return app_name(self.op)


def moment(value: str, kind: str, language: str) -> str | None:
    """``value`` (ISO 8601: a day, a day and a time, or a time) as ``language`` writes it — CLDR's medium day and short
    time, as the screens' ``formatDateTime`` (@erplora/ui) says them —; an instant of another zone at the business's
    hour, a wall-clock time as it is (the app books it at the business's hour). ``None``: it is none."""
    locale = babel_locale(language)
    try:
        if kind == "date" and value.startswith("--"):
            # A day without its year (a birthday, as vCard writes it): its day and its month.
            return format_skeleton("MMMMd", dt.date.fromisoformat(f"2000{value[1:]}"), locale=locale)
        if kind == "date":
            return format_date(dt.date.fromisoformat(value), "medium", locale=locale)
        if kind == "time":
            return format_time(dt.time.fromisoformat(value).replace(tzinfo=None), "short", locale=locale)
        moment = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(business_zone()).replace(tzinfo=None)
    day, hour = format_date(moment.date(), "medium", locale=locale), format_time(moment.time(), "short", locale=locale)
    return get_datetime_format("medium", locale=locale).replace("{1}", day).replace("{0}", hour)


def _reference(value: Any, prop: dict, words: _Words) -> Any:
    """The name of the record ``value`` names, as the read its schema marks (``REFERS``) answers it to the person —
    read with the data of its own object the mark names beside it (``within``: a course by its name with its menu,
    hub#1245) —; or ``_LEFT_OUT`` — no mark, no person at hand, or a read that fails (not there, not theirs to read,
    its app off): the card names nobody by an id, nor reads anything for somebody else. Words a person says that it
    cannot read (``as_said``: several fit, none does) are said as said instead. A datum the write does not use,
    because a datum of its own object the mark names came (``unless``: the record's id), is neither read nor shown
    (hub#1250)."""
    declared = refers_of(prop)
    if declared and any(words.data.get(name) not in (None, "") for name in declared.get("unless", ())):
        return _LEFT_OUT
    read = registry.get(declared.get("read")) if declared else None
    as_said = value if declared and declared.get("as_said") is True and isinstance(value, str) else _LEFT_OUT
    if read is None or words.ctx is None or not isinstance(value, str):
        return as_said
    beside = {name: words.data[name] for name in declared.get("within", ()) if words.data.get(name) not in (None, "")}
    failure, answer = _run(words.ctx, read, {**beside, declared.get("by"): value})
    if failure is not None:
        return as_said
    said = answer.model_dump(mode="json")
    words.found.append(said.get("id"))
    names = [said.get(field) for field in _names(declared)]
    return next((name for name in names if isinstance(name, str) and name.strip()), as_said)


def _names(declared: dict) -> list:
    """The data of the read's answer that name the record, in the order the mark gives them."""
    name = declared.get("name")
    return [name] if isinstance(name, str) else name if isinstance(name, list) else []


def _card_details(
    op: Operation, arguments: dict, language: str, ctx: OperationContext | None = None, found: list | None = None
) -> dict:
    return shared.card(op, arguments, language, _Words(op, language, ctx, found=[] if found is None else found))


def card(
    op: Operation, arguments: dict, language: str, ctx: OperationContext | None = None, *, found: list | None = None
) -> dict:
    """What the person sees before ``op`` runs with ``arguments`` (``live.assistant.card``), in the Hub's words: a
    moment at the business's hour, a record by its name read as ``ctx``'s person, an amount in the currency the write
    names (``CURRENCY``) or the business's; its app by its name, a platform action by its screen (``app_name``).
    With ``ctx`` and a callable ``ai["summary"]``, its fields are exactly what that callable returns; it receives
    ``(ctx, arguments, fields) -> list[dict]``, with the detailed fields already in ``language``, and runs in it too.
    ``found`` gathers the ids of the records it read to name them (``fingerprint``). Each datum is said as the write
    takes it, and as its screen says it (``card_marks``)."""
    taken = card_marks.as_taken(op, arguments)
    shown = _card_details(op, taken, language, ctx, found)
    shown["fields"] = card_marks.marked(op, shown["fields"], taken, language)
    summary = op.ai.get("summary") if isinstance(op.ai, dict) else None
    if ctx is None or not callable(summary):
        return shown
    with translation.override(language):
        shown["fields"] = summary(ctx, arguments, shown["fields"])
    return shown


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
    # This month's messages of the assistant, which «Usage and plan» shows.
    "assistant": "system",
    "blueprint": "settings",
    "business": "settings",
    # The shared image library opens from the form of a product, a service or a menu: no screen of the platform.
    "catalog_image": "home",
    "dataset": "settings",
    "device": "settings",
    "docs": "help",
    "help": "help",
    "event": "system",
    "failed_event": "system",
    "file": "files",
    "hub": "settings",
    "import": "settings",
    "location": "settings",
    "person": "employees",
    "plan": "system",
    "profile": "profile",
    "release_note": "system",
    "role": "employees",
    "setup": "home",
    "support": "report",
    "support_access": "settings",
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


def preview(
    ctx: OperationContext, op: Operation, arguments: dict, *, found: list | None = None
) -> tuple[ToolOutcome | None, list[dict] | None]:
    """What comes before the card of the write ``op`` with ``arguments``, run as ``ctx``'s person: first its check
    (``checked``, which adds the id of what it found to ``found``), whose refusal is the write's outcome; then what the
    dangerous write will do (``live.assistant.preview``: the read its ``ai=`` names), in the Hub's words: its amounts
    in the currency the read answers (``_answer_money``), else the business's; ``signed`` when its schema declares it
    so. ``base.E005`` and ``base.E012`` check the declarations at start."""
    refused = checked(ctx, op, arguments, found=found)
    if refused is not None:
        return refused, None
    return shared.preview(ctx, op, arguments, words_of_answer=_Words.of_answer)


def check_of(op: Operation) -> Any:
    """The read ``op``'s ``ai=`` names to check its data before its card (``check``), or the reads, in order; or
    ``None``."""
    declared = op.ai
    return declared.get("check") if isinstance(declared, dict) else getattr(declared, "check", None)


def checked(
    ctx: OperationContext, op: Operation, arguments: dict, *, found: list | None = None
) -> ToolOutcome | None:
    """Why the first of the reads the write ``op`` names as its check (``check_of``) that refuses ``arguments`` does
    — each run as ``ctx``'s person, with the data of the write its input takes —, or ``None`` when all of them take
    them or the write names none (hub#538: a role the business does not have reached the card, and the write refused
    it only after the person's yes). Nothing of their answers is shown: a normal write's card stays a single line; the
    id of what each found goes to ``found`` (``fingerprint``: a record the write takes by its name is the one the check
    found)."""
    declared = check_of(op)
    for name in (declared,) if isinstance(declared, str) else declared or ():
        read = registry[name]
        failure, answer = _run(ctx, read, {key: value for key, value in arguments.items() if key in read.input.model_fields})
        if failure is not None:
            return failure
        if found is not None:
            found.append(answer.model_dump(mode="json").get("id"))
    return None


def fingerprint(drawn: dict, found: list) -> str:
    """The fingerprint of what a write's card showed the person (``drawn``: its data and what it will do, in their
    words) and of the records it read to show them (``found``: their ids, by the data it names and its check) — what
    their yes is for (hub#1208): with the yes the card is drawn again, and a different fingerprint runs nothing.
    Only what the person saw and which records: never a read's whole answer (a signed link to a photo changes on each
    read, and the yes would never come)."""
    said = json.dumps({"card": drawn, "found": found}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(said.encode()).hexdigest()

