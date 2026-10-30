"""Read operations of the flow app (``READ ONLY``) and the helpers the writes and the engine share.

- **The catalog** (``catalog_events``, ``catalog_operations``): what the active apps declare, never a
  name made up here. Events are each app's ``events.ALL``; actions and reads are its registered
  operations whose permission the app declares (a person can be granted it: platform-only reactions
  are left out). ``active_apps`` is the phase-1 seam: every installed module but this one, as
  ``base.session.me``; phase 2 reads the SaaS's picture there.
- **Values** (``map_params``): a step's params for what the run knows (``document.resolve``), leaving out
  what came out empty, so an optional field keeps its default. What a person reads (``PERSON_PARAMS``, a question's
  texts) says each datum in words (``words_for``); what goes to a machine, as the code keeps it.
- **«Try it»** (``flow.flow.test``) walks the steps against the last real event of this business and
  executes nothing: it validates each action's data against the action's own schema.
- **One record by its id** (an automation, a draft, a run, a question waiting for an answer), with the words its
  screen names it by: what the assistant's card says instead of the id (schemas.py, ``names``).
"""

import datetime as dt
import functools
import importlib
import json
import re
from collections.abc import Collection
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import pydantic
from django.db.models import Count, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Lower
from django.utils import timezone, translation
from babel.dates import format_date, format_time, get_datetime_format
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.context import OperationContext, Scope
from live.errors import Conflict, InvalidPayload, NotFound, OperationError, PermissionDenied
from live.meta import LiveAppConfig, module_configs
from live.models import OutboxEvent
from live.operations import Operation, operation, registry

from apps.flow import document, recipes, vault
from base import assistant as hub_assistant
from base.business import babel_locale, money_text
from base.home import ISO_HOUR, moment
from base.operations import business_currency
from apps.flow.models import Draft, Flow, FlowRun, Question, Secret
from apps.flow.schemas import (
    CatalogIn,
    CatalogOut,
    DraftListIn,
    DraftOut,
    DraftRefIn,
    FlowListIn,
    FlowOut,
    FlowRefIn,
    Page,
    QuestionListIn,
    QuestionOut,
    QuestionPageOut,
    QuestionRefIn,
    RecipeListIn,
    RecipeListOut,
    RunDetailOut,
    RunListIn,
    RunPageOut,
    RunRefIn,
    SampleIn,
    SampleOut,
    SecretListIn,
    SecretPageOut,
    StatusIn,
    StatusOut,
    TestDocumentIn,
    TestIn,
    TestOut,
)

VIEW = "flow.view"
MANAGE = "flow.manage"
#: Run only by the platform (events.py and the scheduled tasks): no role holds it.
SYSTEM = "flow.system"
#: FLOW-F29: answering what is asked of employees, and of managers; whoever manages answers everything.
ANSWER = "flow.answer"
ANSWER_MANAGER = "flow.answer_manager"
#: The permission each role of «Ask someone first» asks for ('' = whoever runs the business).
ROLE_PERMISSION = {"": MANAGE, "manager": ANSWER_MANAGER, "employee": ANSWER}
#: Where a step's conversation lives while the assistant thinks: no step id starts with «_» (``StepId``).
TURN = "_turn"

FLOW_NOT_FOUND = _("That automation does not exist in this business.")
DRAFT_NOT_FOUND = _("That draft does not exist in this business.")
RUN_NOT_FOUND = _("That run does not exist in this business.")
QUESTION_NOT_FOUND = _("That question does not exist in this business.")
QUESTION_NOT_YOURS = _("This question was asked of someone else: you cannot answer it.")
QUESTION_CLOSED = _("This question is closed: its automation no longer waits for it.")
AMBIGUOUS_FLOW = _("Several automations fit «%(text)s»: %(names)s. Say which one.")
UNKNOWN_EVENT = _("That does not happen in this business: «%(name)s».")
UNKNOWN_ACTION = _("That action does not exist in this business: «%(name)s».")
NOT_AN_ACTION = _("«%(name)s» only reads: use «Look something up».")
NOT_A_READ = _("«%(name)s» changes data: use «Do something».")
HIGH_RISK = _("«%(name)s» needs a person in front: an automation cannot do it.")
ASK_FIRST_ONLY = _("«%(name)s» needs a person's yes first: choose «Ask me first».")
#: The code of a refusal of an action that needs a person, when it is saved, granted or run.
HIGH_RISK_CODE = "flow.high_risk"
#: What needs a person in front that an automation may still be granted, only for an «Ask the assistant» step that
#: asks first: cancelling a reservation a guest asks to cancel, done once someone who may cancel it says yes (Zapier's
#: Human in the Loop and n8n's human review gate the step that cannot be undone; Fresha's AI Concierge cancels within
#: the business's policy). Never what is done in person, money, fiscal records nor erasing. An appointment's waits
#: for Appointments to take a change from an automation at all (today: «You may only change your own appointments.»).
ASK_FIRST = frozenset({"reservation.reservation.cancel"})
NO_SECRET = _("There is no secret called «%(name)s».")
BAD_HTTP_GRANT = _("«%(name)s» is no address this automation can be allowed to call.")
NOT_FOR_THE_ASSISTANT = _("The assistant cannot use «%(name)s».")
PINNED_NOT_A_TOOL = _(
    "«%(name)s» has fixed data but the assistant may not use it: add it to what it may use or remove its fixed data."
)
PINNED_NO_INPUT = _("«%(field)s» is no datum of «%(name)s».")
PINNED_EMPTY = _("Give «%(field)s» of «%(name)s» a value, or remove it.")

#: How many names an ambiguous reference lists.
AMBIGUOUS_SHOWN = 5


# --- The catalog ------------------------------------------------------------------------------------


def active_apps() -> dict[str, LiveAppConfig]:
    """The modules active in this business, but this one (phase 1: every installed module)."""
    return {
        config.label: config for config in module_configs() if config.label != "flow"
    }


def catalog_events() -> dict[str, LiveAppConfig]:
    """``{event name: its app}``: the ``events.ALL`` of every active app."""
    found: dict[str, LiveAppConfig] = {}
    for label, config in active_apps().items():
        module_name = f"{config.name}.events"
        if find_spec(module_name) is None:
            continue
        for name in getattr(importlib.import_module(module_name), "ALL", []):
            if name.startswith(f"{label}."):
                found[name] = config
    return found


def grantable_operations() -> dict[str, Operation]:
    """``{operation name: operation}`` of the active apps whose permission the app declares: what a
    person can be granted (the platform-only reactions are left out)."""
    apps = active_apps()
    granted: dict[str, Operation] = {}
    for name, op in registry.items():
        config = apps.get(op.app_label)
        if config is not None and op.permission in config.permissions:
            granted[name] = op
    return granted


