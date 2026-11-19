"""A step's data for what the run knows, and how a text a person reads says each datum (FLOW-F28, F31)."""

import datetime as dt
import functools
import re
from collections.abc import Collection
from typing import Any

import pydantic
from django.utils import translation
from babel.dates import format_date, format_time, get_datetime_format
from django.utils.translation import pgettext_lazy
from live.assistant import MONEY
from live.context import Scope
from live.errors import OperationError
from live.operations import Operation, registry

from apps.flow import document
from base.business import babel_locale, money_text
from base.home import ISO_HOUR, moment
from base.operations import business_currency

from .catalog import step_data

#: The data of an action a person reads, by action: a message to a customer (FLOW-F31), its text and its template's
#: values. Each datum inserted in them is said in words (``words_for``); every other action's data go to a machine.
PERSON_PARAMS: dict[str, frozenset[str]] = {"whatsapp_inbox.message.notify": frozenset({"text", "template"})}
#: A yes or no inserted in a text a person reads.
YES = pgettext_lazy("datum", "Yes")
NO = pgettext_lazy("datum", "No")


#: The mark of an amount in a currency of its own, not the one its step answers: the name of the datum beside it, a text
#: its step leaves, that gives that currency (ISO 4217) — a charge preview's legal limits, in the euros the law writes
#: them in whatever the business charges in (``json_schema_extra={"money": True, "currency_in": "limits_currency"}``,
#: hub#926), as a payment's amount travels with its currency.
CURRENCY_IN = "currency_in"


def _is_money(prop: dict) -> bool:
    """An amount, as its schema marks it (``json_schema_extra={"money": True}``): the mark the assistant's card reads
    (``live.assistant.MONEY``, BASE-F97). Neither a name in ``_cents`` nor the words of a description («in cents») make
    one (hub#498)."""
    return prop.get(MONEY) is True


#: The datum of a step's answer that gives the currency of its amounts (a payment in dollars), as BASE-F98 reads it.
ANSWERED_CURRENCY = "currency"


def _money_currencies(steps: list[dict]) -> dict[str, tuple[str | None, ...]]:
    """The amounts the steps' actions and reads mark in what they leave (``step_data``: their output's schema, a
    read's first row, and the objects inside), by path (``steps.<id>.<field>``, ``steps.<id>.item.unit_price``), each
    with the paths of the data that give its currency, nearest first (``_currency_data``). An event declares none."""
    found: dict[str, tuple[str | None, ...]] = {}
    for step in steps:
        op = registry.get(str(step.get("operation") or "")) if step.get("kind") in ("command", "query") else None
        if op is None:
            continue
        for name, prop in step_data(op).items():
            if _is_money(prop):
                path = f"steps.{step.get('id')}.{name}"
                found[path] = _currency_data(path, prop)
    return found


def _currency_data(path: str, prop: dict) -> tuple[str | None, ...]:
    """The paths of the data that give the currency of the amount at ``path``, nearest first: the one its mark names
    beside it (``CURRENCY_IN``), alone; else the ``ANSWERED_CURRENCY`` of the object that holds it (a cart's line in
    dollars), then of each one around it up to its step's answer, and ``None`` last: the business's — as the
    assistant's card says an amount nested in an object (BASE-F97)."""
    holders = path.split(".")[:-1]
    if own := prop.get(CURRENCY_IN):
        return (".".join([*holders, own]),)
    around = (".".join([*holders[:depth], ANSWERED_CURRENCY]) for depth in range(len(holders), 1, -1))
    return (*around, None)


def _money_paths(steps: list[dict]) -> frozenset[str]:
    """The paths (``steps.<id>.<field>``, ``steps.<id>.item.unit_price``) of the amounts the steps' actions and reads
    mark in what they leave."""
    return frozenset(_money_currencies(steps))


def _answered_currency(data: dict, datum: str) -> str | None:
    """The currency the datum at ``datum`` answers in ``data`` — a ``currency`` (a payment in dollars, an invoice in the
    one it was issued in), as the assistant's card says an amount of a read (BASE-F98), or the one an amount's mark
    names (``CURRENCY_IN``) —; ``None`` when there is none."""
    currency = document.lookup(datum, data)[1]
    return currency if isinstance(currency, str) and currency else None


#: The hour JSON gives (``21:30:00``); one without its seconds (``21:00``) is how an app writes it for a person.
_JSON_HOUR = re.compile(r"\d{2}:\d{2}:\d{2}(\.\d+)?")


