"""The automations (``flow.flow.list``, ``detail`` and ``status``): one by its id or its name, and each as
its screen shows it, with its last run."""

from typing import Any

from django.db.models import OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.flow import document, recipes
from base.ordering import list_order_for
from apps.flow.models import Flow, FlowRun
from apps.flow.schemas import FlowListIn, FlowOut, FlowRefIn, Page, StatusIn, StatusOut

from .reads import VIEW

FLOW_NOT_FOUND = _("That automation does not exist in this business.")
AMBIGUOUS_FLOW = _("Several automations fit «%(text)s»: %(names)s. Say which one.")

#: How many names an ambiguous reference lists.
AMBIGUOUS_SHOWN = 5


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
            "filter": recipes.fixed_filter(flow),
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
        "steps": recipes.fixed_data(flow, flow.steps),
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
        "fixed_by_app": recipes.fixed_by_app(flow),
    }


_FLOW_SORTS = {"name": (Lower("name"),)}


@operation(
    "flow.flow.list",
    kind="query",
    permission=VIEW,
    input=FlowListIn,
    output=Page[FlowOut],
    ai={
        "asks": {
            "en": (
                "what automations do I have?",
                "which automations are switched on?",
                "show me my automations and how their last run went",
            ),
            "es": (
                "¿qué automatizaciones tengo?",
                "¿cuáles de mis automatizaciones están encendidas?",
                "enséñame las automatizaciones y cómo acabó la última vez",
            ),
        },
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
    page = with_last_run(flows.order_by(*list_order_for(data.sort, columns=_FLOW_SORTS)))[
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
        "asks": {
            "en": (
                "what does the welcome automation do, and when does it start?",
                "what permissions is the birthday automation missing?",
            ),
            "es": (
                "¿qué hace la automatización de bienvenida, paso a paso?",
                "dime los pasos y los permisos de la automatización de cumpleaños",
            ),
        },
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
        "asks": {
            "en": (
                "is there already an automation that listens to completed sales?",
                "do I already have an automation for new appointments?",
            ),
            "es": (
                "¿ya hay alguna automatización que escuche las ventas cobradas?",
                "¿ya tengo montada alguna automatización para las citas nuevas?",
            ),
        },
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
