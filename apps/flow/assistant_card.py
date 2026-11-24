"""The assistant's card for an automation, a draft (``flow.draft.propose``) or a new one (``flow.flow.create``): its
name, when it starts and each step, in the words the Automations list and editor say them (``phrasing``), never the
codes of its definition. A normal card's line shows only its first three data."""

from django.utils import translation
from django.utils.translation import gettext, gettext_noop
from live.context import OperationContext
from pydantic import ValidationError

from apps.flow import phrasing
from apps.flow.schemas.drafts import DraftProposeIn
from apps.flow.schemas.fields import STARTS_WITH
from apps.flow.schemas.flows import CreateIn
from base.assistant import card_order

STEPS = gettext_noop("Steps")


def draft(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """A draft's name, when it starts and its steps, in place of its definition. Data the write refuses keep the card
    as they came."""
    try:
        data = DraftProposeIn.model_validate(arguments)
    except ValidationError:
        return fields
    definition = data.definition.model_dump(mode="json", exclude_none=True)
    # A draft without a trigger starts only by hand: that is said too.
    given = {"trigger": definition.get("trigger"), "steps": definition["steps"]}
    return _in_words(fields, given, _said_at(fields, "definition", "trigger"), dropped=("definition",))


def automation(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """A new automation's name, when it starts and its steps, in place of their codes: those it is given (one made from
    a draft may be given only the draft)."""
    try:
        data = CreateIn.model_validate(arguments)
    except ValidationError:
        return fields
    created = data.model_dump(mode="json", exclude_none=True)
    given = {key: created.get(key) for key in ("trigger", "steps") if key in arguments}
    return _in_words(fields, given, _said_at(fields, "trigger"), dropped=("trigger", "steps"))


def _said_at(fields: list[dict], name: str, *within: str) -> str:
    """The moment of a trigger that runs once as the card already says it, at the business's hour; '' without one."""
    value = next((field["value"] for field in fields if field["name"] == name), None)
    for key in within:
        value = value.get(key) if isinstance(value, dict) else None
    return str(value.get("at") or "") if isinstance(value, dict) else ""


def _in_words(fields: list[dict], given: dict, at: str, dropped: tuple[str, ...]) -> list[dict]:
    """``given``: the trigger and the steps the write takes, each said when it comes."""
    steps = given.get("steps") or []
    said = phrasing.Phrasing((translation.get_language() or "en").split("-")[0], tuple(steps))
    computed = []
    if "trigger" in given:
        when = phrasing.describe_trigger(given["trigger"], said, at)
        computed.append({"name": "when", "label": gettext(STARTS_WITH), "kind": "text", "value": when})
    if "steps" in given:
        each = [phrasing.describe_step(step, said) for step in steps]
        computed.append({"name": "steps", "label": gettext(STEPS), "kind": "list", "named": True, "value": each})
    return card_order.put_first(fields, ("name",), *computed, dropped=dropped)