def needs_a_person(op: Operation) -> bool:
    """An action the assistant confirms before running (``ai.risk == "high"``: voiding, refunding,
    erasing, sending to the tax agency…) or one done in person (``ai.in_person``: seating a party at the
    door): never for an automation, which acts with nobody in front."""
    ai = op.ai or {}
    return ai.get("risk") == "high" or ai.get("in_person") is True


def asks_first(op: Operation) -> bool:
    """An action that needs a person in front that an «Ask me first» step may still propose (``ASK_FIRST``), never
    one done in person."""
    return op.name in ASK_FIRST and needs_a_person(op) and (op.ai or {}).get("in_person") is not True


def catalog_operations() -> dict[str, Operation]:
    """What an automation may be granted and run: the grantable operations that do not need a person."""
    return {name: op for name, op in grantable_operations().items() if not needs_a_person(op)}


def ask_first_catalog() -> dict[str, Operation]:
    """What an «Ask the assistant» step that asks first may be granted and offered: the catalog and ``ASK_FIRST``."""
    return {name: op for name, op in grantable_operations().items() if not needs_a_person(op) or asks_first(op)}


def asked_first(steps: list[dict]) -> set[str]:
    """The tools of the steps that ask first («Ask me first», the default of «Ask the assistant»)."""
    return {
        str(name)
        for step in steps
        if step.get("kind") == "assistant" and step.get("mode", "ask") == "ask"
        for name in step.get("tools") or []
    }


def read_permissions(op: Operation) -> frozenset[str]:
    """The reads of ``op``'s app (its declared ``<app>.view…`` permissions): what a step may also need to
    answer with what it did, never to change anything else."""
    config = active_apps().get(op.app_label)
    declared = config.permissions if config is not None else []
    return frozenset(permission for permission in declared if permission.split(".", 1)[-1].startswith("view"))


def _resolve_ref(schema: dict, defs: dict) -> dict:
    ref = schema.get("$ref")
    return defs.get(ref.rsplit("/", 1)[-1], {}) if ref else schema


def _field_type(prop: dict, defs: dict) -> tuple[str, list[str]]:
    for branch in prop.get("anyOf", []):
        if branch.get("type") != "null":
            return _field_type(branch, defs)
    prop = _resolve_ref(prop, defs)
    if "enum" in prop:
        return "choice", [str(value) for value in prop["enum"]]
    if "const" in prop:
        return "choice", [str(prop["const"])]
    kind = (
        prop.get("format")
        if prop.get("format") in ("uuid", "date", "date-time", "time")
        else None
    )
    return kind or str(prop.get("type", "object")), []


def action_fields(op: Operation) -> list[dict]:
    """What an operation asks for: one field each, with its type, whether it is required and its words."""
    schema = op.input.model_json_schema()
    defs = schema.get("$defs", {})
    required = set(schema.get("required", []))
    fields = []
    for name, prop in schema.get("properties", {}).items():
        declared = op.input.model_fields.get(name)
        kind, choices = _field_type(prop, defs)
        fields.append(
            {
                "name": name,
                "type": kind,
                "required": name in required,
                "description": (declared.description if declared else None)
                or prop.get("description", ""),
                "choices": choices,
            }
        )
    return fields


def action_outputs(op: Operation) -> list[str]:
    """What a step of ``op`` leaves for the next ones: its output's fields (a list's first row's), and
    ``found`` and ``count`` for a read."""
    schema = op.output.model_json_schema()
    defs = schema.get("$defs", {})
    properties = schema.get("properties", {})
    if op.kind == "query" and "rows" in properties:
        properties = _resolve_ref(properties["rows"].get("items", {}), defs).get(
            "properties", {}
        )
    names = list(properties)
    if op.kind == "query":
        names += [name for name in ("found", "count") if name not in names]
    return names


@operation(
    "flow.catalog.read",
    kind="query",
    permission=VIEW,
    input=CatalogIn,
    output=CatalogOut,
    ai={
        "description": "What an automation can start on and do in this business: the events of the active apps "
        "(`sale.sale.completed`…) and the actions and reads it can be granted, with the data each one asks for. "
        "One with `ask_first` only goes in an «Ask the assistant» step with «Ask me first»."
    },
)
def read_catalog(ctx: OperationContext, data: CatalogIn) -> dict:
    with translation.override(ctx.language):
        events = [
            {"name": name, "app": config.label, "app_name": str(config.verbose_name)}
            for name, config in catalog_events().items()
        ]
        apps = active_apps()
        actions = [
            {
                "name": name,
                "kind": op.kind,
                "app": op.app_label,
                "app_name": str(apps[op.app_label].verbose_name),
                "description": str((op.ai or {}).get("description", "")),
                "fields": action_fields(op),
                "outputs": action_outputs(op),
                "assistant": hub_assistant.is_tool(op),
                "ask_first": asks_first(op),
            }
            for name, op in ask_first_catalog().items()
        ]
    return {
        "events": sorted(events, key=lambda event: (event["app"], event["name"])),
        "actions": sorted(actions, key=lambda action: (action["app"], action["name"])),
    }


def operation_problem(name: str, kind: str | None = None, *, asking: bool = False) -> tuple[str, str] | None:
    """``(code, message)`` of why an automation may not run the operation ``name`` (as a step of
    ``kind``, when given; for a step that asks first, ``asking``), or ``None`` when it may. A call's origin
    (``http:https://host``) is checked as an address."""
    if name.startswith(document.HTTP_GRANT) and kind is None:
        address = name[len(document.HTTP_GRANT) :]
        if document.origin(address) != address:
            return "invalid_payload", str(BAD_HTTP_GRANT) % {"name": name}
        return None
    op = grantable_operations().get(name)
    if op is None:
        return "invalid_payload", str(UNKNOWN_ACTION) % {"name": name}
    if needs_a_person(op) and not (asking and asks_first(op)):
        message = ASK_FIRST_ONLY if kind is None and asks_first(op) else HIGH_RISK
        return HIGH_RISK_CODE, str(message) % {"name": name}
    if kind == "command" and op.kind != "command":
        return "invalid_payload", str(NOT_AN_ACTION) % {"name": name}
    if kind == "query" and op.kind != "query":
        return "invalid_payload", str(NOT_A_READ) % {"name": name}
    return None


