"""Write operations of the flow app, and the engine that runs the automations.

One operation = one transaction, with its events in the outbox. A write on an automation locks its row
(``select_for_update``) before it looks at it, so two saves, or a save and a run, wait for each other.
What a document names (an event, an action, a read) is checked against the active apps
(``queries.catalog_problems``) and refused by field; nothing fails in silence.

**The engine.** A run starts in ``flow.run.react`` (an event of another app), ``flow.schedule.fire_due``
(a schedule or a date), ``flow.flow.run`` (by hand) and goes on in ``flow.run.resume_due`` (after a
wait). Its steps run in order, in the same transaction, each one an operation of another app nested in
a savepoint: a step that fails leaves nothing of its own and stops the run with its reason; the steps
before it stay. A step runs only if the automation was granted its operation, with the context
``flow_run:<id>`` (what it does carries that reference in the outbox) and the system's permissions,
in the language of whoever saved the automation. One run per automation and trigger key (the outbox
event's id): the row lock and the unique constraint make a repeated delivery start nothing. A run
started by an event that a run of the same automation caused, or by a chain of more than
``document.MAX_CHAIN`` automations, stops before doing anything (``flow.loop_stopped``).
"""

import datetime as dt
import json
import logging
import uuid
from typing import Any

import pydantic
from django.db import IntegrityError, transaction
from django.db.models.functions import Coalesce
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, InvalidPayload, NotFound, OperationError, PermissionDenied
from live.operations import Operation, get, operation
from live.outbox import record_event

from apps.flow import document, events, gateway, http, recipes, vault
from apps.flow.models import Draft, Flow, FlowRun, Question, Secret
from apps.flow.queries import (
    ASSISTANT_GONE_KEY,
    HIGH_RISK_CODE,
    LEAVES,
    ANSWER,
    MANAGE,
    RESUME_DAYS,
    SYSTEM,
    action_label,
    ask_first_catalog,
    asked_first,
    catalog_operations,
    catalog_problems,
    grantable_operations,
    needs_a_person,
    operation_problem,
    read_permissions,
    resume_problem,
    secret_row,
    draft_row,
    flow_row,
    live_flows,
    map_params,
    prepared,
    recipe_flow,
    resolve_flow,
    run_row,
    say,
    validation_fields,
    can_answer,
)
from apps.flow.schemas import (
    AnsweredOut,
    AnswerIn,
    AssistantRoundIn,
    AssistantRoundOut,
    ClaimAssistantOut,
    ClaimCallOut,
    CreateIn,
    DeletedOut,
    DraftOut,
    DraftProposeIn,
    DraftRefIn,
    DueIn,
    DueOut,
    EnabledIn,
    FlowOut,
    FlowRefIn,
    GrantIn,
    ReactIn,
    ReactOut,
    RecipeEnabledOut,
    RecipeRefIn,
    RecordAssistantIn,
    RecordCallIn,
    RunIn,
    RunOut,
    RunRefIn,
    SecretOut,
    SecretRefIn,
    SecretSetIn,
    UpdateIn,
)
from base import assistant as hub_assistant
from base import outbound

logger = logging.getLogger(__name__)

UNTITLED = _("Untitled automation")
COPY_OF = _("Copy of %(name)s")
NUMBERED = "%(name)s (%(n)s)"
PAST_DATE = _("That date and time has already passed.")
DISABLED = _("This automation is paused: turn it on to run it.")
DRAFT_DECIDED = _("That draft was already decided.")
GRANT_BEYOND_CALLER = _("You cannot allow what you may not do yourself: «%(name)s».")
DRAFT_NOT_FOUND = _("That draft does not exist in this business.")
RUN_NOT_FOUND = _("That run does not exist in this business.")
RECIPE_NOT_ON = _("This business has not turned that automation on: there is nothing to change.")
SECRETS_KEY_MISSING = _(
    "This server cannot keep secrets yet: its encryption key is missing. Nothing was saved."
)
SECRET_NOT_FOUND = _("There is no secret called «%(name)s».")
QUESTION_NOT_FOUND = _("That question does not exist in this business.")
QUESTION_NOT_YOURS = _("This question was asked of someone else: you cannot answer it.")
QUESTION_DECIDED = _("Someone already answered this one. Nothing was done twice.")
QUESTION_CLOSED = _("This question is closed: its automation no longer waits for it.")
QUESTION_TOO_LATE = _("Too late: nobody answered it in time, so it was closed. Nothing was done.")
ASSISTANT_WANTS = _("The assistant wants to change something in «%(app)s»")
APPROVAL_BEYOND_YOU = _("Only someone who may do it themselves can say yes to «%(name)s».")

#: How long the history keeps a finished run (hub#699: the old Hub's 90 days, fixed, for every hub).
HISTORY_DAYS = 90
#: At most this many runs go per pass: bounded, never one mass delete at the busiest hour.
PRUNE_BATCH = 500
#: The runs that can no longer go on: what the history may forget (waiting and running ones never).
FINISHED = (
    FlowRun.Status.SUCCEEDED,
    FlowRun.Status.STOPPED,
    FlowRun.Status.FAILED,
    FlowRun.Status.CANCELLED,
)

#: The actor prefix of what a run does (``flow_run:<id>``): the outbox keeps it, the loop guard reads it.
RUN_ACTOR = "flow_run:"
#: A call's ``Idempotency-Key`` is ``uuid5(IDEMPOTENCY_NAMESPACE, "<run id>:<step id>")``: the same in every
#: attempt of a run's step, another in every run (hub#2659, hub#2675).
IDEMPOTENCY_NAMESPACE = uuid.UUID("0199f6a0-6b1f-7c3e-9a51-3f1b2c4d5e6f")
#: How long a call that left holds its run: after it, a call that never answered is sent again, with the
#: same key (at least once; the old hub's 5 minutes).
CALL_LEASE_MINUTES = 5
#: How a call that did not answer 2xx ends: its code (and the name of its reason, ``queries.REASONS``).
_CALL_FAILURES = {
    http.STATUS: "flow.http_status",
    http.BLOCKED: "flow.http_blocked",
    http.FAILED: "flow.http_failed",
    http.TIMEOUT: "flow.http_timeout",
    http.INVALID: "flow.http_url_invalid",
}


def _actor(ctx: OperationContext) -> str:
    return "" if ctx.actor is None else str(ctx.actor)[:128]


def _business_zone() -> dt.tzinfo:
    """The business's time zone (phase 1: ``settings.TIME_ZONE``, Europe/Madrid)."""
    return timezone.get_default_timezone()


# --- The document on an automation ------------------------------------------------------------------


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


def _check(trigger: Any, steps: list[Any] | None, now: dt.datetime, saved_at: dt.datetime | None = None) -> None:
    """Refuses, by field, what this business does not have and a date that has passed — only a date that
    changes (``saved_at`` is the one it keeps): one that already went off must not block a rename."""
    problems, code = catalog_problems(trigger, steps or [])
    if trigger is not None and trigger.kind == "at" and trigger.at != saved_at and trigger.at <= now:
        problems["trigger.at"] = str(PAST_DATE)
    if problems:
        raise InvalidPayload(next(iter(problems.values())), code=code, fields=problems)


def _next_fire(flow: Flow, now: dt.datetime) -> dt.datetime | None:
    """When a schedule or a date starts it next, counted from ``now``; ``None`` while it never will."""
    if not flow.enabled:
        return None
    if flow.trigger_kind == Flow.Trigger.SCHEDULE:
        return document.next_fire(flow.schedule, now, _business_zone())
    if flow.trigger_kind == Flow.Trigger.AT and flow.run_at and flow.run_at > now:
        return flow.run_at
    return None


def _record_switch(ctx: OperationContext, flow: Flow) -> None:
    record_event(
        ctx,
        events.FLOW_ENABLED if flow.enabled else events.FLOW_PAUSED,
        {"id": str(flow.id)},
    )


# --- Create, change, switch, copy, delete -----------------------------------------------------------


def _decide_draft(
    ctx: OperationContext, draft_id, status: str, flow: Flow | None = None
) -> Draft:
    draft = Draft.objects.select_for_update().filter(pk=draft_id).first()
    if draft is None:
        raise NotFound(str(DRAFT_NOT_FOUND))
    if draft.status != Draft.Status.PENDING:
        raise Conflict(str(DRAFT_DECIDED), code="flow.draft_decided")
    draft.status = status
    draft.flow = flow
    draft.decided_by = _actor(ctx)
    draft.decided_at = timezone.now()
    draft.save(update_fields=["status", "flow", "decided_by", "decided_at"])
    return draft


@operation(
    "flow.flow.create",
    kind="command",
    permission=MANAGE,
    input=CreateIn,
    output=FlowOut,
    ai={
        "description": "Create an automation from scratch, from a gallery card or from the assistant's draft "
        "(`draft_id`, which is marked as used in the same step). It is born paused and with no permission "
        "(`flow.flow.set_enabled` turns it on); prefer `flow.draft.propose` when somebody asks you for one.",
        "risk": "normal",
    },
)
def create_flow(ctx: OperationContext, data: CreateIn) -> dict:
    now = timezone.now()
    _check(data.trigger, data.steps, now)
    with translation.override(ctx.language):
        name = data.name or str(UNTITLED)
    flow = Flow(
        name=name,
        steps=[step.model_dump(mode="json", exclude_none=True) for step in data.steps],
        language=ctx.language,
        created_by=_actor(ctx),
        updated_by=_actor(ctx),
    )
    _apply_trigger(flow, data.trigger)
    flow.next_fire_at = _next_fire(flow, now)
    refresh_search_text(flow)
    flow.save()
    record_event(ctx, events.FLOW_CREATED, {"id": str(flow.id)})
    if data.draft_id is not None:
        draft = _decide_draft(ctx, data.draft_id, Draft.Status.USED, flow)
        record_event(
            ctx, events.DRAFT_USED, {"id": str(draft.id), "flow_id": str(flow.id)}
        )
    return flow_row(flow)