def _moment_words(text: str, language: str) -> str | None:
    """``text``, an ISO day, hour or instant as JSON gives it, as CLDR writes it in ``language`` — a medium day and a
    short hour, as the screens and the assistant's card say them —, an instant at the business's hour; ``None`` for
    any other text, an hour already written for a person (``21:00``) among them."""
    if ISO_HOUR.fullmatch(text) and not _JSON_HOUR.fullmatch(text):
        return None
    try:
        when = moment(text)
    except ValueError:
        return None
    locale = babel_locale(language)
    if isinstance(when, dt.datetime):
        when = when.replace(tzinfo=None)
        day, hour = format_date(when.date(), "medium", locale=locale), format_time(when.time(), "short", locale=locale)
        return get_datetime_format("medium", locale=locale).replace("{1}", day).replace("{0}", hour)
    if isinstance(when, dt.date):
        return format_date(when, "medium", locale=locale)
    return format_time(when.replace(tzinfo=None), "short", locale=locale)


def words_for(steps: list[dict], language: str, scope: Scope, data: dict | None = None) -> document.Say:
    """How a text a person reads — a question (FLOW-F28), a message to a customer (FLOW-F31) — says each datum it
    inserts, as the assistant's card says it (BASE-F97): a yes or no as «Yes»/«No», an ISO day, hour or instant as
    ``language`` writes it at the business's hour, and an amount the schema of the step that left it marks as money —
    on its answer or inside an object of it — in the currency the object that holds it answers in ``data``, else its
    step, else the business (``_currency_data``) — one in a currency of its own (``CURRENCY_IN``), only in the one its
    datum gives —; anything else as it is. An event declares no schema: a number it brings is never guessed as
    money."""
    money = _money_currencies(steps)
    business = functools.cache(lambda: _currency(scope))

    def currency(path: str) -> str | None:
        for datum in money[path]:
            if code := (business() if datum is None else _answered_currency(data or {}, datum)):
                return code
        return None

    def say(path: str, value: Any) -> str:
        if isinstance(value, bool):
            with translation.override(language):
                return str(YES if value else NO)
        if isinstance(value, str):
            return _moment_words(value, language) or value
        if isinstance(value, int) and path in money and (code := currency(path)):
            return money_text(value, code, language=language)
        return str(value)

    return say


def _currency(scope: Scope) -> str | None:
    """The business's currency, or ``None`` when it has none (a scope that is no hub's): its amounts then say their
    figure, never a made-up currency."""
    try:
        return business_currency(scope)
    except OperationError:
        return None


def map_params(
    params: dict[str, Any],
    data: dict,
    unknown_steps: set[str] = frozenset(),
    *,
    say: document.Say | None = None,
    person: Collection[str] = (),
) -> tuple[dict, list, list]:
    """``(values, empty, unknown)`` of a step's ``params`` for ``data``.

    A value read from a path that is missing (or null) is left out and named in ``empty``; a template
    with a missing field keeps its text and is named in ``empty`` too. A value that reads the output of
    a step in ``unknown_steps`` (one that has not run) is left out and named in ``unknown``. The params in
    ``person`` are read by a person: each datum in them is the text ``say`` writes for it.
    """
    values: dict[str, Any] = {}
    empty: list[str] = []
    unknown: list[str] = []
    for key, raw in params.items():
        said = say if key in person else None
        reads = document.references(raw)
        if any(
            path.startswith("steps.") and path.split(".")[1] in unknown_steps
            for path in reads
        ):
            unknown.append(key)
            continue
        if document.is_path(raw):
            found, value = document.lookup(raw, data)
            if not found or value is None:
                empty.append(key)
                continue
            values[key] = value if said is None else said(raw, value)
            continue
        values[key] = document.resolve(raw, data, said)
        if any(
            document.lookup(path, data)[1] is None
            for path in reads
            if document.is_path(path)
        ):
            empty.append(key)
    return values, empty, unknown


def prepared(op: Operation, step_kind: str, result: str, values: dict) -> dict:
    """The input of a read that keeps the first row: one row is enough (unless the step asks for more)."""
    if (
        step_kind == "query"
        and result == "first"
        and "limit" in op.input.model_fields
        and "limit" not in values
    ):
        return {**values, "limit": 1}
    return values


def validation_fields(error: pydantic.ValidationError) -> dict[str, str]:
    return {
        ".".join(map(str, item["loc"])) or "__all__": item["msg"]
        for item in error.errors()
    }