def pinned_problem(tools: list[str], pinned: dict[str, dict[str, Any]]) -> str | None:
    """Why the fixed data of an «Ask the assistant» step cannot be saved (the first reason), or ``None``: each is of a
    tool the step may use, names a datum that tool asks for and has a value."""
    for name, fixed in pinned.items():
        op = grantable_operations().get(name)
        if name not in tools or op is None:
            return str(PINNED_NOT_A_TOOL) % {"name": name}
        inputs = {field["name"] for field in action_fields(op)}
        for field, value in fixed.items():
            if field not in inputs:
                return str(PINNED_NO_INPUT) % {"field": field, "name": name}
            if value is None or (isinstance(value, str) and not value.strip()):
                return str(PINNED_EMPTY) % {"field": field, "name": name}
    return None


def catalog_problems(trigger: Any, steps: list[Any]) -> tuple[dict[str, str], str]:
    """What a document names that this business does not have, by field (``trigger.event``,
    ``steps.<n>.operation``), and the code of the refusal: ``flow.high_risk`` when a step needs a
    person in front, ``invalid_payload`` otherwise."""
    problems: dict[str, str] = {}
    code = "invalid_payload"
    if trigger is not None and trigger.kind == "event" and trigger.event not in catalog_events():
        problems["trigger.event"] = str(UNKNOWN_EVENT) % {"name": trigger.event}
    kept = None
    for index, step in enumerate(steps):
        if step.kind == "http":
            # A call names kept secrets: each must exist (FLOW-F26), named next to the field that reads it.
            kept = set(Secret.objects.values_list("name", flat=True)) if kept is None else kept
            for name in document.secret_names(step.model_dump()):
                if name not in kept:
                    field = next(
                        part
                        for part, text in (("url", step.url), ("headers", " ".join(step.headers.values())), ("body", step.body))
                        if f"secret.{name}" in text
                    )
                    problems.setdefault(f"steps.{index}.{field}", str(NO_SECRET) % {"name": name})
            continue
        if step.kind == "assistant":
            for name in step.tools:
                problem = operation_problem(name, asking=step.mode == "ask")
                if problem is None and not hub_assistant.is_tool(grantable_operations()[name]):
                    problem = ("invalid_payload", str(NOT_FOR_THE_ASSISTANT) % {"name": name})
                if problem is not None:
                    problem_code, problems[f"steps.{index}.tools"] = problem
                    code = HIGH_RISK_CODE if problem_code == HIGH_RISK_CODE else code
                    break
            problem = pinned_problem(step.tools, step.pinned or {})
            if problem is not None:
                problems[f"steps.{index}.pinned"] = problem
            continue
        if step.kind not in ("command", "query"):
            continue
        problem = operation_problem(step.operation, step.kind)
        if problem is not None:
            problem_code, problems[f"steps.{index}.operation"] = problem
            if problem_code == HIGH_RISK_CODE:
                code = HIGH_RISK_CODE
    return problems, code


# --- Automations ------------------------------------------------------------------------------------


def live_flows() -> QuerySet[Flow]:
    """The automations that are not deleted."""
    return Flow.objects.filter(deleted_at__isnull=True)


def resolve_flow(
    flow_id, text: str | None, *, lock: bool = False, rows: QuerySet[Flow] | None = None
) -> Flow:
    """The automation of ``flow_id``, or the one whose name is or contains ``text``.

    ``NotFound`` when none (a deleted one included); ``Conflict`` ``flow.ambiguous_flow`` naming the
    candidates when a text fits several. ``lock`` holds its row until the COMMIT. It comes from
    ``rows`` (automations that are not deleted, e.g. ``with_last_run``) when given, in one read by its
    id: a deletion committed meanwhile is either not seen yet or not found, never a row that vanished
    or was deleted between two reads.
    """
    if flow_id is None:
        flows = live_flows()
        exact = list(flows.filter(name__iexact=text).values_list("pk", "name"))
        matches = exact or list(
            flows.filter(name__icontains=text)
            .order_by(Lower("name"), "id")
            .values_list("pk", "name")
        )
        if len(matches) > 1:
            names = ", ".join(f"«{name}»" for _, name in matches[:AMBIGUOUS_SHOWN])
            raise Conflict(
                str(AMBIGUOUS_FLOW) % {"text": text, "names": names},
                code="flow.ambiguous_flow",
            )
        flow_id = matches[0][0] if matches else None
    found = (live_flows() if rows is None else rows).filter(pk=flow_id)
    flow = (found.select_for_update() if lock else found).first()
    if flow is None:
        raise NotFound(str(FLOW_NOT_FOUND))
    return flow


def trigger_of(flow: Flow) -> dict[str, Any]:
    """The trigger of ``flow`` as the document writes it."""
    if flow.trigger_kind == Flow.Trigger.EVENT:
        return {
            "kind": "event",
            "event": flow.trigger_event,
            "filter": flow.trigger_filter,
        }
    if flow.trigger_kind == Flow.Trigger.SCHEDULE:
        schedule = flow.schedule
        return {
            "kind": "schedule",
            "every": schedule.get("every"),
            "weekday": schedule.get("weekday"),
            "day": schedule.get("day"),
            "time": schedule.get("time"),
        }
    if flow.trigger_kind == Flow.Trigger.AT:
        return {"kind": "at", "at": flow.run_at.isoformat() if flow.run_at else None}
    return {"kind": "manual"}


def with_last_run(flows: QuerySet[Flow]) -> QuerySet[Flow]:
    last = FlowRun.objects.filter(flow=OuterRef("pk")).order_by("-started_at", "-id")
    return flows.annotate(
        last_run_id=Subquery(last.values("id")[:1]),
        last_run_status=Subquery(last.values("status")[:1]),
        last_run_started_at=Subquery(last.values("started_at")[:1]),
    )


def flow_row(flow: Flow) -> dict[str, Any]:
    """What ``FlowOut`` shows of an automation (annotated with ``with_last_run`` or not). Not annotated, it
    reads its last run again: only for a row the caller has just written or holds locked; a plain read
    takes it annotated from ``resolve_flow(rows=…)``."""
    required = document.required_grants(flow.steps)
    if not hasattr(flow, "last_run_id"):
        flow = with_last_run(Flow.objects.filter(pk=flow.pk)).get()
    return {
        "id": flow.id,
        "name": flow.name,
        "enabled": flow.enabled,
        "trigger": trigger_of(flow),
        "steps": flow.steps,
        "grants": flow.grants,
        "required_grants": required,
        "missing_grants": [name for name in required if name not in flow.grants],
        "version": flow.version,
        "next_fire_at": flow.next_fire_at,
        "created_at": flow.created_at,
        "updated_at": flow.updated_at,
        "created_by": flow.created_by,
        "updated_by": flow.updated_by,
        "last_run": (
            {
                "id": flow.last_run_id,
                "status": flow.last_run_status,
                "started_at": flow.last_run_started_at,
            }
            if flow.last_run_id
            else None
        ),
    }