@operation(
    "flow.flow.update",
    kind="command",
    permission=MANAGE,
    input=UpdateIn,
    output=FlowOut,
    ai={
        "description": "Change an automation, by its id or its name: its name, what starts it or its steps (to turn "
        "it on or pause it, `flow.flow.set_enabled`). Only what is sent changes; its permissions stay. Changing the trigger or the steps "
        "raises its version, and what is already running goes on with the version it started with.",
        "risk": "normal",
    },
)
def update_flow(ctx: OperationContext, data: UpdateIn) -> dict:
    now = timezone.now()
    flow = resolve_flow(data.id, data.flow, lock=True)
    _check(data.trigger, data.steps, now, saved_at=flow.run_at)
    changed_document = False
    if data.name is not None:
        with translation.override(ctx.language):
            flow.name = data.name or str(UNTITLED)
    if data.trigger is not None:
        before = (
            flow.trigger_kind,
            flow.trigger_event,
            flow.trigger_filter,
            flow.schedule,
            flow.run_at,
        )
        _apply_trigger(flow, data.trigger)
        changed_trigger = before != (
            flow.trigger_kind,
            flow.trigger_event,
            flow.trigger_filter,
            flow.schedule,
            flow.run_at,
        )
        changed_document |= changed_trigger
    else:
        changed_trigger = False
    if data.steps is not None:
        steps = [step.model_dump(mode="json", exclude_none=True) for step in data.steps]
        changed_document |= steps != flow.steps
        flow.steps = steps
    if changed_document:
        flow.version += 1
    if changed_trigger:
        flow.next_fire_at = _next_fire(flow, now)
    flow.language = ctx.language
    flow.updated_by = _actor(ctx)
    refresh_search_text(flow)
    flow.save()
    if changed_document or data.name is not None:
        record_event(
            ctx, events.FLOW_UPDATED, {"id": str(flow.id), "version": flow.version}
        )
    return flow_row(flow)


@operation(
    "flow.flow.set_enabled",
    kind="command",
    permission=MANAGE,
    input=EnabledIn,
    output=FlowOut,
    ai={
        "description": "Turn an automation on or pause it, by its id or its name («activate the welcome "
        "automation», «pause the cash close one»). A schedule turned on counts from now. Turning on one that "
        "lacks permissions leaves it doing nothing until they are granted: say so.",
        "risk": "high",
    },
)
def set_enabled(ctx: OperationContext, data: EnabledIn) -> dict:
    flow = resolve_flow(data.id, data.flow, lock=True)
    _switch(ctx, flow, data.enabled)
    return flow_row(flow)


def _switch(ctx: OperationContext, flow: Flow, enabled: bool) -> None:
    """Turns the locked ``flow`` on or pauses it (a schedule counts from now), with its event; nothing when
    it already is."""
    if flow.enabled != enabled:
        flow.enabled = enabled
        flow.next_fire_at = _next_fire(flow, timezone.now())
        flow.updated_by = _actor(ctx)
        flow.save(update_fields=["enabled", "next_fire_at", "updated_by", "updated_at"])
        _record_switch(ctx, flow)


@operation(
    "flow.flow.duplicate",
    kind="command",
    permission=MANAGE,
    input=FlowRefIn,
    output=FlowOut,
    ai={
        "description": "Copy an automation: «Copy of …», paused, with the same trigger and steps and none of its "
        "permissions or history.",
        "risk": "normal",
    },
)
def duplicate_flow(ctx: OperationContext, data: FlowRefIn) -> dict:
    original = resolve_flow(data.id, data.flow)
    with translation.override(ctx.language):
        base = str(COPY_OF) % {"name": original.name}
    taken = set(
        live_flows().filter(name__startswith=base).values_list("name", flat=True)
    )
    name, n = base, 2
    while name in taken:
        name, n = NUMBERED % {"name": base, "n": n}, n + 1
    copy = Flow(
        name=name[: Flow._meta.get_field("name").max_length],
        enabled=False,
        trigger_kind=original.trigger_kind,
        trigger_event=original.trigger_event,
        trigger_filter=original.trigger_filter,
        schedule=original.schedule,
        run_at=original.run_at,
        steps=original.steps,
        language=ctx.language,
        created_by=_actor(ctx),
        updated_by=_actor(ctx),
    )
    refresh_search_text(copy)
    copy.save()
    record_event(ctx, events.FLOW_CREATED, {"id": str(copy.id)})
    return flow_row(copy)


@operation(
    "flow.flow.delete",
    kind="command",
    permission=MANAGE,
    input=FlowRefIn,
    output=DeletedOut,
    ai={
        "description": "Delete an automation, by its id or its name: it stops at once, what was waiting is "
        "cancelled and its history stays. Cannot be undone: confirm it first.",
        "risk": "high",
    },
)
def delete_flow(ctx: OperationContext, data: FlowRefIn) -> dict:
    flow = resolve_flow(data.id, data.flow, lock=True)
    now = timezone.now()
    with translation.override(flow.language):
        for waiting in FlowRun.objects.select_for_update().filter(
            flow=flow, status__in=[FlowRun.Status.WAITING, FlowRun.Status.CALLING, FlowRun.Status.ASKING]
        ):
            Question.objects.filter(run=waiting, status=Question.Status.PENDING).update(
                status=Question.Status.CANCELLED, decided_at=now
            )
            _finish(ctx, waiting, FlowRun.Status.CANCELLED, now, _own("flow.deleted"))
    flow.deleted_at = now
    flow.enabled = False
    flow.next_fire_at = None
    flow.updated_by = _actor(ctx)
    flow.save(
        update_fields=[
            "deleted_at",
            "enabled",
            "next_fire_at",
            "updated_by",
            "updated_at",
        ]
    )
    record_event(ctx, events.FLOW_DELETED, {"id": str(flow.id)})
    return {"id": flow.id}


@operation(
    "flow.flow.grant",
    kind="command",
    permission=MANAGE,
    input=GrantIn,
    output=FlowOut,
    ai={
        "description": "Set the whole list of actions and reads an automation may run, by name: what is not in "
        "the list is withdrawn. A list that names something this business does not have is refused whole. "
        "An automation does nothing it was not allowed.",
        "risk": "high",
    },
)
def grant(ctx: OperationContext, data: GrantIn) -> dict:
    flow = resolve_flow(data.id, data.flow, lock=True)
    problems: dict[str, str] = {}
    code = "invalid_payload"
    asking = asked_first(flow.steps)
    for index, name in enumerate(data.operations):
        problem = operation_problem(name, asking=name in asking)
        if problem is not None:
            problem_code, problems[f"operations.{index}"] = problem
            if problem_code == HIGH_RISK_CODE:
                code = HIGH_RISK_CODE
    if problems:
        raise InvalidPayload(next(iter(problems.values())), code=code, fields=problems)
    # Nobody grants more than they may do themselves (an API key with flow:write included); a call's
    # origin is the automation's own permission, which whoever manages it already holds.
    offered = grantable_operations()
    beyond = {
        f"operations.{index}": str(GRANT_BEYOND_CALLER) % {"name": name}
        for index, name in enumerate(data.operations)
        if not name.startswith(document.HTTP_GRANT) and not ctx.has(offered[name].permission)
    }
    if beyond:
        raise PermissionDenied(next(iter(beyond.values())), fields=beyond)
    flow.grants = list(dict.fromkeys(data.operations))
    flow.updated_by = _actor(ctx)
    flow.save(update_fields=["grants", "updated_by", "updated_at"])
    record_event(ctx, events.FLOW_GRANTED, {"id": str(flow.id)})
    return flow_row(flow)


# --- The ready-made automations the apps bring (FLOW-F33 to F36) -------------------------------------


def _recipe_grants(ctx: OperationContext, recipe: recipes.Recipe) -> list[str]:
    """The recipe's permissions, which whoever turns it on or restores it must hold themselves (FLOW-F12's
    rule: nobody allows what they may not do)."""
    wanted = recipes.grants(recipe)
    offered = grantable_operations()  # an offered recipe asks only for what its steps may use (recipes.shelf)
    for name in wanted:
        if not ctx.has(offered[name].permission):
            raise PermissionDenied(str(GRANT_BEYOND_CALLER) % {"name": name})
    return wanted


def _recipe_flow(ref: str) -> Flow:
    flow = recipe_flow(ref, lock=True)
    if flow is None:
        raise NotFound(str(RECIPE_NOT_ON), code="flow.recipe_not_on")
    return flow


def _apply_recipe(ctx: OperationContext, flow: Flow, recipe: recipes.Recipe, now: dt.datetime) -> bool:
    """Writes today's recipe on ``flow`` (its name in ``ctx``'s language, trigger, steps and fingerprint);
    whether its trigger or steps changed."""
    built = recipes.build(recipe, ctx.language)
    parsed = CreateIn.model_validate(built)
    before = (flow.trigger_kind, flow.trigger_event, flow.trigger_filter, flow.schedule, flow.run_at, flow.steps)
    flow.name = parsed.name
    _apply_trigger(flow, parsed.trigger)
    flow.steps = [step.model_dump(mode="json", exclude_none=True) for step in parsed.steps]
    flow.recipe_digest = recipes.digest(recipe)
    flow.next_fire_at = _next_fire(flow, now)
    flow.language = ctx.language
    flow.updated_by = _actor(ctx)
    refresh_search_text(flow)
    return before != (flow.trigger_kind, flow.trigger_event, flow.trigger_filter, flow.schedule, flow.run_at, flow.steps)


