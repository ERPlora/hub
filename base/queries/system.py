"""System's reads: the hub's status, its log of events between apps and the failed events."""

from typing import Any

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext, ngettext
from live.context import OperationContext
from live.errors import NotFound
from live.models import OutboxEvent
from live.operations import AI, operation

from base import system
from base.apps_on import active_apps
from base.models.relay import EventDelivery
from base.permissions import ADMINISTER_HUB
from base.schemas.failed_events import FailedEventIn, FailedEventListIn, FailedEventListOut, FailedEventOut
from base.schemas.system import EventListIn, EventListOut, SystemStatusIn, SystemStatusOut


# ── System ─────────────────────────────────────────────────────────────────────────────────────────────────────
# The hub's status, its log and the failed events, for who runs the business only (an error may carry a customer's
# tax id and name). One hub never sees another's.

#: How many of the last events between apps System › Logs shows: the old hub's.
EVENT_LOG_SIZE = 50
#: How much of a failed event's last error the list carries: its start tells it, and the page stays light.
FAILED_EVENT_ERROR_LENGTH = 300


@operation(
    "base.system.status",
    kind="query",
    permission=ADMINISTER_HUB,
    input=SystemStatusIn,
    output=SystemStatusOut,
    ai=AI(
        description=(
            "Reads the status of this hub's system: the version of ERPlora it runs and when that version was published "
            "(the hub updates itself, nobody installs anything)."
        ),
        asks={
            "en": ("which ERPlora version are we on?", "is the system up to date?"),
            "es": ("¿qué versión de ERPlora tenemos?", "¿está actualizado el sistema?"),
        },
    ),
)
def system_status(ctx: OperationContext, data: SystemStatusIn) -> dict:
    """The release (``base.system``: the commit, short) and its date, never made up."""
    return {"version": system.version(settings.APP_VERSION), "released_at": system.released_at(settings.APP_RELEASED_AT)}


@operation(
    "base.event.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=EventListIn,
    output=EventListOut,
    ai=AI(
        description=(
            "Reads the log of the last 50 events between this hub's apps (a sale charged, a round fired…), newest "
            "first: when each happened, which app recorded it, its level (info, warning, error) and what happened to "
            "it (delivered to each app, retrying, given up and waiting in «Failed events», discarded). Never the "
            "content of an event."
        ),
        asks={
            "en": ("what's been happening between the apps?", "show me the latest event log"),
            "es": ("enséñame el registro de eventos", "¿qué ha pasado entre las apps últimamente?"),
        },
    ),
)
def event_list(ctx: OperationContext, data: EventListIn) -> dict:
    """The old hub's System › Logs: the hub's last outbox events with how their deliveries went (``base.relay``)."""
    with translation.override(ctx.language):
        recent = list(
            OutboxEvent.objects.filter(scope_kind=ctx.scope.kind).order_by("-created_at", "-id")[:EVENT_LOG_SIZE]
        )
        deliveries: dict[Any, list[EventDelivery]] = {}
        for delivery in EventDelivery.objects.filter(event_id__in=[event.pk for event in recent]).order_by(
            "app_label"
        ):
            deliveries.setdefault(delivery.event_id, []).append(delivery)
        return {"entries": [_log_entry(event, deliveries.get(event.pk, [])) for event in recent]}


def _log_entry(event: OutboxEvent, deliveries: list[EventDelivery]) -> dict:
    app = event.name.split(".", 1)[0]
    if not deliveries:
        detail = gettext("No app listens to it.") if event.delivered_at else gettext("Waiting to be handed to the apps.")
        return _entry(event, app, "info", detail)
    statuses = {delivery.status for delivery in deliveries}
    if EventDelivery.Status.DEAD in statuses:
        level = "error"
    elif any(delivery.status == EventDelivery.Status.PENDING and delivery.attempts for delivery in deliveries):
        level = "warning"
    else:
        level = "info"
    return _entry(event, app, level, " ".join(_delivery_detail(delivery) for delivery in deliveries))


def _entry(event: OutboxEvent, app: str, level: str, detail: str) -> dict:
    return {
        "id": event.pk,
        "at": event.created_at,
        "level": level,
        "name": event.name,
        "app": app,
        "app_name": system.app_name(app),
        "detail": detail,
    }