_FLOW_SORTS = {
    "-updated_at": ("-updated_at", "id"),
    "updated_at": ("updated_at", "id"),
    "name": (Lower("name"), "id"),
    "-name": (Lower("name").desc(), "-id"),
}


@operation(
    "flow.flow.list",
    kind="query",
    permission=VIEW,
    input=FlowListIn,
    output=Page[FlowOut],
    ai={
        "description": "The automations of this business («what automations do I have?»), each with what starts it, "
        "whether it is on, the permissions it still lacks and how its last run ended; search by name, event "
        "or action."
    },
)
def list_flows(ctx: OperationContext, data: FlowListIn) -> dict:
    flows = live_flows()
    if data.search:
        flows = flows.filter(
            Q(search_text__icontains=data.search) | Q(name__icontains=data.search)
        )
    if data.enabled is not None:
        flows = flows.filter(enabled=data.enabled)
    if data.trigger_kind is not None:
        flows = flows.filter(trigger_kind=data.trigger_kind)
    total = flows.count()
    page = with_last_run(flows.order_by(*_FLOW_SORTS[data.sort]))[
        data.offset : data.offset + data.limit
    ]
    return {
        "rows": [flow_row(flow) for flow in page],
        "total": total,
        "limit": data.limit,
        "offset": data.offset,
    }


@operation(
    "flow.flow.detail",
    kind="query",
    permission=VIEW,
    input=FlowRefIn,
    output=FlowOut,
    ai={
        "description": "One automation by its id or its name («the welcome automation»): its trigger, its steps, "
        "the permissions it needs and the ones it lacks, and its last run."
    },
)
def flow_detail(ctx: OperationContext, data: FlowRefIn) -> dict:
    return flow_row(resolve_flow(data.id, data.flow, rows=with_last_run(live_flows())))


@operation(
    "flow.flow.status",
    kind="query",
    permission=VIEW,
    input=StatusIn,
    output=StatusOut,
    ai={
        "description": "Is it already set up here? For one event and one action: how many automations start with "
        "the event and may run the action, how many of those are on, and how many listen to the event with "
        "no permission granted yet. Three numbers, no names."
    },
)
def flow_status(ctx: OperationContext, data: StatusIn) -> dict:
    listening = live_flows().filter(
        trigger_kind=Flow.Trigger.EVENT, trigger_event=data.event
    )
    granted = listening.filter(grants__contains=[data.operation])
    return {
        "total": granted.count(),
        "enabled": granted.filter(enabled=True).count(),
        "unfinished": listening.filter(grants=[]).count(),
    }


# --- The ready-made automations the apps bring (FLOW-F33 to F36) -------------------------------------


def recipe_flow(ref: str, *, lock: bool = False) -> Flow | None:
    """The automation (not deleted) this business built from the recipe ``ref``, if any."""
    found = live_flows().filter(recipe=ref)
    return (found.select_for_update() if lock else found).first()


@operation(
    "flow.recipe.list",
    kind="query",
    permission=VIEW,
    input=RecipeListIn,
    output=RecipeListOut,
    ai={
        "description": "The ready-made automations the active apps bring («fill the gap when a customer cancels»), "
        "with what each one does, the permissions it asks for and why, and, when it was turned on here, its "
        "automation, whether it is on, whether its app brings a newer version and what a repair would add; "
        "and the ones this business cannot use, with why."
    },
)
def list_recipes(ctx: OperationContext, data: RecipeListIn) -> dict:
    offered, set_aside = recipes.shelf()
    mine = {flow.recipe: flow for flow in live_flows().exclude(recipe="")}
    rows = []
    with translation.override(ctx.language):
        for recipe in offered:
            built = recipes.build(recipe, ctx.language)
            reasons = recipes.reasons(recipe, ctx.language)
            flow = mine.get(recipe.ref)
            required = document.required_grants(flow.steps) if flow else []
            rows.append(
                {
                    "ref": recipe.ref,
                    "app": recipe.app.label,
                    "app_name": str(recipe.app.verbose_name),
                    "icon": recipe.app.icon,
                    "id": recipe.id,
                    **recipes.words(recipe, ctx.language),
                    "trigger": built["trigger"],
                    "steps": built["steps"],
                    "grants": [{"operation": name, "reason": reasons[name]} for name in recipes.grants(recipe)],
                    "installed": (
                        {
                            "flow_id": flow.id,
                            "name": flow.name,
                            "enabled": flow.enabled,
                            "outdated": flow.recipe_digest != recipes.digest(recipe),
                            "missing_grants": [name for name in required if name not in flow.grants],
                            "repair": recipes.missing_clauses(recipe, flow),
                        }
                        if flow
                        else None
                    ),
                }
            )
        aside = [
            {
                "ref": item.ref,
                "app": item.app.label,
                "app_name": str(item.app.verbose_name),
                "name": recipes.words(item, ctx.language)["name"],
                "code": item.code,
                "message": item.message,
                "apps": list(item.apps),
            }
            for item in set_aside
        ]
    return {"recipes": rows, "set_aside": aside}


# --- Why a run stopped ------------------------------------------------------------------------------

NOT_ALLOWED = _(
    "It tried to do something you have not allowed it to do («%(name)s»), so it stopped. "
    "Open Permissions and allow what it needs."
)
UNAVAILABLE = _(
    "«%(name)s» is not available in this business any more (its app is off), so it stopped."
)
INVALID_PARAMS = _("«%(name)s» did not accept the data it was given, so it stopped.")
CRASHED = _(
    "Something went wrong while doing «%(name)s», so it stopped. Nothing of that step was kept."
)
LOOP = _(
    "It was started by something its own steps did, so it stopped before doing anything."
)
CHAIN_TOO_LONG = _(
    "A chain of %(count)s automations started it, more than the %(max)s allowed, so it stopped before doing "
    "anything."
)
FILTER_UNREADABLE = _(
    "Its «Only when…» can no longer be read, so it did not go on. Open it, check «Only when…» and save it "
    "again."
)
CONDITION_UNREADABLE = _(
    "This «Only continue if…» can no longer be read, so it stopped. Open the automation, check this step "
    "and save it again."
)
RUN_IF_UNREADABLE = _(
    "The «Only if…» of this step can no longer be read, so it stopped. Open the automation, check this step "
    "and save it again."
)
HTTP_STATUS = _("«%(host)s» answered %(status)s, so it stopped.")
HTTP_BLOCKED = _("«%(host)s» is inside a private network, so it was not called.")
HTTP_FAILED = _("It could not reach «%(host)s», so it stopped.")
HTTP_TIMEOUT = _("«%(host)s» did not answer within %(seconds)s seconds, so it stopped.")
HTTP_INVALID = _("The address of this step is not a plain https address, so it was not called.")
SECRET_GONE = _(
    "The secret «%(name)s» no longer exists, so it stopped before calling. Save it again in this step."
)
SECRET_UNREADABLE = _(
    "The secret «%(name)s» cannot be opened with this server's key, so it stopped before calling. Save it "
    "again in this step."
)
SECRETS_KEY_GONE = _(
    "This server cannot use secrets (its encryption key is missing), so it stopped before calling."
)
CANCELLED_PAUSED = _("Cancelled: the automation was paused while it waited.")
CANCELLED_DELETED = _("Cancelled: the automation was deleted.")
ANSWERED_NO = _("Cancelled: %(who)s answered no to «%(title)s».")
NOBODY_ANSWERED = _("Cancelled: nobody answered «%(title)s» in time.")
ASSISTANT_ROUNDS = _("The assistant took its %(n)s turns without finishing, so it stopped.")
ASSISTANT_QUOTA = _(
    "The assistant's messages of this month are spent, so it stopped. They come back on the 1st; for more, "
    "upgrade the plan."
)
ASSISTANT_UNAVAILABLE = _("The assistant could not answer now, so it stopped: resume the run in a while.")
ASSISTANT_UNREACHABLE = _("It could not reach the assistant on erplora.com, so it stopped: resume the run in a while.")
ASSISTANT_REFUSED = _("erplora.com's assistant did not take the task, so it stopped.")
ASSISTANT_GONE = _("«%(name)s» is no longer allowed or available, so the assistant's change was not made.")
ASSISTANT_GONE_UNNAMED = _("That action is no longer allowed or available, so the assistant's change was not made.")

