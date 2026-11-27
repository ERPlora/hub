"""System: the failed events (``base.failed_event.*``).

Resend one, resend all and discard one, for who runs the business. A failed event is a delivery the relay gave up
on (``dead``): resending puts it back in the queue for the app that had failed only; discarding closes it for good
and keeps the row. One hub never touches another's.
"""

from uuid import UUID

from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import AI, operation
from live.outbox import record_event

from base import events, system
from base.apps_on import active_apps
from base.models.relay import EventDelivery
from base.permissions import ADMINISTER_HUB
from base.schemas.failed_events import (
    FailedEventCountOut,
    FailedEventDiscardIn,
    FailedEventIn,
    FailedEventOutId,
    FailedEventRetryAllIn,
)


@operation(
    "base.failed_event.retry",
    kind="command",
    permission=ADMINISTER_HUB,
    input=FailedEventIn,
    output=FailedEventOutId,
    ai=AI(
        description=(
            "Resends one failed event of this hub (by its id, from the list of failed events) once its cause is fixed: "
            "it goes back to the queue with its attempts at zero, for the app that could not take it only. Refused "
            "when that app is no longer on in this business."
        ),
        asks={
            "en": ("retry that failed event", "send the stuck invoicing event again"),
            "es": ("reintenta ese evento caído", "vuelve a mandar el evento de facturación que se quedó atascado"),
        },
    ),
)
def failed_event_retry(ctx: OperationContext, data: FailedEventIn) -> dict:
    """``pending`` again, due now, attempts at zero; the relay takes it on its next tick."""
    delivery = _failed_event(ctx, data.id)
    if delivery.app_label not in active_apps(ctx.scope):
        raise Conflict(
            gettext("%(app)s is not on in this business: turn it on, then resend the event.")
            % {"app": system.app_name(delivery.app_label)},
            code="base.failed_event_app_off",
        )
    _requeue([delivery.pk])
    record_event(ctx, events.FAILED_EVENT_RETRIED, {"id": str(delivery.pk), "count": 1})
    return {"id": delivery.pk}


@operation(
    "base.failed_event.retry_all",
    kind="command",
    permission=ADMINISTER_HUB,
    input=FailedEventRetryAllIn,
    output=FailedEventCountOut,
    ai=AI(
        description=(
            "Resends every failed event of this hub that can be resent (also those beyond the first page of the list), "
            "once the cause of a passing failure is fixed. Those for an app that is no longer on stay. Says how many "
            "went back to the queue."
        ),
        asks={
            "en": ("retry all the failed events", "the printer is back, resend everything that failed"),
            "es": ("reintenta todos los eventos caídos", "vuelve a mandar todos los eventos que fallaron"),
        },
    ),
)
def failed_event_retry_all(ctx: OperationContext, data: FailedEventRetryAllIn) -> dict:
    """Every ``dead`` delivery of the hub whose app is on; another worker's rows wait (``SKIP LOCKED``)."""
    ids = list(
        EventDelivery.objects.select_for_update(skip_locked=True, of=("self",))
        .filter(
            status=EventDelivery.Status.DEAD,
            event__scope_kind=ctx.scope.kind,
            app_label__in=active_apps(ctx.scope),
        )
        .values_list("pk", flat=True)
    )
    if ids:
        _requeue(ids)
        record_event(ctx, events.FAILED_EVENT_RETRIED, {"count": len(ids)})
    return {"count": len(ids)}


@operation(
    "base.failed_event.discard",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=FailedEventDiscardIn,
    output=FailedEventOutId,
    ai=AI(
        description=(
            "Discards one failed event of this hub for good (by its id), with an optional reason: it is never "
            "delivered again and is kept with who discarded it, when and why. Only when it must not be delivered (a "
            "duplicate, already done by hand): discarding a sale's event for Invoicing leaves that sale without its "
            "invoice."
        ),
        risk="high",
        asks={
            "en": ("discard that failed event, I already did it by hand", "drop the duplicate event that failed"),
            "es": ("descarta ese evento caído, ya lo hice a mano", "olvídate del evento duplicado que falló"),
        },
    ),
)
def failed_event_discard(ctx: OperationContext, data: FailedEventDiscardIn) -> dict:
    """Closed as ``discarded`` with who, when and why; the row and its last error stay for the audit."""
    delivery = _failed_event(ctx, data.id)
    delivery.status = EventDelivery.Status.DISCARDED
    delivery.closed_at = timezone.now()
    delivery.closed_by = str(ctx.actor)[: EventDelivery._meta.get_field("closed_by").max_length]
    delivery.close_reason = data.reason.strip()
    delivery.save(update_fields=["status", "closed_at", "closed_by", "close_reason"])
    record_event(ctx, events.FAILED_EVENT_DISCARDED, {"id": str(delivery.pk)})
    return {"id": delivery.pk}


def resend_done(ctx: OperationContext, *, app_label: str, event: str, match: dict) -> int:
    """Resends the failed events for ``app_label`` of the ``event`` whose payload holds ``match``, once that app has
    done what they asked by other means (Invoicing issued a sale's document by hand): they leave Failed events and the
    bell, and the app's reaction, idempotent, finds the work done. Called inside that app's command; another app's,
    a discarded one and one another worker holds stay as they are. How many went back to the queue."""
    ids = list(
        EventDelivery.objects.select_for_update(skip_locked=True, of=("self",))
        .filter(
            status=EventDelivery.Status.DEAD,
            app_label=app_label,
            event__name=event,
            event__scope_kind=ctx.scope.kind,
            event__payload__contains=match,
        )
        .values_list("pk", flat=True)
    )
    if ids:
        _requeue(ids)
        record_event(ctx, events.FAILED_EVENT_RETRIED, {"count": len(ids)})
    return len(ids)


def _failed_event(ctx: OperationContext, delivery_id: UUID) -> EventDelivery:
    """The failed event ``delivery_id`` of the hub of ``ctx``, locked; not found if it is another hub's, or no longer
    failed (resent, discarded, or delivered in the meantime)."""
    delivery = (
        EventDelivery.objects.select_for_update(of=("self",))
        .filter(pk=delivery_id, status=EventDelivery.Status.DEAD, event__scope_kind=ctx.scope.kind)
        .first()
    )
    if delivery is None:
        raise NotFound(gettext("That failed event is no longer in the queue: refresh the list."))
    return delivery


def _requeue(ids: list[UUID]) -> None:
    """Back to the queue, due now, with their attempts at zero and no error."""
    EventDelivery.objects.filter(pk__in=ids).update(
        status=EventDelivery.Status.PENDING, attempts=0, next_attempt_at=timezone.now(), last_error=""
    )
