"""What an automation does, in the words of the Automations screens: the server's side of ``frontend/lib/phrasing.ts``,
reading the same catalogues, for what the server says itself (the History's actions, the assistant's card). Layered as
the screens: a hand-written phrase for the known events and actions, composed from the app and a dictionary of facts
and verbs for the rest, and the raw words for what nobody wrote down yet."""

import dataclasses
import datetime as dt
import functools
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from babel.dates import format_time
from django.apps import apps
from live.operations import Operation, registry

from apps.flow.document import TEMPLATE_RE, is_path, literal_origin
from base import assistant as hub_assistant
from base.business import babel_locale

#: The words of the app's screens, by language.
LOCALES = Path(__file__).resolve().parent / "frontend" / "locale"
#: The units a wait is said in, the largest that divides it (``delayParts`` of ``frontend/lib/document.ts``).
UNIT_SECONDS = (("days", 86400), ("hours", 3600))


@functools.cache
def screen_words(language: str) -> dict:
    path = LOCALES / f"{language}.json"
    return json.loads((path if path.exists() else LOCALES / "en.json").read_text(encoding="utf-8"))["flow"]


@dataclasses.dataclass(frozen=True)
class Phrasing:
    """The words of the screens in ``language`` and the steps of the automation a text speaks of (``Phrasing`` of
    ``frontend/lib/phrasing.ts``)."""

    language: str
    steps: tuple[dict, ...] = ()

    @property
    def words(self) -> dict:
        return screen_words(self.language)


def _fill(text: str, /, **values: Any) -> str:
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def _humanize(text: str) -> str:
    return text.replace("_", " ")


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def _quoted(text: str, p: Phrasing) -> str:
    """``text`` between the quotation marks of ``p``'s language: “Big sale”, «Venta grande»."""
    return _fill(p.words["quoted"], text=text)


def _clock(time: str, p: Phrasing) -> str:
    """A wall-clock ``HH:MM`` as ``p``'s language writes it, «6:00 PM», «18:00» (``formatTimeOfDay`` of the
    screens); what is no time, as it came."""
    try:
        moment = dt.time.fromisoformat(time)
    except (TypeError, ValueError):
        return str(time)
    return format_time(moment, "short", locale=babel_locale(p.language))


def action_label(op: Operation, language: str) -> str:
    """``op`` as the History names it: its own words or, without them, its verb, app and thing (``actionLabel`` of
    ``frontend/lib/phrasing.ts``)."""
    words = screen_words(language)
    curated = words["actions"].get(op.name.replace(".", "__"))
    if curated:
        return curated
    _app, entity, verb = ([*op.name.split(".", 2), "", ""])[:3]
    verb_word = words["verbs"].get(verb) or verb.replace("_", " ")
    return f"{verb_word} · {hub_assistant.cards.app_name(op)} ({entity.replace('_', ' ')})"


def _action(name: str, p: Phrasing) -> str:
    """An action a step names, by its words; one that no longer exists, by its verb and thing."""
    op = registry.get(name)
    if op is not None:
        return action_label(op, p.language)
    _app, entity, verb = ([*name.split(".", 2), "", ""])[:3]
    curated = p.words["actions"].get(name.replace(".", "__"))
    return curated or f"{p.words['verbs'].get(verb) or _humanize(verb)} ({_humanize(entity)})"


def event_label(name: str, p: Phrasing) -> str:
    """«a sale is charged», or «Customers: group deleted» for an event without a phrase."""
    curated = p.words["events"].get(name.replace(".", "__"))
    if curated:
        return curated
    app, entity, fact = ([*name.split(".", 2), "", ""])[:3]
    what = f"{_humanize(entity)} {p.words['facts'].get(fact) or _humanize(fact)}".strip()
    try:
        return f"{apps.get_app_config(app).verbose_name}: {what}"
    except LookupError:
        return _capitalize(what)


def describe_trigger(trigger: dict | None, p: Phrasing, at: str = "") -> str:
    """«When a sale is charged», «Every Friday at 18:00», «Only when you press Run»… ``at``: the moment of a trigger
    that runs once, already said at the business's hour."""
    said = p.words["trigger"]["describe"]
    kind = (trigger or {}).get("kind")
    if kind == "event":
        event = trigger.get("event")
        return _fill(said["event"], event=event_label(event, p)) if event else said["noEvent"]
    if kind == "schedule":
        return _schedule(trigger, p)
    if kind == "at":
        return _fill(said["at"], date=at) if at else said["noDate"]
    return said["manual"]


def _schedule(trigger: dict, p: Phrasing) -> str:
    said = p.words["trigger"]["describe"]
    every = trigger.get("every")
    if every == "week":
        weekday = p.words["trigger"]["weekdays"][trigger.get("weekday") or 0]
        return _fill(said["week"], weekday=weekday, time=_clock(trigger["time"], p))
    if every == "month":
        return _fill(said["month"], day=trigger.get("day") or 1, time=_clock(trigger["time"], p))
    return _fill(said["day"], time=_clock(trigger["time"], p))