#: A change of the assistant no longer granted (code ``flow.not_allowed``), named for a person when it is read.
ASSISTANT_GONE_KEY = "flow.assistant_gone"
#: The engine's own reasons, by name (the code, but where one code says different things): a run and the entry of
#: the step that failed keep the name and its values, and the reason is said when it is read, in the reader's
#: language (FLOW-F16). A name never equals a code it does not say whole: a run kept with its words alone
#: (before names were kept) is said by its code (``say``).
REASONS = {
    HIGH_RISK_CODE: HIGH_RISK,
    "flow.not_allowed": NOT_ALLOWED,
    "flow.action_unavailable": UNAVAILABLE,
    "flow.invalid_params": INVALID_PARAMS,
    "flow.step_crashed": CRASHED,
    "flow.loop": LOOP,
    "flow.chain_too_long": CHAIN_TOO_LONG,
    "flow.filter_unreadable": FILTER_UNREADABLE,
    "flow.condition_unreadable": CONDITION_UNREADABLE,
    "flow.run_if_unreadable": RUN_IF_UNREADABLE,
    "flow.http_status": HTTP_STATUS,
    "flow.http_blocked": HTTP_BLOCKED,
    "flow.http_failed": HTTP_FAILED,
    "flow.http_timeout": HTTP_TIMEOUT,
    "flow.http_url_invalid": HTTP_INVALID,
    "flow.secret_not_found": SECRET_GONE,
    "flow.secret_unreadable": SECRET_UNREADABLE,
    "flow.secrets_key_missing": SECRETS_KEY_GONE,
    "flow.paused": CANCELLED_PAUSED,
    "flow.deleted": CANCELLED_DELETED,
    "flow.question_rejected": ANSWERED_NO,
    "flow.question_expired": NOBODY_ANSWERED,
    "flow.assistant_too_many_rounds": ASSISTANT_ROUNDS,
    "flow.assistant_quota_exceeded": ASSISTANT_QUOTA,
    "flow.assistant_unavailable": ASSISTANT_UNAVAILABLE,
    "flow.assistant_unreachable": ASSISTANT_UNREACHABLE,
    "flow.assistant_refused": ASSISTANT_REFUSED,
    ASSISTANT_GONE_KEY: ASSISTANT_GONE,
}
#: The words of the app's screens, by language: how the History names an action («Create a task»).
LOCALES = Path(__file__).resolve().parent / "frontend" / "locale"


@functools.cache
def _screen_words(language: str) -> dict:
    path = LOCALES / f"{language}.json"
    return json.loads((path if path.exists() else LOCALES / "en.json").read_text(encoding="utf-8"))["flow"]


def action_label(op: Operation, language: str) -> str:
    """``op`` as the History names it: its own words or, without them, its verb, app and thing (``actionLabel`` of
    ``frontend/lib/phrasing.ts``)."""
    words = _screen_words(language)
    curated = words["actions"].get(op.name.replace(".", "__"))
    if curated:
        return curated
    _app, entity, verb = ([*op.name.split(".", 2), "", ""])[:3]
    verb_word = words["verbs"].get(verb) or verb.replace("_", " ")
    return f"{verb_word} · {hub_assistant.app_name(op)} ({entity.replace('_', ' ')})"


def say(reason: dict, said: str = "") -> str:
    """Why a run (or its step) stopped, in the active language: the engine's own words for a reason it named
    (``{"key", "values"}``); ``said`` — what an action of another app answered, as it answered, or a reason kept
    before its values were — for anything else."""
    key = reason.get("key")
    words = REASONS.get(key)
    if words is None:
        return said
    values = dict(reason.get("values") or {})
    if key == ASSISTANT_GONE_KEY:
        # The action it wanted, named as the History names it now; one that no longer exists, not at all.
        op = registry.get(str(values.get("operation", "")))
        if op is None:
            return str(ASSISTANT_GONE_UNNAMED)
        values["name"] = action_label(op, (translation.get_language() or "en").split("-")[0])
    try:
        return str(words) % values
    except (KeyError, TypeError, ValueError):
        return said


def _said_entry(entry: dict) -> dict:
    """A log entry with the reason of its failure, if any, in the active language (its name stays inside)."""
    error = entry.get("error")
    if not isinstance(error, dict):
        return entry
    shown = {name: value for name, value in error.items() if name != "reason"}
    shown["message"] = say(error.get("reason") or {"key": error.get("code")}, error.get("message", ""))
    return {**entry, "error": shown}


# --- Runs and drafts --------------------------------------------------------------------------------