@operation(
    "flow.recipe.enable",
    kind="command",
    permission=MANAGE,
    input=RecipeRefIn,
    output=RecipeEnabledOut,
    ai={
        "description": "Turn on a ready-made automation an app brings (`flow.recipe.list`). The first time it is "
        "built and left on with exactly the permissions the recipe asks for; afterwards the one already built is "
        "switched on as the owner left it. Say what it will do and what it may do before turning it on.",
        "risk": "high",
    },
)
def enable_recipe(ctx: OperationContext, data: RecipeRefIn) -> dict:
    recipe = recipes.find(data.recipe)
    wanted = _recipe_grants(ctx, recipe)
    now = timezone.now()
    flow = recipe_flow(recipe.ref, lock=True)
    if flow is None:
        flow = Flow(recipe=recipe.ref, grants=wanted, enabled=True, created_by=_actor(ctx))
        _apply_recipe(ctx, flow, recipe, now)
        try:
            with transaction.atomic():
                flow.save()
        except IntegrityError:
            # Turned on at the same time by someone else: theirs is the one (the unique recipe per business).
            flow = _recipe_flow(recipe.ref)
        else:
            for name in (events.FLOW_CREATED, events.FLOW_GRANTED, events.FLOW_ENABLED):
                record_event(ctx, name, {"id": str(flow.id)})
            return {"created": True, "flow": flow_row(flow)}
    if not flow.grants:
        # Left with no permission at all, it could do nothing: «on» means working, so it gets the recipe's.
        flow.grants = wanted
        flow.updated_by = _actor(ctx)
        flow.save(update_fields=["grants", "updated_by", "updated_at"])
        record_event(ctx, events.FLOW_GRANTED, {"id": str(flow.id)})
    _switch(ctx, flow, True)
    return {"created": False, "flow": flow_row(flow)}


@operation(
    "flow.recipe.disable",
    kind="command",
    permission=MANAGE,
    input=RecipeRefIn,
    output=FlowOut,
    ai={
        "description": "Turn off a ready-made automation an app brings: it is paused, never deleted; its permissions "
        "and its history stay, and turning it on again leaves it as it was.",
        "risk": "high",
    },
)
def disable_recipe(ctx: OperationContext, data: RecipeRefIn) -> dict:
    flow = _recipe_flow(data.recipe)
    _switch(ctx, flow, False)
    return flow_row(flow)


@operation(
    "flow.recipe.restore",
    kind="command",
    permission=MANAGE,
    input=RecipeRefIn,
    output=FlowOut,
    ai={
        "description": "Give a ready-made automation back the version its app brings today: its name, trigger, steps "
        "and exactly the recipe's permissions replace the owner's changes; it stays on or paused as it is and keeps "
        "its history. Confirm it: what the owner changed is lost.",
        "risk": "high",
    },
)
def restore_recipe(ctx: OperationContext, data: RecipeRefIn) -> dict:
    recipe = recipes.find(data.recipe)
    wanted = _recipe_grants(ctx, recipe)
    flow = _recipe_flow(recipe.ref)
    if _apply_recipe(ctx, flow, recipe, timezone.now()):
        flow.version += 1
    granted = flow.grants != wanted
    flow.grants = wanted
    flow.save()
    record_event(ctx, events.FLOW_UPDATED, {"id": str(flow.id), "version": flow.version})
    if granted:
        record_event(ctx, events.FLOW_GRANTED, {"id": str(flow.id)})
    return flow_row(flow)


@operation(
    "flow.recipe.repair",
    kind="command",
    permission=MANAGE,
    input=RecipeRefIn,
    output=FlowOut,
    ai={
        "description": "Repair a ready-made automation built from an older version that started in more cases than "
        "its app meant: only the conditions of «Only when…» its app added since are added; its name, steps, "
        "permissions and switch stay. Nothing changes when there is nothing to repair.",
        "risk": "normal",
    },
)
def repair_recipe(ctx: OperationContext, data: RecipeRefIn) -> dict:
    recipe = recipes.find(data.recipe)
    flow = _recipe_flow(recipe.ref)
    missing = recipes.missing_clauses(recipe, flow)
    if missing:
        flow.trigger_filter = {**flow.trigger_filter, **missing}
        flow.version += 1
        flow.updated_by = _actor(ctx)
        flow.save(update_fields=["trigger_filter", "version", "updated_by", "updated_at"])
        record_event(ctx, events.FLOW_UPDATED, {"id": str(flow.id), "version": flow.version})
    return flow_row(flow)


# --- Secrets (FLOW-F26) ------------------------------------------------------------------------------


@operation(
    "flow.secret.set",
    kind="command",
    permission=MANAGE,
    input=SecretSetIn,
    output=SecretOut,
    ai={
        "description": "Not an assistant tool: saves a secret (an API key, a token) by name for the automations' "
        "calls to other systems; saving a name again replaces its value. NEVER ask anybody for a secret's value in a "
        "conversation: the person types it in the automation's step, on the screen. Its value is never shown again.",
        "risk": "high",
    },
)
def set_secret(ctx: OperationContext, data: SecretSetIn) -> dict:
    try:
        sealed = vault.seal(data.value.get_secret_value())
    except vault.Unavailable:
        with translation.override(ctx.language):
            raise Conflict(str(SECRETS_KEY_MISSING), code="flow.secrets_key_missing") from None
    secret = Secret.objects.select_for_update().filter(name=data.name).first()
    if secret is None:
        secret = Secret(name=data.name, created_by=_actor(ctx))
    secret.ciphertext = sealed
    secret.updated_by = _actor(ctx)
    secret.save()
    record_event(ctx, events.SECRET_SAVED, {"id": str(secret.id)})
    return secret_row(secret)


@operation(
    "flow.secret.delete",
    kind="command",
    permission=MANAGE,
    input=SecretRefIn,
    output=DeletedOut,
    ai={
        "description": "Delete a secret by its name: the automations whose calls use it will fail with "
        "`flow.secret_not_found` until it is saved again. Confirm it first.",
        "risk": "high",
    },
)
def delete_secret(ctx: OperationContext, data: SecretRefIn) -> dict:
    secret = Secret.objects.select_for_update().filter(name=data.name).first()
    if secret is None:
        with translation.override(ctx.language):
            raise NotFound(str(SECRET_NOT_FOUND) % {"name": data.name})
    gone = secret.id
    secret.delete()
    record_event(ctx, events.SECRET_DELETED, {"id": str(gone)})
    return {"id": gone}


# --- The assistant's drafts -------------------------------------------------------------------------


@operation(
    "flow.draft.propose",
    kind="command",
    permission=MANAGE,
    input=DraftProposeIn,
    output=DraftOut,
    ai={
        "description": "Propose a DRAFT automation — «when X happens, do Y» — whenever somebody asks for something "
        "to happen on its own («create a flow that creates a task when a sale over 100 € is completed»). "
        "It does not run, holds no permissions and waits in Automations for a person to review it and turn "
        "it on. Steps are command, condition or delay only; money is in cents (100,00 € = 10000); use "
        "the event and action names of `flow.catalog.read`. Put what you guessed in `notes`, then say it "
        "is waiting in Automations and repeat your doubts.",
        "risk": "normal",
    },
)
def propose_draft(ctx: OperationContext, data: DraftProposeIn) -> dict:
    draft = Draft.objects.create(
        name=data.name,
        definition=data.definition.model_dump(mode="json", exclude_none=True),
        notes=list(data.notes),
        created_by=_actor(ctx),
    )
    record_event(ctx, events.DRAFT_PROPOSED, {"id": str(draft.id)})
    return draft_row(draft)


@operation(
    "flow.draft.dismiss",
    kind="command",
    permission=MANAGE,
    input=DraftRefIn,
    output=DraftOut,
    ai={
        "description": "Discard a draft the assistant proposed; it stays as a record.",
        "risk": "normal",
    },
)
def dismiss_draft(ctx: OperationContext, data: DraftRefIn) -> dict:
    draft = _decide_draft(ctx, data.id, Draft.Status.DISMISSED)
    record_event(ctx, events.DRAFT_DISMISSED, {"id": str(draft.id)})
    return draft_row(draft)


# --- The engine -------------------------------------------------------------------------------------


