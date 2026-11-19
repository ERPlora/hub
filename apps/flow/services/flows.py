"""The automations (``flow.flow.*``): created, changed, turned on or paused, copied, deleted and granted what
they may do."""

from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload, PermissionDenied
from live.operations import operation
from live.outbox import record_event

from apps.flow import document, events, recipes
from apps.flow.models import Draft, Flow, FlowRun, Question
from apps.flow.queries.catalog import asked_first, grantable_operations
from apps.flow.queries.flows import flow_row, live_flows, resolve_flow
from apps.flow.queries.problems import HIGH_RISK_CODE, operation_problem
from apps.flow.queries.reads import MANAGE
from apps.flow.schemas import CreateIn, DeletedOut, EnabledIn, FlowOut, FlowRefIn, GrantIn, UpdateIn

from .drafts import _decide_draft
from .engine import _finish, _own
from .flow_document import _apply_trigger, _check, _next_fire, _record_switch, refresh_search_text, _taken_off
from .writes import GRANT_BEYOND_CALLER, _actor

UNTITLED = _("Untitled automation")
COPY_OF = _("Copy of %(name)s")
NUMBERED = "%(name)s (%(n)s)"


@operation(
    "flow.flow.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE,
    input=CreateIn,
    output=FlowOut,
    ai={
        "asks": {
            "en": (
                "create the automation from the assistant's draft",
                "set up a new automation that runs every Monday at 9",
            ),
            "es": (
                "crea la automatización a partir del borrador que me propusiste",
                "monta una automatización nueva que arranque cada lunes a las 9",
            ),
        },
        "description": "Create an automation from scratch, from a gallery card or from the assistant's draft "
        "(`draft_id`, which is marked as used in the same step). It is born paused and with no permission "
        "(`flow.flow.set_enabled` turns it on); prefer `flow.draft.propose` when somebody asks you for one.",
        "risk": "normal",
    },
)
def create_flow(ctx: OperationContext, data: CreateIn) -> dict:
    now = timezone.now()
    _check(ctx, data.trigger, data.steps, now)
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE,
    input=UpdateIn,
    output=FlowOut,
    ai={
        "asks": {
            "en": (
                "change the name of the welcome automation to «New customers»",
                "change the steps of the birthday automation",
            ),
            "es": (
                "cambia el nombre de la automatización de bienvenida a «Clientes nuevos»",
                "modifica los pasos de la automatización de cumpleaños",
            ),
        },
        "description": "Change an automation, by its id or its name: its name, what starts it or its steps (to turn "
        "it on or pause it, `flow.flow.set_enabled`). Only what is sent changes; its permissions stay. Changing the trigger or the steps "
        "raises its version, and what is already running goes on with the version it started with. What its app fixes "
        "on one built from a recipe (`fixed_by_app` of `flow.flow.detail`) cannot be left out: give it another value.",
        "risk": "normal",
    },
)
def update_flow(ctx: OperationContext, data: UpdateIn) -> dict:
    now = timezone.now()
    flow = resolve_flow(data.id, data.flow, lock=True)
    _taken_off(ctx, flow, data.trigger, data.steps)
    _check(ctx, data.trigger, data.steps, now, saved_at=flow.run_at)
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE,
    input=EnabledIn,
    output=FlowOut,
    ai={
        "asks": {
            "en": (
                "turn on the welcome automation",
                "pause the birthday automation",
            ),
            "es": (
                "enciende la automatización que salta al cobrar una venta",
                "pausa la automatización de cumpleaños",
                "vuelve a encender la automatización de reseñas",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE,
    input=FlowRefIn,
    output=FlowOut,
    ai={
        "asks": {
            "en": (
                "make a copy of the welcome automation",
                "duplicate the birthday automation",
            ),
            "es": (
                "haz una copia de la automatización de bienvenida",
                "duplica la automatización de cumpleaños",
            ),
        },
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
        trigger_filter=recipes.fixed_filter(original),
        schedule=original.schedule,
        run_at=original.run_at,
        steps=recipes.fixed_data(original, original.steps),
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE,
    input=FlowRefIn,
    output=DeletedOut,
    ai={
        "asks": {
            "en": (
                "delete the birthday automation",
                "get rid of the welcome automation but keep its history",
            ),
            "es": (
                "borra la automatización de cumpleaños",
                "quita la automatización de bienvenida, ya no la uso",
            ),
        },
        "description": "Delete an automation, by its id or its name: it stops at once, what was waiting is "
        "cancelled and its history stays. Cannot be undone.",
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE,
    input=GrantIn,
    output=FlowOut,
    ai={
        "asks": {
            "en": (
                "grant the welcome automation the permission to create tasks",
                "give the birthday automation permission to send WhatsApp messages",
            ),
            "es": (
                "dale permiso a la automatización de bienvenida para crear tareas",
                "deja que la automatización de cumpleaños mande WhatsApp a los clientes",
                "autoriza a la automatización de las ventas cobradas a leer los clientes",
            ),
        },
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
        problem = operation_problem(ctx.scope, name, asking=name in asking)
        if problem is not None:
            problem_code, problems[f"operations.{index}"] = problem
            if problem_code == HIGH_RISK_CODE:
                code = HIGH_RISK_CODE
    if problems:
        raise InvalidPayload(next(iter(problems.values())), code=code, fields=problems)
    # Nobody grants more than they may do themselves (an API key with flow:write included); a call's
    # origin is the automation's own permission, which whoever manages it already holds.
    offered = grantable_operations(ctx.scope)
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