#: How long a run that stopped by an error keeps what its steps left, to be resumed (FLOW-F24); after
#: that, the hourly prune forgets it (what a step read is never kept longer than a wait could).
RESUME_DAYS = 7
#: Failures that happened before any step ran, or that the same steps would hit again for sure.
NOT_RESUMABLE = frozenset(
    {
        "flow.loop_stopped",
        "flow.filter_unreadable",
        "flow.condition_unreadable",
        "flow.run_if_unreadable",
        HIGH_RISK_CODE,
        # A call to an address that is not plain https, or inside a private network: the same steps would
        # be refused again (FLOW-F27); the step has to change, and a resumed run keeps the steps it started with.
        "flow.http_url_invalid",
        "flow.http_blocked",
    }
)
#: The kinds of step whose output later steps read (``steps.<id>``).
LEAVES = ("command", "query", "http", "ask", "assistant")
RUN_NOT_RESUMABLE = _("Only a run that stopped by an error at one of its steps can be resumed.")
BEFORE_ANY_STEP = _(
    "This run cannot be resumed: it stopped before doing any step, or would stop there again. Run it "
    "again whole."
)
RESUME_EXPIRED = _(
    "This run can no longer be resumed: it stopped more than %(days)s days ago and no longer keeps what "
    "its steps did. Run it again whole."
)


def resume_problem(run: FlowRun, now) -> tuple[str, str] | None:
    """``(code, message)`` of why ``run`` cannot be resumed at the step that failed, or ``None``.

    It must have stopped by an error at a step (its last entry), still keep what every earlier step left
    and have stopped less than ``RESUME_DAYS`` ago.
    """
    steps = run.definition.get("steps", [])
    if run.status != FlowRun.Status.FAILED:
        return "flow.run_not_resumable", str(RUN_NOT_RESUMABLE)
    last = run.log[-1] if run.log else {}
    at_a_step = (
        run.step_index < len(steps)
        and last.get("outcome") == "failed"
        and last.get("step") == steps[run.step_index].get("id")
    )
    if not at_a_step or run.error_code in NOT_RESUMABLE:
        return "flow.run_not_resumable", str(BEFORE_ANY_STEP)
    ended = run.finished_at or run.started_at
    lost = any(
        step.get("kind") in LEAVES and step.get("id") not in run.outputs
        for step in steps[: run.step_index]
    )
    if lost or ended < now - dt.timedelta(days=RESUME_DAYS):
        return "flow.resume_expired", str(RESUME_EXPIRED) % {"days": RESUME_DAYS}
    return None


def run_row(run: FlowRun) -> dict[str, Any]:
    return {
        "resumable": resume_problem(run, timezone.now()) is None,
        "id": run.id,
        "flow_id": run.flow_id,
        "flow_version": run.flow_version,
        "status": run.status,
        "trigger_kind": run.trigger_kind,
        "event_name": run.event_name,
        "input": run.input,
        "step_index": run.step_index,
        "steps_total": len(run.definition.get("steps", [])),
        "log": [_said_entry(entry) for entry in run.log],
        "error_code": run.error_code,
        "error_message": say(run.error_reason or {"key": run.error_code}, run.error_message),
        "resume_at": run.resume_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "started_by": run.started_by,
    }


@operation(
    "flow.run.list",
    kind="query",
    permission=VIEW,
    input=RunListIn,
    output=RunPageOut,
    ai={
        "description": "What an automation did, the newest first: each run's status (finished well, stopped by a "
        "condition, stopped by an error, waiting, cancelled), each step and the reason of a failure; and how "
        "many runs failed («why did the welcome automation fail?»)."
    },
)
def list_runs(ctx: OperationContext, data: RunListIn) -> dict:
    runs = FlowRun.objects.filter(flow_id=data.flow_id)
    failed = runs.aggregate(failed=Count("id", filter=Q(status=FlowRun.Status.FAILED)))[
        "failed"
    ]
    if data.status is not None:
        runs = runs.filter(status=data.status)
    total = runs.count()
    page = runs.order_by("-started_at", "-id")[data.offset : data.offset + data.limit]
    with translation.override(ctx.language):
        rows = [run_row(run) for run in page]
    return {
        "rows": rows,
        "total": total,
        "limit": data.limit,
        "offset": data.offset,
        "failed": failed,
    }


def run_label(run: FlowRun, language: str) -> str:
    """As the History names a run, with its automation in front (out of its History it says whose): «Welcome · Oct 15,
    2026, 9:00 PM», when it started at the business's hour."""
    return f"{run.flow.name} · {_moment_words(run.started_at.isoformat(), language)}"


@operation(
    "flow.run.get",
    kind="query",
    permission=VIEW,
    input=RunRefIn,
    output=RunDetailOut,
    ai={
        "description": "One run by its id (its reference in the History): how it ended or where it waits, each step, "
        "the reason of a failure and whether it can be resumed; named by its automation and when it started."
    },
)
def get_run(ctx: OperationContext, data: RunRefIn) -> dict:
    found = FlowRun.objects.select_related("flow").filter(pk=data.id).first()
    with translation.override(ctx.language):
        if found is None:
            raise NotFound(str(RUN_NOT_FOUND))
        return {**run_row(found), "label": run_label(found, ctx.language)}


def draft_row(draft: Draft) -> dict[str, Any]:
    return {
        "id": draft.id,
        "name": draft.name,
        "definition": draft.definition,
        "notes": draft.notes,
        "status": draft.status,
        "flow_id": draft.flow_id,
        "created_at": draft.created_at,
        "created_by": draft.created_by,
    }


@operation(
    "flow.draft.list",
    kind="query",
    permission=VIEW,
    input=DraftListIn,
    output=Page[DraftOut],
    ai={
        "description": "The automations the assistant proposed that are waiting for a person, the newest first."
    },
)
def list_drafts(ctx: OperationContext, data: DraftListIn) -> dict:
    drafts = Draft.objects.filter(status=Draft.Status.PENDING)
    total = drafts.count()
    page = drafts.order_by("-created_at", "-id")[data.offset : data.offset + data.limit]
    return {
        "rows": [draft_row(draft) for draft in page],
        "total": total,
        "limit": data.limit,
        "offset": data.offset,
    }


@operation(
    "flow.draft.get",
    kind="query",
    permission=VIEW,
    input=DraftRefIn,
    output=DraftOut,
    ai={
        "description": "One draft the assistant proposed, by its id: its name, its steps, what it could not work out "
        "and whether it still waits, was used or was discarded."
    },
)
def get_draft(ctx: OperationContext, data: DraftRefIn) -> dict:
    found = Draft.objects.filter(pk=data.id).first()
    if found is None:
        with translation.override(ctx.language):
            raise NotFound(str(DRAFT_NOT_FOUND))
    return draft_row(found)


# --- The last real event and «Try it» ---------------------------------------------------------------


def last_event(ctx: OperationContext, name: str) -> OutboxEvent | None:
    return (
        OutboxEvent.objects.filter(
            scope_kind=ctx.scope.kind, scope_key=ctx.scope.key, name=name
        )
        .order_by("-created_at", "-id")
        .first()
    )


def sample_of(ctx: OperationContext, name: str) -> dict[str, Any]:
    event = last_event(ctx, name)
    if event is None:
        return {"found": False, "event": name, "at": None, "payload": {}}
    return {
        "found": True,
        "event": name,
        "at": event.created_at,
        "payload": event.payload,
    }