def _delivery_detail(delivery: EventDelivery) -> str:
    """What happened to one app's delivery; the error itself stays in Failed events."""
    app = system.app_name(delivery.app_label)
    if delivery.status == EventDelivery.Status.DELIVERED:
        return gettext("Delivered to %(app)s.") % {"app": app}
    if delivery.status == EventDelivery.Status.DEAD:
        return gettext("%(app)s could not take it: it is in Failed events.") % {"app": app}
    if delivery.status == EventDelivery.Status.DISCARDED:
        return gettext("Discarded for %(app)s.") % {"app": app}
    if delivery.attempts:
        return ngettext(
            "%(app)s failed %(count)d time; it is retried by itself.",
            "%(app)s failed %(count)d times; it is retried by itself.",
            delivery.attempts,
        ) % {"app": app, "count": delivery.attempts}
    return gettext("Waiting for %(app)s.") % {"app": app}


@operation(
    "base.failed_event.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=FailedEventListIn,
    output=FailedEventListOut,
    ai=AI(
        description=(
            "Lists the failed events of this hub, newest first: messages between apps (a sale to Invoicing, a round to "
            "Printing…) that could not be delivered after every retry. Each one says the event, the app that sent it "
            "and the one that could not take it, the attempts, when it happened, the start of the last error and "
            "whether it can be resent (not when the app it was for is no longer on). Pages of up to 100."
        ),
        asks={
            "en": (
                "is anything stuck between the apps?",
                "list the failed events",
                "what never got delivered to printing?",
            ),
            "es": ("¿hay algo atascado entre las apps?", "lista los eventos caídos"),
        },
    ),
)
def failed_event_list(ctx: OperationContext, data: FailedEventListIn) -> dict:
    """The deliveries the relay gave up on (``dead``) of the hub; a resent one is ``pending`` again and a discarded one
    is closed: neither is here."""
    with translation.override(ctx.language):
        failed = EventDelivery.objects.filter(status=EventDelivery.Status.DEAD, event__scope_kind=ctx.scope.kind)
        page = failed.select_related("event").order_by("-event__created_at", "-id")[
            data.offset : data.offset + data.limit
        ]
        on = active_apps(ctx.scope)
        return {"items": [_failed_event(delivery, on) for delivery in page], "total": failed.count()}


@operation(
    "base.failed_event.detail",
    kind="query",
    permission=ADMINISTER_HUB,
    input=FailedEventIn,
    output=FailedEventOut,
    ai=AI(
        description=(
            "Reads one failed event of this hub by its id, as the list of failed events shows it: the event, the app "
            "that sent it and the one that could not take it, the attempts and whether it can be resent."
        ),
        asks={
            "en": ("why did that failed event fail?", "show me the failed invoicing event"),
            "es": ("¿por qué ha fallado ese evento?", "dame el detalle del evento caído de facturación"),
        },
    ),
)
def failed_event_detail(ctx: OperationContext, data: FailedEventIn) -> dict:
    """One failed event of System (a delivery the relay gave up on), of the hub of ``ctx`` only."""
    delivery = (
        EventDelivery.objects.select_related("event")
        .filter(pk=data.id, status=EventDelivery.Status.DEAD, event__scope_kind=ctx.scope.kind)
        .first()
    )
    if delivery is None:
        raise NotFound(gettext("That failed event is no longer in the queue: refresh the list."))
    with translation.override(ctx.language):
        return _failed_event(delivery, active_apps(ctx.scope))


def _failed_event(delivery: EventDelivery, on: frozenset[str]) -> dict:
    source = delivery.event.name.split(".", 1)[0]
    return {
        "id": delivery.pk,
        "event_id": delivery.event_id,
        "name": delivery.event.name,
        "source_app": source,
        "source_app_name": system.app_name(source),
        "target_app": delivery.app_label,
        "target_app_name": system.app_name(delivery.app_label),
        "attempts": delivery.attempts,
        "occurred_at": delivery.event.created_at,
        "last_error": delivery.last_error[:FAILED_EVENT_ERROR_LENGTH],
        "retryable": delivery.app_label in on,
    }