class StepFailed(Exception):
    """Why a step (or a run) stopped: ``message`` in the automation's language, for the steps after it; ``reason``,
    the engine's own reason by name and values (``_own``), said again when the History is read, in the reader's
    language; none for what an action of another app answered, which is said as it answered."""

    def __init__(
        self,
        code: str,
        message: str,
        fields: dict | None = None,
        technical: str = "",
        reason: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.fields, self.technical, self.reason = (
            code,
            message,
            fields,
            technical,
            reason or {},
        )

    def entry(self) -> dict:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.fields:
            error["fields"] = self.fields
        if self.technical:
            error["technical"] = self.technical
        if self.reason:
            error["reason"] = self.reason
        return error


def _own(code: str, key: str = "", *, fields: dict | None = None, technical: str = "", **values: Any) -> StepFailed:
    """A failure in the engine's own words (``queries.REASONS[key or code]``), said now in the active language (the
    automation's) and kept by name and values for whoever reads it later."""
    reason = {"key": key or code, "values": values}
    return StepFailed(code, say(reason), fields=fields, technical=technical, reason=reason)


def _log(run: FlowRun, step: dict, outcome: str, now: dt.datetime, **more: Any) -> None:
    entry = {"step": step["id"], "kind": step["kind"]}
    if step.get("operation"):
        entry["operation"] = step["operation"]
    run.log = [*run.log, {**entry, "outcome": outcome, **more, "at": now.isoformat()}]


def _start(
    ctx: OperationContext,
    flow: Flow,
    *,
    kind: str,
    key: str,
    input: dict,
    now: dt.datetime,
    event_name: str = "",
    chain: list[str] | None = None,
) -> FlowRun:
    started = FlowRun.objects.create(
        flow=flow,
        flow_version=flow.version,
        definition={"steps": flow.steps},
        trigger_kind=kind,
        trigger_key=key,
        event_name=event_name,
        input=input,
        chain=chain or [],
        started_by=_actor(ctx),
        started_at=now,
    )
    record_event(
        ctx, events.RUN_STARTED, {"id": str(started.id), "flow_id": str(flow.id)}
    )
    return started


def _finish(
    ctx: OperationContext,
    run: FlowRun,
    status: str,
    now: dt.datetime,
    failure: StepFailed | None = None,
) -> None:
    run.status = status
    run.finished_at = now
    run.resume_at = None
    # What the steps read (a customer's card…) is only needed while the run may go on: none is kept,
    # except by one that stopped by an error, which may be resumed for RESUME_DAYS (FLOW-F24).
    if status != FlowRun.Status.FAILED:
        run.outputs = {}
    run.error_code = failure.code if failure else ""
    run.error_message = failure.message if failure else ""
    run.error_reason = failure.reason if failure else {}
    run.save()
    record_event(
        ctx,
        events.RUN_FINISHED,
        {"id": str(run.id), "flow_id": str(run.flow_id), "status": status},
    )


def _step_context(ctx: OperationContext, run: FlowRun, flow: Flow, op: Operation) -> OperationContext:
    """What a step runs with: the run's reference as the actor, the permission of its own operation and
    the reads of its app (to answer with what it did), never every permission — the operation's own
    checks still apply (the old engine's «no elevation») —, in the language of whoever saved it."""
    return OperationContext(
        scope=ctx.scope,
        actor=f"{RUN_ACTOR}{run.id}",
        permissions=frozenset({op.permission}) | read_permissions(op),
        language=flow.language,
    )


def _read_output(step: dict, output: dict) -> tuple[dict, str, int]:
    """``(what the step leaves, outcome, count)`` of a read: the first row's fields (or none) and found/count."""
    if "rows" in output and isinstance(output["rows"], list):
        rows = output["rows"]
        count = int(output.get("total", len(rows)))
        first = rows[0] if rows and isinstance(rows[0], dict) else {}
    else:
        count, first = 1, output
    found = count > 0
    left = (dict(first) if step.get("result", "first") == "first" else {}) | {
        "found": found,
        "count": count,
    }
    return left, "found" if found else "not_found", count


def _operation_step(
    ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, data: dict
) -> tuple[dict, str, dict]:
    """Runs a command or query step; ``(what it leaves, outcome, log extras)`` or ``StepFailed``."""
    name = step["operation"]
    grantable = grantable_operations().get(name)
    if grantable is not None and needs_a_person(grantable):
        raise _own(HIGH_RISK_CODE, name=name)
    if name not in flow.grants:
        raise _own("flow.not_allowed", name=name)
    op = catalog_operations().get(name)
    if op is None or op.kind != step["kind"]:
        raise _own("flow.action_unavailable", name=name)
    step_ctx = _step_context(ctx, run, flow, op)
    values, _, _ = map_params(step.get("params", {}), data)
    try:
        payload = op.input.model_validate(
            prepared(op, step["kind"], step.get("result", "first"), values)
        )
    except pydantic.ValidationError as invalid:
        raise _own("flow.invalid_params", fields=validation_fields(invalid), name=name) from None
    try:
        result = op(step_ctx, payload)
    except NotFound:
        if step["kind"] == "query":
            return {"found": False, "count": 0}, "not_found", {"count": 0}
        raise
    except OperationError as refused:
        raise StepFailed(refused.code, refused.message, fields=refused.fields) from None
    except Exception as crash:
        logger.exception(
            "flow: step %s (%s) of run %s crashed", step["id"], name, step_ctx.actor
        )
        raise _own("flow.step_crashed", technical=f"{type(crash).__name__}: {crash}", name=name) from None
    output = result.model_dump(mode="json")
    if step["kind"] == "query":
        left, outcome, count = _read_output(step, output)
        return left, outcome, {"count": count}
    return output, "done", {}


def _fail(
    ctx: OperationContext, run: FlowRun, step: dict, failure: StepFailed, now: dt.datetime, left: dict | None = None
) -> bool:
    """Writes a step's failure; ``True`` when the run goes on (``on_error: continue``, FLOW-F25), leaving
    ``failed``, ``error_code``, ``error_message`` and ``left`` (a call's ``status``) for later steps."""
    if step.get("on_error") == "continue":
        _log(run, step, "failed", now, error=failure.entry(), continued=True)
        run.outputs = {
            **run.outputs,
            step["id"]: {"failed": True, "error_code": failure.code, "error_message": failure.message, **(left or {})},
        }
        run.step_index += 1
        return True
    _log(run, step, "failed", now, error=failure.entry())
    _finish(ctx, run, FlowRun.Status.FAILED, now, failure)
    return False


def _skipped(ctx: OperationContext, run: FlowRun, step: dict, data: dict, now: dt.datetime) -> bool | None:
    """Applies a step's «Only if…» (FLOW-F25): ``True`` when it is skipped (and the run goes on),
    ``None`` when it cannot be read (the run stopped), ``False`` when the step runs."""
    run_if = step.get("run_if")
    if not run_if:
        return False
    if not document.readable(run_if):
        _fail(ctx, run, {**step, "on_error": "stop"}, _own("flow.run_if_unreadable"), now)
        return None
    failed = document.failed_clauses(run_if, data)
    if not failed:
        return False
    _log(run, step, "skipped", now, failed=failed)
    if step["kind"] in LEAVES:
        run.outputs = {**run.outputs, step["id"]: {"skipped": True}}
    run.step_index += 1
    return True


def _advance(ctx: OperationContext, run: FlowRun, flow: Flow, now: dt.datetime) -> None:
    """Runs ``run``'s steps from ``step_index`` until it ends, waits or fails."""
    steps = run.definition.get("steps", [])
    with translation.override(flow.language):
        while run.step_index < len(steps):
            step = steps[run.step_index]
            data = {"input": run.input, "steps": run.outputs}
            if step["kind"] != "condition":
                skipped = _skipped(ctx, run, step, data, now)
                if skipped is None:
                    return
                if skipped:
                    continue
            if step["kind"] == "delay":
                until = now + dt.timedelta(seconds=step["seconds"])
                _log(
                    run,
                    step,
                    "waiting",
                    now,
                    seconds=step["seconds"],
                    until=until.isoformat(),
                )
                run.step_index += 1
                run.status = FlowRun.Status.WAITING
                run.resume_at = until
                run.save()
                record_event(
                    ctx,
                    events.RUN_PARKED,
                    {
                        "id": str(run.id),
                        "flow_id": str(flow.id),
                        "resume_at": until.isoformat(),
                    },
                )
                return
            if step["kind"] == "condition":
                if not document.readable(step.get("when")):
                    failure = _own("flow.condition_unreadable")
                    _fail(ctx, run, {**step, "on_error": "stop"}, failure, now)
                    return
                failed = document.failed_clauses(step["when"], data)
                if failed:
                    _log(run, step, "stopped", now, failed=failed)
                    _finish(ctx, run, FlowRun.Status.STOPPED, now)
                    return
                _log(run, step, "passed", now)
                run.step_index += 1
                continue
            if step["kind"] == "http":
                if _park_call(ctx, run, flow, step, now):
                    return
                continue
            if step["kind"] == "ask":
                _ask(ctx, run, flow, step, data, now)
                return
            if step["kind"] == "assistant":
                _park_assistant(ctx, run, flow, step, now)
                return
            try:
                left, outcome, extras = _operation_step(ctx, run, flow, step, data)
            except StepFailed as failure:
                if _fail(ctx, run, step, failure, now):
                    continue
                return
            except OperationError as refused:
                if _fail(ctx, run, step, StepFailed(refused.code, refused.message), now):
                    continue
                return
            run.outputs = {**run.outputs, step["id"]: left}
            _log(run, step, outcome, now, **extras)
            run.step_index += 1
        _finish(ctx, run, FlowRun.Status.SUCCEEDED, now)


# --- Calls to another system (FLOW-F27) ------------------------------------------------------------


def _call_allowed(run: FlowRun, flow: Flow, step: dict) -> StepFailed | None:
    """Why the automation may not make this call (its origin not granted), or ``None``."""
    grant = document.http_grant(str(step.get("url") or ""))
    if grant is None:
        return _own("flow.http_url_invalid")
    if grant not in flow.grants:
        return _own("flow.not_allowed", name=document.host_of(step["url"]))
    return None


def _park_call(ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, now: dt.datetime) -> bool:
    """Parks the run on a call and answers: the call never goes out from here (a web request would wait for
    the other system). Its ``flow.run.parked`` reaches the worker through the outbox relay, which makes it
    (``flow.run.call``); ``True`` when the run stops here (parked, or failed), ``False`` when it goes on (a
    refusal with «If it fails, carry on»)."""
    refused = _call_allowed(run, flow, step)
    if refused is not None:
        return not _fail(ctx, run, step, refused, now)
    _log(run, step, "calling", now, host=document.host_of(step["url"]))
    run.status = FlowRun.Status.CALLING
    run.resume_at = now
    run.save()
    record_event(
        ctx, events.RUN_PARKED, {"id": str(run.id), "flow_id": str(flow.id), "resume_at": now.isoformat()}
    )
    return True


def _go_on(ctx: OperationContext, run: FlowRun, flow: Flow, now: dt.datetime) -> None:
    run.status = FlowRun.Status.RUNNING
    run.resume_at = None
    record_event(ctx, events.RUN_RESUMED, {"id": str(run.id), "flow_id": str(flow.id)})
    _advance(ctx, run, flow, now)


def _call_failed(ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, failure: StepFailed, now, left=None) -> None:
    run.resume_at = None
    if _fail(ctx, run, step, failure, now, left):
        _go_on(ctx, run, flow, now)


# --- Asking the assistant (FLOW-F37 to F39) ---------------------------------------------------------

#: Where a step's conversation lives while the assistant thinks: no step id starts with «_» (``StepId``).
TURN = "_turn"
#: What the step's instructions add to the assistant's own: nobody is in front, and what a change does.
UNATTENDED = (
    "This is a step of the automation «%(name)s» and nobody is watching: never ask a question, decide with your "
    "tools and answer with what you found or did, in a few words."
)
#: What the assistant hears of a call of its answer that was not made: one change waits for a person at a time.
NOT_MADE = hub_assistant.error_content("not_made", "Not made: ask for one change at a time.")
CHANGES = {
    "ask": "A change you ask for is not made yet: it waits for a person's yes, so say what you proposed.",
    "auto": "A change you ask for is made at once, for real.",
}


def _park_assistant(ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, now: dt.datetime) -> None:
    """Parks the run on its «Ask the assistant» step and answers: the model is never asked from here (a web request
    would wait for it). Its ``flow.run.parked`` reaches the worker, which asks it (``flow.run.call``); a step resumed
    (FLOW-F24) starts its conversation again."""
    run.outputs = {key: value for key, value in run.outputs.items() if key != TURN}
    _back_to_assistant(ctx, run, flow, step, now)


def _back_to_assistant(ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, now: dt.datetime) -> None:
    """Parks the run for the worker to ask the assistant, with the step's conversation as it is."""
    _log(run, step, "thinking", now)
    run.status = FlowRun.Status.CALLING
    run.resume_at = now
    run.save()
    record_event(ctx, events.RUN_PARKED, {"id": str(run.id), "flow_id": str(flow.id), "resume_at": now.isoformat()})


def _offered(flow: Flow, step: dict) -> dict[str, Operation]:
    """The tools of the step: what it names AND the automation was granted, of the active apps, that the assistant
    may use; never a person's permissions. Cancelling a booking (``ASK_FIRST``) only when it asks first."""
    catalog = ask_first_catalog() if step.get("mode", "ask") == "ask" else catalog_operations()
    tools: dict[str, Operation] = {}
    for name in step.get("tools") or []:
        op = catalog.get(name)
        if name in flow.grants and op is not None and hub_assistant.is_tool(op):
            tools[name] = op
    return tools


def _instructions(ctx: OperationContext, flow: Flow, step: dict) -> str:
    try:
        business = get("base.business.get")(ctx, get("base.business.get").input()).model_dump()
    except OperationError:
        business = {}
    currency = business.get("currency") or "EUR"
    text = hub_assistant.instructions(
        language=flow.language,
        currency=currency,
        decimals=business.get("currency_decimals", 2),
        business=business.get("name") or "",
        screens={},
    )
    mode = CHANGES.get(step.get("mode", "ask"), CHANGES["ask"])
    return f"{text}\n\n{UNATTENDED % {'name': flow.name}} {mode}"


def _assistant_run(run_id: uuid.UUID) -> tuple[FlowRun | None, dict]:
    """The run whose «Ask the assistant» step is thinking, locked, and that step; ``None`` for any other."""
    run = FlowRun.objects.select_for_update(of=("self",)).select_related("flow").filter(pk=run_id).first()
    if run is None or run.status != FlowRun.Status.CALLING:
        return None, {}
    step = run.definition["steps"][run.step_index]
    return (run, step) if step["kind"] == "assistant" else (None, {})


def dispatch_assistant(scope: Scope, run_id: uuid.UUID) -> None:
    """Asks the assistant a run's step, with no transaction and no lock around a turn: ``flow.run.claim_assistant`` →
    a turn → ``flow.run.assistant_round`` (its reads and actions, in a transaction of their own) → … →
    ``flow.run.record_assistant``. A step another process holds, or that ended meanwhile, is left alone."""
    system = system_context(scope)
    claimed = get("flow.run.claim_assistant")(system, RunRefIn(id=run_id))
    if not claimed.claimed:
        return
    messages, continuation = claimed.messages, claimed.continuation
    while True:
        outbound.release()  # each turn waits on the assistant with no connection held
        try:
            answer = gateway.turn(
                scope.key, messages=messages, tools=claimed.tools, instructions=claimed.instructions, continuation=continuation
            )
        except gateway.Failed as failed:
            get("flow.run.record_assistant")(system, RecordAssistantIn(id=run_id, failure=failed.code))
            return
        if not answer.calls:
            get("flow.run.record_assistant")(system, RecordAssistantIn(id=run_id, text=answer.text))
            return
        went = get("flow.run.assistant_round")(
            system,
            AssistantRoundIn(id=run_id, text=answer.text, calls=answer.calls, continuation=answer.continuation),
        )
        if not went.go_on:
            return
        messages, continuation = went.messages, went.continuation


@operation(
    "flow.run.claim_assistant",
    kind="command",
    permission=SYSTEM,
    input=RunRefIn,
    output=ClaimAssistantOut,
    ai={
        "description": "System only: takes a run's «Ask the assistant» step to ask it (nobody else holds it), with "
        "its task filled in, the tools it may use and its conversation so far, for CALL_LEASE_MINUTES.",
        "risk": "normal",
    },
)
def claim_assistant(ctx: OperationContext, data: RunRefIn) -> dict:
    now = timezone.now()
    run = (
        FlowRun.objects.select_for_update(skip_locked=True, of=("self",))
        .select_related("flow")
        .filter(pk=data.id, status=FlowRun.Status.CALLING, resume_at__lte=now)
        .first()
    )
    if run is None:
        return {"claimed": False}
    flow = run.flow
    step = run.definition["steps"][run.step_index]
    if step["kind"] != "assistant":
        return {"claimed": False}
    with translation.override(flow.language):
        if flow.deleted_at is not None:
            _finish(ctx, run, FlowRun.Status.CANCELLED, now, _own("flow.deleted"))
            return {"claimed": False}
        turn = run.outputs.get(TURN) or {
            "messages": [{"role": "user", "content": document.fill(step["prompt"], {"input": run.input, "steps": run.outputs})}],
            "rounds": 0,
            "continuation": None,
        }
        instructions = _instructions(ctx, flow, step)
    run.outputs = {**run.outputs, TURN: turn}
    run.resume_at = now + dt.timedelta(minutes=CALL_LEASE_MINUTES)
    run.save(update_fields=["outputs", "resume_at"])
    return {
        "claimed": True,
        "messages": turn["messages"],
        "tools": [hub_assistant.tool_spec(op) for op in _offered(flow, step).values()],
        "instructions": instructions,
        "continuation": turn["continuation"],
    }


def _propose(
    ctx: OperationContext,
    run: FlowRun,
    flow: Flow,
    step: dict,
    op: Operation,
    call: Any,
    later: list[str],
    turn: dict,
    said: str,
    now: dt.datetime,
) -> None:
    """«Ask me first»: the change waits in «Waiting for your answer» with what it would send, and the run on it; a
    yes makes it (``answer_question``), a no or silence cancels the run, as a question that stops on a no. One change
    waits at a time: ``later``, the calls of the same answer behind it, are not made, and the assistant hears so with
    the change's result. Each change it asks for is a question of its own (``<step>:<n>``), so a late yes to one
    never approves the next."""
    try:
        arguments = json.loads(call.arguments or "{}")
    except ValueError:
        arguments = {}
    card = hub_assistant.card(op, arguments if isinstance(arguments, dict) else {}, flow.language)
    lines = [f"{field['label']}: {field['value']}" for field in card["fields"] if field["kind"] != "empty"]
    question = Question.objects.create(
        run=run,
        flow=flow,
        step_id=f"{step['id']}:{Question.objects.filter(run=run).count() + 1}",
        title=(str(ASSISTANT_WANTS) % {"app": card["app_name"]})[:300],
        details="\n".join([*([said] if said else []), *lines])[:2000],
        role="",
        on_no="stop",
        on_timeout="no",
        expires_at=now + dt.timedelta(hours=72),
        created_at=now,
    )
    proposal = {"call_id": call.call_id, "operation": op.name, "arguments": call.arguments, "later": later}
    run.outputs = {**run.outputs, TURN: {**turn, "proposal": proposal}}
    _log(run, step, "assistant_proposed", now, operation=op.name, until=question.expires_at.isoformat())
    run.status = FlowRun.Status.ASKING
    run.resume_at = question.expires_at
    run.save()
    record_event(ctx, events.QUESTION_ASKED, {"id": str(question.id), "run_id": str(run.id), "flow_id": str(flow.id)})
    record_event(
        ctx, events.RUN_PARKED, {"id": str(run.id), "flow_id": str(flow.id), "resume_at": question.expires_at.isoformat()}
    )


@operation(
    "flow.run.assistant_round",
    kind="command",
    permission=SYSTEM,
    input=AssistantRoundIn,
    output=AssistantRoundOut,
    ai={
        "description": "System only: runs the reads and actions the assistant asked for in a run's step, as the "
        "automation and only those it was offered; with «Ask me first» a change waits for a person's yes instead.",
        "risk": "normal",
    },
)
def assistant_round(ctx: OperationContext, data: AssistantRoundIn) -> dict:
    now = timezone.now()
    run, step = _assistant_run(data.id)
    turn = run.outputs.get(TURN) if run is not None else None
    if run is None or turn is None:
        return {"go_on": False}
    flow = run.flow
    tools = _offered(flow, step)
    asked = [{"call_id": call.call_id, "name": call.name, "arguments": call.arguments} for call in data.calls]
    messages = [*turn["messages"], {"role": "assistant", "content": data.text, "tool_calls": [
        {"id": call["call_id"], "type": "function", "function": {"name": call["name"], "arguments": call["arguments"]}}
        for call in asked
    ]}]
    with translation.override(flow.language):
        for index, call in enumerate(data.calls):
            op = hub_assistant.operation_of(call.name, tools)
            if op is None:
                content = hub_assistant.error_content("not_available", "That tool was not offered in this step.")
            elif op.kind == "command" and step.get("mode", "ask") == "ask":
                later = [behind.call_id for behind in data.calls[index + 1 :]]
                asked_turn = {**turn, "messages": messages, "continuation": data.continuation}
                _propose(ctx, run, flow, step, op, call, later, asked_turn, data.text, now)
                return {"go_on": False}
            else:
                outcome = hub_assistant.run_tool(_step_context(ctx, run, flow, op), op, call.arguments)
                _log(run, step, "assistant_used", now, operation=op.name, ok=outcome.outcome == "ok")
                content = outcome.content
            messages.append({"role": "tool", "tool_call_id": call.call_id, "content": content})
        rounds = turn["rounds"] + 1
        if _out_of_rounds(ctx, run, flow, step, rounds, now):
            return {"go_on": False}
    run.outputs = {**run.outputs, TURN: {**turn, "messages": messages, "rounds": rounds, "continuation": data.continuation}}
    run.resume_at = now + dt.timedelta(minutes=CALL_LEASE_MINUTES)
    run.save()
    return {"go_on": True, "messages": messages, "continuation": data.continuation}


#: How a turn that did not come back ends: the gateway's code → ours (and the name of its reason).
_ASSISTANT_FAILURES = {
    "assistant.quota_exceeded": "flow.assistant_quota_exceeded",
    "assistant.unreachable": "flow.assistant_unreachable",
    "assistant.provider_unavailable": "flow.assistant_unavailable",
    "assistant.internal_error": "flow.assistant_unavailable",
    "assistant.unavailable": "flow.assistant_unavailable",
    "rate_limited": "flow.assistant_unavailable",
}


@operation(
    "flow.run.record_assistant",
    kind="command",
    permission=SYSTEM,
    input=RecordAssistantIn,
    output=DueOut,
    ai={
        "description": "System only: records what the assistant answered in a run's step, for the steps after it, "
        "and goes on (or stops the run with why it did not answer); an answer for a run no longer thinking changes nothing.",
        "risk": "normal",
    },
)
def record_assistant(ctx: OperationContext, data: RecordAssistantIn) -> dict:
    now = timezone.now()
    run, step = _assistant_run(data.id)
    if run is None:
        return {"count": 0}
    flow = run.flow
    answered = (run.outputs.get(TURN) or {}).get("answered") or {}
    run.outputs = {key: value for key, value in run.outputs.items() if key != TURN}
    with translation.override(flow.language):
        if data.failure:
            code = _ASSISTANT_FAILURES.get(data.failure, "flow.assistant_refused")
            _call_failed(ctx, run, flow, step, _own(code, technical=data.failure), now)
            return {"count": 1}
        run.outputs = {**run.outputs, step["id"]: {"text": data.text, **answered}}
        _log(run, step, "assistant_answered", now, text=data.text[:2000])
        run.step_index += 1
        _go_on(ctx, run, flow, now)
    return {"count": 1}


def _out_of_rounds(ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, rounds: int, now: dt.datetime) -> bool:
    """Stops the step when the assistant spent its turns (``max_rounds``) and says so; ``True`` when it did."""
    if rounds < int(step.get("max_rounds", 6)):
        return False
    run.outputs = {key: value for key, value in run.outputs.items() if key != TURN}
    failure = _own("flow.assistant_too_many_rounds", n=rounds)
    _call_failed(ctx, run, flow, step, failure, now)
    return True


def _make_proposal(ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, answered: dict, now: dt.datetime) -> None:
    """A yes to the assistant's change: it is made now, by its own operation, as the automation (what it was granted
    now, not when it was proposed), and the step goes back to the assistant with what happened — the change's result
    (or its refusal) and, for the calls of that answer behind it, that they were not made —, so it can say it or ask
    for the next change. The run goes on with what it answers then (``record_assistant``); a change no longer
    granted stops the step."""
    turn = run.outputs.get(TURN) or {}
    proposal = turn.get("proposal") or {}
    name = str(proposal.get("operation") or "")
    op = _offered(flow, step).get(name)
    if op is None:
        run.outputs = {key: value for key, value in run.outputs.items() if key != TURN}
        if _fail(ctx, run, step, _own("flow.not_allowed", ASSISTANT_GONE_KEY, operation=name), now):
            _go_on(ctx, run, flow, now)
        return
    outcome = hub_assistant.run_tool(_step_context(ctx, run, flow, op), op, str(proposal.get("arguments") or "{}"))
    _log(run, step, "assistant_used", now, operation=op.name, ok=outcome.outcome == "ok")
    told = [{"role": "tool", "tool_call_id": proposal["call_id"], "content": outcome.content}]
    told += [{"role": "tool", "tool_call_id": call_id, "content": NOT_MADE} for call_id in proposal.get("later") or []]
    rounds = turn["rounds"] + 1
    run.outputs = {
        **run.outputs,
        TURN: {
            **{key: value for key, value in turn.items() if key != "proposal"},
            "messages": [*turn["messages"], *told],
            "rounds": rounds,
            "answered": answered,
        },
    }
    if not _out_of_rounds(ctx, run, flow, step, rounds, now):
        _back_to_assistant(ctx, run, flow, step, now)


# --- Asking someone first (FLOW-F28 to F30) ---------------------------------------------------------


def _who(ctx: OperationContext) -> str:
    """The name of whoever answers, as the history says it («Marta»)."""
    actor = ctx.actor
    if hasattr(actor, "get_username"):
        return (actor.get_full_name() or actor.get_username())[:128]
    return _actor(ctx)


def _ask(ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, data: dict, now: dt.datetime) -> None:
    """Leaves the step's question, its texts filled in now, in «Waiting for your answer» and parks the run on it. A
    question the run already asked at this step (a run resumed onto it) is not asked twice."""
    expires = now + dt.timedelta(hours=int(step.get("hours", 72)))
    question, _created = Question.objects.get_or_create(
        run=run,
        step_id=step["id"],
        defaults={
            "flow": flow,
            "title": document.fill(step["title"], data)[:300],
            "details": document.fill(step.get("details", ""), data),
            "role": step.get("role", ""),
            "on_no": step.get("on_no", "stop"),
            "on_timeout": step.get("on_timeout", "no"),
            "expires_at": expires,
            "created_at": now,
        },
    )
    _log(run, step, "asking", now, role=question.role, until=question.expires_at.isoformat())
    run.status = FlowRun.Status.ASKING
    run.resume_at = question.expires_at
    run.save()
    record_event(
        ctx, events.QUESTION_ASKED, {"id": str(question.id), "run_id": str(run.id), "flow_id": str(flow.id)}
    )
    record_event(
        ctx,
        events.RUN_PARKED,
        {"id": str(run.id), "flow_id": str(flow.id), "resume_at": question.expires_at.isoformat()},
    )


def _carry_on(ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, left: dict, now: dt.datetime) -> None:
    run.outputs = {**run.outputs, step["id"]: left}
    run.step_index += 1
    _go_on(ctx, run, flow, now)


def _may_say_yes(ctx: OperationContext, run: FlowRun) -> None:
    """A yes to the assistant's change that needs a person in front (cancelling a booking, ``ASK_FIRST``) is only of
    someone who may make it themselves: the yes lends nothing (the old engine's «no elevation»); the change still runs
    as the automation."""
    proposal = (run.outputs.get(TURN) or {}).get("proposal") or {}
    op = grantable_operations().get(str(proposal.get("operation") or ""))
    if op is not None and needs_a_person(op) and not ctx.has(op.permission):
        message = str(APPROVAL_BEYOND_YOU) % {"name": action_label(op, ctx.language)}
        raise PermissionDenied(message, code="flow.approval_beyond_you")


@operation(
    "flow.question.answer",
    kind="command",
    permission=ANSWER,
    input=AnswerIn,
    output=AnsweredOut,
    ai={
        "description": "Answer yes or no, with an optional note, to a question an automation asked and is waiting "
        "on (from `flow.question.list`): a yes carries it on, a no does what its step says. Only the role it was "
        "asked of, or whoever runs the business. It is the person's decision: confirm it with them first.",
        "risk": "high",
    },
)
def answer_question(ctx: OperationContext, data: AnswerIn) -> dict:
    now = timezone.now()
    found = Question.objects.filter(pk=data.id).values_list("flow_id", "run_id").first()
    with translation.override(ctx.language):
        if found is None:
            raise NotFound(str(QUESTION_NOT_FOUND), code="flow.question_not_found")
        # The order of every write: the automation, then its run, then the question.
        flow = Flow.objects.select_for_update().filter(pk=found[0]).first()
        run = FlowRun.objects.select_for_update().filter(pk=found[1]).first()
        question = Question.objects.select_for_update().filter(pk=data.id).first()
        if flow is None or run is None or question is None:
            raise NotFound(str(QUESTION_NOT_FOUND), code="flow.question_not_found")
        if not can_answer(ctx, question.role):
            raise PermissionDenied(str(QUESTION_NOT_YOURS), code="flow.question_not_yours")
        pending = question.status == Question.Status.PENDING
        if question.status == Question.Status.EXPIRED or (pending and question.expires_at <= now):
            raise Conflict(str(QUESTION_TOO_LATE), code="flow.question_expired")
        if not pending or run.status != FlowRun.Status.ASKING:
            closed = question.status == Question.Status.CANCELLED or run.status != FlowRun.Status.ASKING
            raise Conflict(str(QUESTION_CLOSED if closed else QUESTION_DECIDED), code="flow.question_decided")
        goes_on = data.approve or question.on_no == "continue"
        if goes_on and not flow.enabled:
            raise Conflict(str(DISABLED), code="flow.disabled")
        if data.approve:
            _may_say_yes(ctx, run)
    who = _who(ctx)
    question.status = Question.Status.APPROVED if data.approve else Question.Status.REJECTED
    question.decided_by, question.decided_at, question.note = who, now, data.note
    question.save(update_fields=["status", "decided_by", "decided_at", "note"])
    record_event(ctx, events.QUESTION_ANSWERED, {"id": str(question.id), "run_id": str(run.id)})
    step = run.definition["steps"][run.step_index]
    with translation.override(flow.language):
        _log(run, step, "answered", now, approved=data.approve, by=who, note=data.note)
        if goes_on and step["kind"] == "assistant":
            _make_proposal(ctx, run, flow, step, {"approved": True, "note": data.note, "answered_by": who}, now)
        elif goes_on:
            left = {"approved": data.approve, "expired": False, "note": data.note, "answered_by": who}
            _carry_on(ctx, run, flow, step, left, now)
        else:
            no = _own("flow.question_rejected", who=who, title=question.title)
            _finish(ctx, run, FlowRun.Status.CANCELLED, now, no)
    return {"id": question.id, "run_id": run.id, "status": run.status}


@operation(
    "flow.question.expire_due",
    kind="command",
    permission=SYSTEM,
    input=DueIn,
    output=DueOut,
    ai={
        "description": "System only, every minute: closes the questions nobody answered in time and does what "
        "each step says for silence (what a no does, stop, or carry on).",
        "risk": "normal",
    },
)
def expire_questions(ctx: OperationContext, data: DueIn) -> dict:
    now = timezone.now()
    # The run first, with SKIP LOCKED: one being answered (its automation and run locked) is left to it.
    due = (
        FlowRun.objects.filter(status=FlowRun.Status.ASKING, resume_at__lte=now)
        .select_related("flow")
        .select_for_update(skip_locked=True, of=("self",))
        .order_by("resume_at", "id")
    )
    closed = 0
    for run in due:
        flow = run.flow
        step = run.definition["steps"][run.step_index]
        # The one it waits on: an «Ask someone first» step's own, or the assistant's last change (``<step>:<n>``).
        question = Question.objects.select_for_update().filter(run=run, status=Question.Status.PENDING).first()
        if question is None:
            continue
        question.status, question.decided_at = Question.Status.EXPIRED, now
        question.save(update_fields=["status", "decided_at"])
        record_event(ctx, events.QUESTION_EXPIRED, {"id": str(question.id), "run_id": str(run.id)})
        closed += 1
        policy = question.on_no if question.on_timeout == "no" else question.on_timeout
        with translation.override(flow.language):
            _log(run, step, "expired", now)
            if policy != "continue":
                silence = _own("flow.question_expired", title=question.title)
                _finish(ctx, run, FlowRun.Status.CANCELLED, now, silence)
            elif flow.deleted_at is not None:
                _finish(ctx, run, FlowRun.Status.CANCELLED, now, _own("flow.deleted"))
            elif not flow.enabled:
                _finish(ctx, run, FlowRun.Status.CANCELLED, now, _own("flow.paused"))
            else:
                left = {"approved": False, "expired": True, "note": "", "answered_by": ""}
                _carry_on(ctx, run, flow, step, left, now)
    return {"count": closed}


def dispatch_call(scope: Scope, run_id: uuid.UUID) -> None:
    """Makes a run's call, with no transaction and no lock around it, and records how it ended in a
    transaction of its own: ``flow.run.claim_call`` → ``http.call`` → ``flow.run.record_call``. A call
    another process holds, or that ended meanwhile, is left alone."""
    system = system_context(scope)
    claimed = get("flow.run.claim_call")(system, RunRefIn(id=run_id))
    if not claimed.claimed:
        return
    outbound.release()  # the call waits on the other system with no connection held
    reply = http.call(claimed.method, claimed.url, claimed.headers, claimed.body, claimed.timeout)
    get("flow.run.record_call")(
        system,
        RecordCallIn(
            id=run_id,
            kind=reply.kind,
            status=reply.status,
            body=vault.mask_any(reply.body, claimed.masks),
            truncated=reply.truncated,
            detail=vault.mask(reply.detail, claimed.masks)[:2000],
        ),
    )


@operation(
    "flow.run.call",
    kind="command",
    permission=SYSTEM,
    input=RunRefIn,
    output=DueOut,
    ai={
        "description": "System only, in the worker: the reaction to `flow.run.parked` — a run that is calling "
        "makes its call after this COMMIT (`flow.run.claim_call` → the call → `flow.run.record_call`), never "
        "inside a person's request; a run that waits or asks has nothing to call.",
        "risk": "normal",
    },
)
def call_parked(ctx: OperationContext, data: RunRefIn) -> dict:
    parked = FlowRun.objects.filter(pk=data.id, status=FlowRun.Status.CALLING).values("definition", "step_index").first()
    if parked is None:
        return {"count": 0}
    outbound.after_commit(_dispatcher(parked), ctx.scope, data.id)
    return {"count": 1}


def _dispatcher(parked: dict):
    """What a run that waits on something outside the Hub makes, outside any transaction: its call, or its turn."""
    step = parked["definition"]["steps"][parked["step_index"]]
    return dispatch_assistant if step["kind"] == "assistant" else dispatch_call


@operation(
    "flow.run.claim_call",
    kind="command",
    permission=SYSTEM,
    input=RunRefIn,
    output=ClaimCallOut,
    ai={
        "description": "System only: takes a run's call to another system to make it (nobody else holds it), "
        "with its data and secrets filled in, for CALL_LEASE_MINUTES.",
        "risk": "normal",
    },
)
def claim_call(ctx: OperationContext, data: RunRefIn) -> dict:
    now = timezone.now()
    run = (
        FlowRun.objects.select_for_update(skip_locked=True, of=("self",))
        .select_related("flow")
        .filter(pk=data.id, status=FlowRun.Status.CALLING, resume_at__lte=now)
        .first()
    )
    if run is None:
        return {"claimed": False}
    flow = run.flow
    step = run.definition["steps"][run.step_index]
    with translation.override(flow.language):
        if flow.deleted_at is not None:
            _finish(ctx, run, FlowRun.Status.CANCELLED, now, _own("flow.deleted"))
            return {"claimed": False}
        refused = _call_allowed(run, flow, step)
        if refused is None:
            secrets, refused = _open_secrets(document.secret_names(step))
        if refused is not None:
            _call_failed(ctx, run, flow, step, refused, now)
            return {"claimed": False}
    key = str(uuid.uuid5(IDEMPOTENCY_NAMESPACE, f"{run.id}:{step['id']}"))
    url, headers, body = document.render_call(step, {"input": run.input, "steps": run.outputs}, secrets, key)
    if not any(name.lower() == "idempotency-key" for name in headers):
        headers["Idempotency-Key"] = key
    run.resume_at = now + dt.timedelta(minutes=CALL_LEASE_MINUTES)
    run.save(update_fields=["resume_at"])
    return {
        "claimed": True,
        "method": step.get("method", "POST"),
        "url": url,
        "headers": headers,
        "body": body,
        "timeout": int(step.get("timeout", 10)),
        "masks": list(secrets.values()),
    }


def _open_secrets(names: list[str]) -> tuple[dict[str, str], StepFailed | None]:
    """The values of the secrets a call reads, or why it cannot make it."""
    if not names:
        return {}, None
    if not vault.available():
        return {}, _own("flow.secrets_key_missing")
    kept = dict(Secret.objects.filter(name__in=names).values_list("name", "ciphertext"))
    opened: dict[str, str] = {}
    for name in names:
        if name not in kept:
            return {}, _own("flow.secret_not_found", name=name)
        try:
            opened[name] = vault.open_value(kept[name])
        except vault.Unreadable:
            return {}, _own("flow.secret_unreadable", name=name)
    return opened, None


@operation(
    "flow.run.record_call",
    kind="command",
    permission=SYSTEM,
    input=RecordCallIn,
    output=DueOut,
    ai={
        "description": "System only: records how a run's call to another system ended and goes on with the run "
        "(or stops it with the reason); an answer for a run that is no longer calling changes nothing.",
        "risk": "normal",
    },
)
def record_call(ctx: OperationContext, data: RecordCallIn) -> dict:
    now = timezone.now()
    run = FlowRun.objects.select_for_update(of=("self",)).select_related("flow").filter(pk=data.id).first()
    if run is None or run.status != FlowRun.Status.CALLING:
        return {"count": 0}
    flow = run.flow
    step = run.definition["steps"][run.step_index]
    host = document.host_of(step["url"])
    with translation.override(flow.language):
        if data.kind == http.OK:
            run.outputs = {
                **run.outputs,
                step["id"]: {"ok": True, "status": data.status, "body": data.body, "truncated": data.truncated},
            }
            _log(run, step, "called", now, host=host, status=data.status)
            run.step_index += 1
            _go_on(ctx, run, flow, now)
            return {"count": 1}
        failure = _own(
            _CALL_FAILURES[data.kind],
            technical=data.detail,
            host=host,
            status=data.status,
            seconds=step.get("timeout", 10),
        )
        _call_failed(ctx, run, flow, step, failure, now, {"status": data.status})
    return {"count": 1}


def _parent_chain(actor: str) -> list[str]:
    """The automations behind the run that caused an event (``flow_run:<id>``); empty for anything else."""
    if not actor.startswith(RUN_ACTOR):
        return []
    try:
        parent_id = uuid.UUID(actor[len(RUN_ACTOR) :])
    except ValueError:
        return []
    parent = FlowRun.objects.filter(pk=parent_id).values("flow_id", "chain").first()
    return [*parent["chain"], str(parent["flow_id"])] if parent else []


@operation(
    "flow.run.react",
    kind="command",
    permission=SYSTEM,
    input=ReactIn,
    output=ReactOut,
    ai={
        "description": "System only: the platform's reaction to every event of the outbox: starts the automations "
        "that wait for it (once per automation and event) and runs their steps.",
        "risk": "normal",
    },
)
def react(ctx: OperationContext, data: ReactIn) -> dict:
    now = timezone.now()
    started = skipped = 0
    key = str(data.event_id)
    chain = _parent_chain(data.actor)
    waiting_ids = list(
        live_flows()
        .filter(enabled=True, trigger_kind=Flow.Trigger.EVENT, trigger_event=data.event)
        .order_by("created_at", "id")
        .values_list("pk", flat=True)
    )
    for flow_id in waiting_ids:
        flow = (
            Flow.objects.select_for_update()
            .filter(pk=flow_id, deleted_at__isnull=True, enabled=True)
            .first()
        )
        if flow is None or FlowRun.objects.filter(flow=flow, trigger_key=key).exists():
            skipped += 1
            continue
        if not document.readable(flow.trigger_filter):
            # Never «does not hold» in silence (hub#1766): the owner reads why in its history.
            run = _start(
                ctx,
                flow,
                kind=Flow.Trigger.EVENT,
                key=key,
                input=data.payload,
                now=now,
                event_name=data.event,
                chain=chain,
            )
            started += 1
            with translation.override(flow.language):
                _finish(ctx, run, FlowRun.Status.FAILED, now, _own("flow.filter_unreadable"))
            continue
        if not document.holds(
            flow.trigger_filter, {"input": data.payload, "steps": {}}
        ):
            skipped += 1
            continue
        run = _start(
            ctx,
            flow,
            kind=Flow.Trigger.EVENT,
            key=key,
            input=data.payload,
            now=now,
            event_name=data.event,
            chain=chain,
        )
        started += 1
        with translation.override(flow.language):
            if str(flow.id) in chain:
                _finish(ctx, run, FlowRun.Status.FAILED, now, _own("flow.loop_stopped", "flow.loop"))
                continue
            if len(chain) >= document.MAX_CHAIN:
                too_long = _own(
                    "flow.loop_stopped", "flow.chain_too_long", count=len(chain) + 1, max=document.MAX_CHAIN
                )
                _finish(ctx, run, FlowRun.Status.FAILED, now, too_long)
                continue
        _advance(ctx, run, flow, now)
    return {"started": started, "skipped": skipped}


@operation(
    "flow.schedule.fire_due",
    kind="command",
    permission=SYSTEM,
    input=DueIn,
    output=DueOut,
    ai={
        "description": "System only, a scheduled task, every minute: starts once each automation whose schedule or "
        "date has come, and moves its schedule on from now.",
        "risk": "normal",
    },
)
def fire_due(ctx: OperationContext, data: DueIn) -> dict:
    now = timezone.now()
    due = (
        live_flows()
        .filter(
            enabled=True,
            trigger_kind__in=[Flow.Trigger.SCHEDULE, Flow.Trigger.AT],
            next_fire_at__lte=now,
        )
        .select_for_update(skip_locked=True)
        .order_by("next_fire_at", "id")
    )
    fired = 0
    for flow in due:
        key = f"{flow.trigger_kind}:{flow.next_fire_at.astimezone(_business_zone()).isoformat()}"
        if not FlowRun.objects.filter(flow=flow, trigger_key=key).exists():
            run = _start(ctx, flow, kind=flow.trigger_kind, key=key, input={}, now=now)
            _advance(ctx, run, flow, now)
            fired += 1
        flow.next_fire_at = (
            document.next_fire(flow.schedule, now, _business_zone())
            if flow.trigger_kind == Flow.Trigger.SCHEDULE
            else None
        )
        flow.save(update_fields=["next_fire_at"])
    return {"count": fired}


@operation(
    "flow.run.resume_due",
    kind="command",
    permission=SYSTEM,
    input=DueIn,
    output=DueOut,
    ai={
        "description": "System only, a scheduled task, every minute: the runs whose wait is over go on with their "
        "next step; those of a paused or deleted automation are cancelled.",
        "risk": "normal",
    },
)
def resume_due(ctx: OperationContext, data: DueIn) -> dict:
    now = timezone.now()
    due = (
        FlowRun.objects.filter(status=FlowRun.Status.WAITING, resume_at__lte=now)
        .select_related("flow")
        .select_for_update(skip_locked=True, of=("self",))
        .order_by("resume_at", "id")
    )
    resumed = 0
    for run in due:
        flow = run.flow
        with translation.override(flow.language):
            if flow.deleted_at is not None:
                _finish(ctx, run, FlowRun.Status.CANCELLED, now, _own("flow.deleted"))
                continue
            if not flow.enabled:
                _finish(ctx, run, FlowRun.Status.CANCELLED, now, _own("flow.paused"))
                continue
        waited = [dict(entry) for entry in run.log]
        if waited and waited[-1].get("outcome") == "waiting":
            waited[-1]["outcome"] = "waited"
        run.log = waited
        run.status = FlowRun.Status.RUNNING
        run.resume_at = None
        record_event(
            ctx, events.RUN_RESUMED, {"id": str(run.id), "flow_id": str(flow.id)}
        )
        _advance(ctx, run, flow, now)
        resumed += 1
    # A call (or a turn of the assistant) whose lease ran out never answered (the process died): it goes again.
    stuck = (
        FlowRun.objects.filter(status=FlowRun.Status.CALLING, resume_at__lte=now)
        .select_for_update(skip_locked=True)
        .order_by("resume_at", "id")
        .values("pk", "definition", "step_index")
    )
    for parked in stuck:
        outbound.after_commit(_dispatcher(parked), ctx.scope, parked["pk"])
        resumed += 1
    return {"count": resumed}


@operation(
    "flow.flow.run",
    kind="command",
    permission=MANAGE,
    input=RunIn,
    output=RunOut,
    ai={
        "description": "Run an automation now, for real, by its id or its name («run the weekly review now»), "
        "with `input` as what its steps read. Only when it is on; to see what it would do without effects, "
        "use `flow.flow.test`. Confirm it first.",
        "risk": "high",
    },
)
def run_now(ctx: OperationContext, data: RunIn) -> dict:
    flow = resolve_flow(data.id, data.flow, lock=True)
    if not flow.enabled:
        with translation.override(ctx.language):
            raise Conflict(str(DISABLED), code="flow.disabled")
    now = timezone.now()
    started = _start(
        ctx,
        flow,
        kind=Flow.Trigger.MANUAL,
        key=f"manual:{uuid.uuid7()}",
        input=data.input,
        now=now,
    )
    _advance(ctx, started, flow, now)
    with translation.override(ctx.language):
        return run_row(started)


@operation(
    "flow.run.retry",
    kind="command",
    permission=MANAGE,
    input=RunRefIn,
    output=RunOut,
    ai={
        "description": "Resume a run that stopped by an error at the step that failed, once its cause is fixed "
        "(a permission granted, an app turned on, the other system back): the steps before it are not "
        "repeated and it goes on with the steps it started with. Only within 7 days, with the automation on. "
        "It does things for real: confirm it first.",
        "risk": "high",
    },
)
def retry_run(ctx: OperationContext, data: RunRefIn) -> dict:
    run = FlowRun.objects.filter(pk=data.id).values("flow_id").first()
    if run is None:
        raise NotFound(str(RUN_NOT_FOUND))
    # The automation first, as every write does: a save, a delete or a run wait for this one.
    flow = resolve_flow(run["flow_id"], None, lock=True)
    failed = FlowRun.objects.select_for_update().get(pk=data.id)
    now = timezone.now()
    with translation.override(ctx.language):
        problem = resume_problem(failed, now)
        if problem is not None:
            raise Conflict(problem[1], code=problem[0])
        if not flow.enabled:
            raise Conflict(str(DISABLED), code="flow.disabled")
    step = failed.definition["steps"][failed.step_index]
    _log(failed, step, "resumed", now, by=_actor(ctx))
    failed.status = FlowRun.Status.RUNNING
    failed.finished_at = None
    failed.error_code = failed.error_message = ""
    failed.error_reason = {}
    record_event(ctx, events.RUN_RESUMED, {"id": str(failed.id), "flow_id": str(flow.id)})
    _advance(ctx, failed, flow, now)
    with translation.override(ctx.language):
        return run_row(failed)


@operation(
    "flow.run.prune",
    kind="command",
    permission=SYSTEM,
    input=DueIn,
    output=DueOut,
    ai={
        "description": "System only, a scheduled task, every hour: deletes the finished runs older than 90 days "
        "(the history keeps 90 days); a run that is waiting or running is never touched.",
        "risk": "normal",
    },
)
def prune_runs(ctx: OperationContext, data: DueIn) -> dict:
    cutoff = timezone.now() - dt.timedelta(days=HISTORY_DAYS)
    doomed = list(
        FlowRun.objects.filter(status__in=FINISHED)
        .annotate(ended=Coalesce("finished_at", "started_at"))
        .filter(ended__lt=cutoff)
        .order_by("ended", "id")
        .values_list("pk", flat=True)[:PRUNE_BATCH]
    )
    # A failure older than RESUME_DAYS can no longer be resumed: what its steps read goes (FLOW-F24).
    FlowRun.objects.filter(
        status=FlowRun.Status.FAILED,
        finished_at__lt=timezone.now() - dt.timedelta(days=RESUME_DAYS),
    ).exclude(outputs={}).update(outputs={})
    if doomed:
        FlowRun.objects.filter(pk__in=doomed).delete()
        # Counted: a silent prune cannot be told from lost data the day somebody looks for an old run.
        logger.info(
            "flow: deleted %d finished runs older than %d days", len(doomed), HISTORY_DAYS
        )
    return {"count": len(doomed)}