@operation(
    "flow.event.sample",
    kind="query",
    permission=MANAGE,
    input=SampleIn,
    output=SampleOut,
    ai={
        "description": "The last time an event really happened in this business, with what it brought."
    },
)
def event_sample(ctx: OperationContext, data: SampleIn) -> dict:
    return sample_of(ctx, data.event)


#: The data of an action a person reads, by action: a message to a customer (FLOW-F31), its text and its template's
#: values. Each datum inserted in them is said in words (``words_for``); every other action's data go to a machine.
PERSON_PARAMS: dict[str, frozenset[str]] = {"whatsapp_inbox.message.notify": frozenset({"text", "template"})}
#: A yes or no inserted in a text a person reads.
YES = pgettext_lazy("datum", "Yes")
NO = pgettext_lazy("datum", "No")


def _is_money(name: str, prop: dict) -> bool:
    """An amount in cents, as its schema declares it: the rule of the assistant's card (base/assistant.py)."""
    return name.endswith("_cents") or "in cents" in str(prop.get("description", "")).lower()


def _money_paths(steps: list[dict]) -> frozenset[str]:
    """The paths (``steps.<id>.<field>``) of the amounts in cents the steps' actions and reads declare they leave: their
    output's schema (a read's first row). An event declares none."""
    found: set[str] = set()
    for step in steps:
        op = registry.get(str(step.get("operation") or "")) if step.get("kind") in ("command", "query") else None
        if op is None:
            continue
        schema = op.output.model_json_schema()
        defs = schema.get("$defs", {})
        props = schema.get("properties", {})
        if op.kind == "query" and "rows" in props:
            props = _resolve_ref(props["rows"].get("items", {}), defs).get("properties", {})
        found |= {f"steps.{step.get('id')}.{name}" for name, prop in props.items() if _is_money(name, prop)}
    return frozenset(found)


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


def words_for(steps: list[dict], language: str, scope: Scope) -> document.Say:
    """How a text a person reads — a question (FLOW-F28), a message to a customer (FLOW-F31) — says each datum it
    inserts, as the assistant's card says it (BASE-F97): a yes or no as «Yes»/«No», an ISO day, hour or instant as
    ``language`` writes it at the business's hour, and an amount the step that left it declares in cents in the
    business's currency; anything else as it is. An event declares no schema: a number it brings is never guessed as
    money."""
    money = _money_paths(steps)
    currency = functools.cache(lambda: _currency(scope))

    def say(path: str, value: Any) -> str:
        if isinstance(value, bool):
            with translation.override(language):
                return str(YES if value else NO)
        if isinstance(value, str):
            return _moment_words(value, language) or value
        if isinstance(value, int) and path in money and currency():
            return money_text(value, currency(), language=language)
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


def _clauses(failed: list[dict]) -> list[dict]:
    return [
        {"path": clause["path"], "op": clause["op"], "value": clause["value"]}
        for clause in failed
    ]


def _try_call(step: Any, values: dict, grants: list[str], unknown_steps: set[str]) -> dict:
    """What «Try it» says of a call: where it would go and with what — every secret as ``vault.MASK`` and
    the call's key as «…» (it is known when it runs) —, never calling."""
    reads = [
        path
        for path in document.references([step.url, *step.headers.values(), step.body])
        if path.startswith("steps.") and path.split(".")[1] in unknown_steps
    ]
    if reads:
        return {"outcome": "cannot_tell", "unknown": reads}
    masked = dict.fromkeys(document.secret_names(step.model_dump()), vault.MASK)
    url, headers, body = document.render_call(step.model_dump(), values, masked, "…")
    params = {"method": step.method, "url": url, "headers": headers, "body": body, "host": document.host_of(step.url)}
    granted = document.http_grant(step.url) in grants
    return {"outcome": "would_call" if granted else "not_allowed", "params": params}


@operation(
    "flow.flow.test",
    kind="query",
    permission=MANAGE,
    input=TestIn,
    output=TestOut,
    ai={
        "description": "Try an automation without effects: walk its steps against the last time its event really "
        "happened here and say, step by step, what it would do, what would come out empty, what the action "
        "would refuse, where a condition would stop it and what it is not allowed yet. Executes nothing."
    },
)
def try_flow(ctx: OperationContext, data: TestIn) -> dict:
    grants = resolve_flow(data.id, None).grants if data.id is not None else []
    try:
        tried = TestDocumentIn.model_validate_json(data.document)
    except pydantic.ValidationError as invalid:
        fields = {f"document.{key}": message for key, message in validation_fields(invalid).items()}
        raise InvalidPayload(next(iter(fields.values())), fields=fields) from None
    trigger = tried.trigger
    sample = (
        sample_of(ctx, trigger.event)
        if trigger.kind == "event"
        else {"found": False, "event": "", "at": None, "payload": {}}
    )
    values = {"input": sample["payload"], "steps": {}}
    trigger_failed = (
        document.failed_clauses(trigger.filter, values)
        if trigger.kind == "event" and sample["found"]
        else []
    )
    stopped = bool(trigger_failed)
    operations = catalog_operations()
    # What a person would read is said as the person trying it reads it (who saves it, in their language).
    say = words_for([step.model_dump() for step in tried.steps], ctx.language, ctx.scope)
    unknown_steps: set[str] = set()
    steps = []
    for step in tried.steps:
        out: dict[str, Any] = {
            "id": step.id,
            "kind": step.kind,
            "operation": getattr(step, "operation", ""),
        }
        if stopped:
            steps.append(out | {"outcome": "not_reached"})
            continue
        run_if = getattr(step, "run_if", None)
        if run_if and not any(
            path.startswith("steps.") and path.split(".")[1] in unknown_steps
            for path in [*run_if, *document.references(list(run_if.values()))]
        ):
            skipped = document.failed_clauses(run_if, values)
            if skipped:
                steps.append(out | {"outcome": "skipped", "failed": _clauses(skipped)})
                continue
        if step.kind == "delay":
            steps.append(out | {"outcome": "waits", "seconds": step.seconds})
            continue
        if step.kind == "http":
            steps.append(out | _try_call(step, values, grants, unknown_steps))
            unknown_steps.add(step.id)
            continue
        if step.kind == "ask":
            # Nothing is asked; what the person would answer is not known here.
            texts = {"title": document.fill(step.title, values, say), "details": document.fill(step.details, values, say)}
            steps.append(out | {"outcome": "would_ask", "params": texts | {"role": step.role, "hours": step.hours}})
            unknown_steps.add(step.id)
            continue
        if step.kind == "assistant":
            # Nothing is asked: what the assistant would answer is not known here.
            asked = {"prompt": document.fill(step.prompt, values), "tools": list(step.tools), "mode": step.mode}
            steps.append(out | {"outcome": "would_ask_assistant", "params": asked})
            unknown_steps.add(step.id)
            continue
        if step.kind == "condition":
            reads = list(step.when)
            if any(
                path.startswith("steps.") and path.split(".")[1] in unknown_steps
                for path in reads
            ):
                steps.append(out | {"outcome": "cannot_tell"})
                continue
            failed = document.failed_clauses(step.when, values)
            stopped = bool(failed)
            steps.append(
                out
                | {
                    "outcome": "stops_here" if failed else "would_run",
                    "failed": _clauses(failed),
                }
            )
            continue
        unknown_steps.add(step.id)
        op = operations.get(step.operation)
        mapped, empty, unknown = map_params(
            step.params, values, unknown_steps, say=say, person=PERSON_PARAMS.get(step.operation, ())
        )
        out |= {"params": mapped, "empty": empty, "unknown": unknown}
        grantable = grantable_operations().get(step.operation)
        if grantable is not None and needs_a_person(grantable):
            steps.append(out | {"outcome": "high_risk"})
        elif op is None or op.kind != step.kind:
            steps.append(out | {"outcome": "unavailable"})
        elif step.operation not in grants:
            steps.append(out | {"outcome": "not_allowed"})
        elif unknown:
            steps.append(out | {"outcome": "cannot_tell"})
        else:
            try:
                op.input.model_validate(
                    prepared(op, step.kind, getattr(step, "result", "first"), mapped)
                )
            except pydantic.ValidationError as invalid:
                steps.append(
                    out | {"outcome": "refused", "errors": validation_fields(invalid)}
                )
            else:
                steps.append(out | {"outcome": "would_run"})
    return {
        "sample": sample,
        "starts": not trigger_failed,
        "trigger_failed": _clauses(trigger_failed),
        "steps": steps,
    }


