"""The document on an automation: what its trigger writes on the row, what the list's search looks in,
when a schedule or a date starts it next, and the refusals, by field, of what this business does not
have, of a date that has passed and of what its app fixes on one built from a recipe (FLOW-F36)."""

import datetime as dt
from typing import Any

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload
from live.outbox import record_event

from apps.flow import document, events, recipes
from apps.flow.models import Flow
from apps.flow.queries.problems import catalog_problems
from base.business import business_zone

PAST_DATE = _("That date and time has already passed.")
#: What its app fixes on an automation built from one of its recipes is not taken off from it (FLOW-F36): the ways
#: out are another value, taking that tool off the step, starting it with something else, or a copy (the owner's).
FIXED_CLAUSE = _(
    "«%(app)s» puts a condition on «%(field)s»: give it another value, start it with something else or make a copy."
)
FIXED_PIN = _(
    "«%(app)s» fixes «%(field)s» of «%(name)s»: give it another value, take «%(name)s» off what it may use or make a copy."
)
#: The code of that refusal.
RECIPE_FIXED_CODE = "flow.recipe_fixed"


def refresh_search_text(flow: Flow) -> None:
    """What the list's search looks in: the name, the event and the operations of its steps."""
    parts = [flow.name, flow.trigger_event, *document.required_grants(flow.steps)]
    flow.search_text = " ".join(part for part in parts if part)


def _apply_trigger(flow: Flow, trigger: Any) -> None:
    flow.trigger_kind = trigger.kind
    flow.trigger_event = trigger.event if trigger.kind == "event" else ""
    flow.trigger_filter = trigger.filter if trigger.kind == "event" else {}
    flow.schedule = (
        {
            key: value
            for key, value in trigger.model_dump(mode="json").items()
            if key != "kind"
        }
        if trigger.kind == "schedule"
        else {}
    )
    flow.run_at = trigger.at if trigger.kind == "at" else None


def _taken_off(ctx: OperationContext, flow: Flow, trigger: Any, steps: list[Any] | None) -> None:
    """Refuses, by field, a change that leaves out what its app fixes on ``flow`` (FLOW-F36): a condition of its «Only
    when…» while it starts on the recipe's event, or a datum of an «Ask the assistant» step (or leaves it empty) while
    that step may use its tool. Saved, it would come back on reading it without a word."""
    fixed = recipes.fixed_by_app(flow)
    if fixed is None:
        return
    problems: dict[str, str] = {}
    if trigger is not None and trigger.kind == "event" and trigger.event == fixed["event"]:
        gone = next((path for path in fixed["filter"] if path not in (trigger.filter or {})), None)
        if gone is not None:
            problems["trigger.filter"] = str(FIXED_CLAUSE) % {"app": fixed["app_name"], "field": gone}
    for index, step in enumerate(steps or []):
        wanted = fixed["pinned"].get(step.id) if step.kind == "assistant" else None
        for tool, fields in (wanted or {}).items():
            have = (step.pinned or {}).get(tool) or {}
            gone = next((field for field in fields if _blank(have.get(field))), None)
            if tool in step.tools and gone is not None:
                problems[f"steps.{index}.pinned"] = str(FIXED_PIN) % {
                    "app": fixed["app_name"], "field": gone, "name": tool
                }
                break
    if problems:
        raise InvalidPayload(next(iter(problems.values())), code=RECIPE_FIXED_CODE, fields=problems)


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _check(
    ctx: OperationContext, trigger: Any, steps: list[Any] | None, now: dt.datetime, saved_at: dt.datetime | None = None
) -> None:
    """Refuses, by field, what this business does not have and a date that has passed — only a date that
    changes (``saved_at`` is the one it keeps): one that already went off must not block a rename."""
    problems, code = catalog_problems(ctx.scope, trigger, steps or [])
    if trigger is not None and trigger.kind == "at" and trigger.at != saved_at and trigger.at <= now:
        problems["trigger.at"] = str(PAST_DATE)
    if problems:
        raise InvalidPayload(next(iter(problems.values())), code=code, fields=problems)


def _next_fire(flow: Flow, now: dt.datetime) -> dt.datetime | None:
    """When a schedule or a date starts it next, counted from ``now``; ``None`` while it never will."""
    if not flow.enabled:
        return None
    if flow.trigger_kind == Flow.Trigger.SCHEDULE:
        return document.next_fire(flow.schedule, now, business_zone())
    if flow.trigger_kind == Flow.Trigger.AT and flow.run_at and flow.run_at > now:
        return flow.run_at
    return None


def _record_switch(ctx: OperationContext, flow: Flow) -> None:
    record_event(
        ctx,
        events.FLOW_ENABLED if flow.enabled else events.FLOW_PAUSED,
        {"id": str(flow.id)},
    )