def field_label(name: str, p: Phrasing) -> str:
    """«Title», or «Party size» for a field without a word."""
    return p.words["fields"].get(name) or _capitalize(_humanize(name))


def path_label(path: str, p: Phrasing) -> str:
    """Where a datum comes from: «Customer › Name», «1. Create a task › Number»."""
    root, *rest = path.split(".")
    if root == "input" and rest:
        return " › ".join(field_label(part, p) for part in rest)
    if root == "secret" and len(rest) == 1:
        return _fill(p.words["picker"]["secret"], name=rest[0])
    if path == "run.idempotency_key":
        return p.words["picker"]["idempotencyKey"]
    index = next((i for i, step in enumerate(p.steps) if rest and step.get("id") == rest[0]), None)
    if root != "steps" or len(rest) < 2 or index is None or p.steps[index].get("kind") in ("condition", "delay"):
        return path
    step = p.steps[index]
    named = step.get("kind") in ("http", "ask", "assistant")
    what = describe_step(step, p) if named else _action(step.get("operation", ""), p)
    return f"{index + 1}. {what} › {' › '.join(field_label(part, p) for part in rest[1:])}"


def _value_text(value: Any, p: Phrasing) -> str:
    if value is True or value is False:
        return p.words["steps"]["yes" if value else "no"]
    if isinstance(value, list):
        return ", ".join(_value_text(item, p) for item in value)
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        # The screens have one kind of number: 10000.0 is said «10000».
        return str(int(value))
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")) if isinstance(value, dict) else str(value)


def describe_clause(path: str, op: str, value: Any, p: Phrasing) -> str:
    """«Total greater than or equal to 10000», «Customer present: yes»; another datum, by its words."""
    what = path_label(path, p)
    operator = p.words["steps"]["operators"].get(op, op)
    if op == "exists":
        return f"{what} {operator}: {_value_text(value, p)}"

    def named(item: Any) -> Any:
        return path_label(item, p) if is_path(item) else item

    shown = [named(item) for item in value] if isinstance(value, list) else named(value)
    return f"{what} {operator} {_value_text(shown, p)}"


def _templated(text: Any, p: Phrasing) -> str:
    """A text with ``{{…}}`` data, each datum by its words between the quotation marks of its language."""
    if text is None:
        return ""
    if not isinstance(text, str):
        return json.dumps(text, ensure_ascii=False) if isinstance(text, dict) else str(text)
    if is_path(text):
        return _quoted(path_label(text, p), p)
    return TEMPLATE_RE.sub(lambda match: _quoted(path_label(match[1], p), p), text).strip()


def _delay(step: dict, p: Phrasing) -> str:
    seconds = int(step.get("seconds") or 0)
    unit, amount = next(
        ((unit, seconds // size) for unit, size in UNIT_SECONDS if seconds and seconds % size == 0),
        # Half a minute rounds up, as the screens' ``Math.round``; Python's ``round`` goes to the even one.
        ("minutes", max(1, (seconds + 30) // 60)),
    )
    units = p.words["steps"]["units"][unit]
    return _fill(p.words["steps"]["wait"], amount=amount, unit=units["one" if amount == 1 else "many"])


def _condition(step: dict, p: Phrasing) -> str:
    clauses = [
        describe_clause(path, op, value, p)
        for path, comparisons in (step.get("when") or {}).items()
        for op, value in (comparisons or {}).items()
    ]
    return "; ".join(clauses) if clauses else p.words["steps"]["describe"]["noCondition"]


def _http(step: dict, p: Phrasing) -> str:
    found = literal_origin(str(step.get("url") or ""))
    said = p.words["steps"]["describe"]
    return _fill(said["http"], host=found.removeprefix("https://")) if found else said["noHttp"]


def _asked(key: str, field: str, empty: str) -> Callable[[dict, Phrasing], str]:
    """A step that says a text of its own: a question, or what it asks the assistant."""

    def describe(step: dict, p: Phrasing) -> str:
        text = _templated(step.get(field), p)
        said = p.words["steps"]["describe"]
        return _fill(said[key], **{field: text}) if text else said[empty]

    return describe


_STEPS = {
    "delay": _delay,
    "condition": _condition,
    "http": _http,
    "ask": _asked("ask", "title", "noAsk"),
    "assistant": _asked("assistant", "prompt", "noAssistant"),
}


def describe_step(step: dict, p: Phrasing) -> str:
    """What a step does, in one line, as the title of its card in the editor."""
    describe = _STEPS.get(step.get("kind", ""))
    if describe is not None:
        return describe(step, p)
    if not step.get("operation"):
        return p.words["steps"]["noAction"]
    action = _action(step["operation"], p)
    return _fill(p.words["steps"]["describe"]["query"], action=action) if step.get("kind") == "query" else action