# --- Questions (FLOW-F29) ----------------------------------------------------------------------------


def can_answer(ctx: OperationContext, role: str) -> bool:
    """Whether ``ctx`` may answer a question asked of ``role``: that role's people, and whoever runs the
    business, always."""
    return ctx.has(ROLE_PERMISSION.get(role, MANAGE)) or ctx.has(MANAGE)


def proposal_fields(ctx: OperationContext, question: Question) -> list[dict]:
    """The data of the change the assistant wants that ``question`` waits on (FLOW-F38, «Ask me first»), each as its
    confirmation card in the chat says it (BASE-F97 step 2): read now, as ``ctx``'s person and in their language, so
    a record is named only for whoever may read it, never for the automation nor by its id. A run waits on one change
    at a time, the one its assistant step holds; an «Ask someone first» question, or a change whose action is gone,
    has none."""
    run = question.run
    steps = run.definition.get("steps") or []
    step = steps[run.step_index] if run.step_index < len(steps) else {}
    proposal = (run.outputs.get(TURN) or {}).get("proposal") if step.get("kind") == "assistant" else None
    op = registry.get(str(proposal.get("operation") or "")) if proposal else None
    if op is None:
        return []
    try:
        arguments = json.loads(proposal.get("arguments") or "{}")
    except ValueError:
        arguments = {}
    return hub_assistant.card(op, arguments if isinstance(arguments, dict) else {}, ctx.language, ctx)["fields"]


def question_row(question: Question, fields: list[dict] | None = None) -> dict[str, Any]:
    return {
        "id": question.id,
        "flow_id": question.flow_id,
        "flow_name": question.flow.name,
        "run_id": question.run_id,
        "title": question.title,
        "details": question.details,
        "role": question.role,
        "on_no": question.on_no,
        "on_timeout": question.on_timeout,
        "expires_at": question.expires_at,
        "created_at": question.created_at,
        "fields": fields or [],
    }


@operation(
    "flow.question.list",
    kind="query",
    permission=ANSWER,
    input=QuestionListIn,
    output=QuestionPageOut,
    ai={
        "description": "«Waiting for your answer»: the questions automations asked and are waiting on that this person may "
        "answer (their role's, or all of them for whoever runs the business), the soonest to expire first, "
        "up to 100."
    },
)
def list_questions(ctx: OperationContext, data: QuestionListIn) -> dict:
    roles = [role for role in ROLE_PERMISSION if can_answer(ctx, role)]
    pending = (
        Question.objects.select_related("flow", "run")
        .filter(status=Question.Status.PENDING, role__in=roles, run__status=FlowRun.Status.ASKING)
        .order_by("expires_at", "id")[:100]
    )
    return {"rows": [question_row(question, proposal_fields(ctx, question)) for question in pending]}


@operation(
    "flow.question.get",
    kind="query",
    permission=ANSWER,
    input=QuestionRefIn,
    output=QuestionOut,
    ai={
        "description": "One question an automation asked and is waiting on, by its id, as «Waiting for your answer» "
        "shows it: what it asks, its details, the change of the assistant it waits on, if any, and until when. Only "
        "the role it was asked of, or whoever runs the business."
    },
)
def get_question(ctx: OperationContext, data: QuestionRefIn) -> dict:
    found = Question.objects.select_related("flow", "run").filter(pk=data.id).first()
    with translation.override(ctx.language):
        if found is None:
            raise NotFound(str(QUESTION_NOT_FOUND), code="flow.question_not_found")
        if not can_answer(ctx, found.role):
            raise PermissionDenied(str(QUESTION_NOT_YOURS), code="flow.question_not_yours")
        if found.status != Question.Status.PENDING or found.run.status != FlowRun.Status.ASKING:
            raise NotFound(str(QUESTION_CLOSED), code="flow.question_closed")
    return question_row(found, proposal_fields(ctx, found))


# --- Secrets (FLOW-F26) ------------------------------------------------------------------------------


def secret_row(secret: Secret) -> dict[str, Any]:
    """What is ever shown of a secret: its name and who changed it when; never its value."""
    return {
        "id": secret.id,
        "name": secret.name,
        "created_at": secret.created_at,
        "updated_at": secret.updated_at,
        "updated_by": secret.updated_by,
    }


@operation(
    "flow.secret.list",
    kind="query",
    permission=MANAGE,
    input=SecretListIn,
    output=SecretPageOut,
    ai={
        "description": "The NAMES of the secrets the automations' calls to other systems can use (never their "
        "values, which nothing gives back), and whether this server can keep secrets."
    },
)
def list_secrets(ctx: OperationContext, data: SecretListIn) -> dict:
    return {
        "rows": [secret_row(secret) for secret in Secret.objects.order_by("name", "id")[:100]],
        "available": vault.available(),
    }
