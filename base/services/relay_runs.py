"""What the passes of the apps' scheduled tasks (``base.scheduler``) and of the outbox relay (``base.relay``) write."""

import datetime as dt
import logging
from collections.abc import Callable, Collection, Iterable
from contextvars import ContextVar
from functools import partial

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from live.context import Scope, system_context
from live.errors import OperationError
from live.models import OutboxEvent
from live.operations import atomic
from live.outbox import notify

from base import events
from base.models.relay import EventDelivery
from base.models.scheduler import TaskSchedule
from base.tenancy.context import HUB_SCOPE_KIND, current_hub

logger = logging.getLogger(__name__)


# ── The scheduled tasks' clock (base.scheduler) ────────────────────────────────────────────────


def sync_task_schedules(declared: Iterable[tuple[str, str, str, str, dt.datetime]]) -> None:
    """Write the tasks the apps declare, ``(app_label, name, operation, cron, first_run)``; forget the rest.

    Not an ``@operation``: the worker calls it for no hub's user when it starts. A task it already knew keeps
    its ``next_run`` and ``last_run`` (a boot never resets the clock) and takes the declared operation and
    cron; a new one is due at ``first_run``.
    """
    with atomic():
        keep = set()
        for app_label, name, operation, cron, first_run in declared:
            TaskSchedule.objects.update_or_create(
                app_label=app_label,
                name=name,
                defaults={"operation": operation, "cron": cron},
                create_defaults={"operation": operation, "cron": cron, "next_run": first_run},
            )
            keep.add((app_label, name))
        gone = [row.pk for row in TaskSchedule.objects.all() if (row.app_label, row.name) not in keep]
        TaskSchedule.objects.filter(pk__in=gone).delete()


def run_next_due_task(
    now: dt.datetime,
    *,
    execute: Callable[[str], object],
    reschedule: Callable[[str, dt.datetime], dt.datetime],
    apps: Collection[str] | None = None,
) -> tuple[str, bool] | None:
    """Claim one task due at ``now``, run it and move its ``next_run``, all in one transaction. With ``apps`` (those on
    in the business), only a task of one of them: another app's is left as it is, untouched, and runs once when its app
    is on again.

    ``SELECT … FOR UPDATE SKIP LOCKED``: a second worker (a deploy overlaps the old one and the new one)
    skips the row this one holds, and once it commits the row is no longer due. ``execute(operation)``
    runs in a savepoint: a task that raises is logged and its writes undone, and it is rescheduled all the
    same, so it runs again at its next time instead of on every tick; ``last_run`` is the last run that
    finished. ``reschedule(cron, now)`` is the next time strictly after ``now``: missed times collapse into
    this one run. Returns ``("<app>.<name>", ran)``,
    or ``None`` when nothing is due.
    """
    with atomic():
        due = TaskSchedule.objects.select_for_update(skip_locked=True).filter(next_run__lte=now)
        if apps is not None:
            due = due.filter(app_label__in=list(apps))
        row = due.order_by("next_run", "app_label", "name").first()
        if row is None:
            return None
        ran = True
        try:
            with atomic():
                execute(row.operation)
        except Exception:
            ran = False
            logger.exception(
                "scheduler: %s (%s) failed; its writes were undone and it runs again at its next time.",
                row,
                row.operation,
            )
        row.next_run = reschedule(row.cron, now)
        if ran:
            row.last_run = now
        row.save(update_fields=["next_run", "last_run"])
    return str(row), ran


# ── The outbox relay's deliveries (base.relay) ───────────────────────────────────────────────────────────────────

#: The longest ``last_error`` a delivery keeps (the start of the error is what tells it).
LAST_ERROR_MAX_LENGTH = 2000
#: What a delivery past the deepest level says (``base.relay.MAX_EVENT_DEPTH``).
TOO_DEEP = "Not delivered: its depth, {depth}, is past the deepest level of events ({limit})."
#: The events the running delivery records, so they are handed over one level deeper, in its transaction.
_recorded_by_the_delivery: ContextVar[list[OutboxEvent] | None] = ContextVar(
    "base_recorded_by_the_delivery", default=None
)


@receiver(post_save, sender=OutboxEvent, dispatch_uid="base.services.recorded_by_the_delivery")
def _note_an_event_recorded_by_the_delivery(sender, instance: OutboxEvent, created: bool, **kwargs) -> None:
    recorded = _recorded_by_the_delivery.get()
    if created and recorded is not None:
        recorded.append(instance)


def _of_the_hub_at_work(event: OutboxEvent) -> OutboxEvent:
    """``event`` in the scope its hub has now: an outbox holds its own hub's events alone, and that hub's address may
    have changed since ``event`` was recorded, when its reactions would run for a hub that is not there."""
    hub = current_hub()
    if hub is not None:
        event.scope_key = hub.slug
    return event


def relay_take_events(
    now: dt.datetime,
    *,
    listeners: Callable[[OutboxEvent], list[str]],
    limit: int,
    max_depth: int,
    of_hubs: bool = True,
) -> int:
    """Take up to ``limit`` events nobody took yet, oldest first: one delivery per app of ``listeners(event)``,
    and the event's ``delivered_at`` (taken) in the same transaction. Returns how many it took. ``of_hubs=False``
    (control's outbox): a business's event is never taken there.

    ``SELECT … FOR UPDATE SKIP LOCKED``: a second worker (a deploy overlaps the old one and the new one) skips the
    events this one holds, and once it commits they are taken.
    """
    with atomic():
        events = OutboxEvent.objects.select_for_update(skip_locked=True).filter(delivered_at__isnull=True)
        if not of_hubs:
            events = events.exclude(scope_kind=HUB_SCOPE_KIND)
        taken = [_of_the_hub_at_work(event) for event in events.order_by("created_at", "id")[:limit]]
        _hand_over(taken, now=now, depth=0, listeners=listeners, max_depth=max_depth)
    return len(taken)


def relay_deliver_next(  # noqa: PLR0913
    now: dt.datetime,
    *,
    deliver: Callable[[str, OutboxEvent], object],
    listeners: Callable[[OutboxEvent], list[str]],
    carried: Callable[[str], bool],
    max_depth: int,
    max_attempts: int,
    backoff: Callable[[int], dt.timedelta],
    of_hubs: bool = True,
) -> tuple[EventDelivery, bool] | None:
    """Claim one delivery due at ``now`` (the oldest event first), run its app's reaction and mark it, all in
    one transaction; returns ``(delivery, delivered)``, or ``None`` when nothing is due.

    The claim is ``SKIP LOCKED``, as the scheduler's. ``deliver(app_label, event)`` runs in a savepoint, and the
    events it records (and keeps) are handed over in it, one level deeper. Those it records as the system take the
    event's actor when ``carried(actor)`` says it is passed on (``base.relay.carried``: a recovery's, whose events are
    nothing new to the business, or one an app declares to follow its own chain through the others' reactions), however
    deep the chain goes; those it records as someone of its own keep theirs. A reaction that raises has its writes
    undone and waits ``backoff(attempts)``; after ``max_attempts`` it is given up (``dead``). Either way it is
    logged with the event, and the other deliveries go on: a refusal of the business (an ``OperationError``) as a
    warning with its code; anything else, and the delivery given up, as an error with its traceback.
    """
    with atomic():
        due = EventDelivery.objects.select_for_update(skip_locked=True, of=("self",)).filter(
            status=EventDelivery.Status.PENDING, next_attempt_at__lte=now
        )
        if not of_hubs:
            due = due.exclude(event__scope_kind=HUB_SCOPE_KIND)
        delivery = due.select_related("event").order_by("event__created_at", "event_id", "app_label").first()
        if delivery is None:
            return None
        _of_the_hub_at_work(delivery.event)
        delivery.attempts += 1
        try:
            with atomic():
                recorded: list[OutboxEvent] = []
                token = _recorded_by_the_delivery.set(recorded)
                try:
                    deliver(delivery.app_label, delivery.event)
                finally:
                    _recorded_by_the_delivery.reset(token)
                # Only what the reaction kept: an event recorded in a savepoint it gave up is gone.
                kept = list(
                    OutboxEvent.objects.filter(pk__in=[event.pk for event in recorded]).order_by("created_at", "id")
                )
                if carried(delivery.event.actor):
                    system = system_context(Scope(delivery.event.scope_kind, delivery.event.scope_key)).actor
                    OutboxEvent.objects.filter(pk__in=[event.pk for event in kept], actor=system).update(
                        actor=delivery.event.actor
                    )
                _hand_over(kept, now=now, depth=delivery.depth + 1, listeners=listeners, max_depth=max_depth)
        except Exception as error:
            delivered = False
            delivery.last_error = f"{type(error).__name__}: {error}"[:LAST_ERROR_MAX_LENGTH]
            # A refusal of the business (an ``OperationError``: no issuer yet…) is expected and has its code; a
            # traceback only for the unexpected, and for the delivery given up.
            refused = isinstance(error, OperationError)
            reason = error.code if refused else type(error).__name__
            if delivery.attempts >= max_attempts:
                delivery.status = EventDelivery.Status.DEAD
                _tell_failed(Scope(delivery.event.scope_kind, delivery.event.scope_key))
                logger.exception(
                    "relay: %s gave up on %s (%s) after %d attempts (%s); its writes were undone.",
                    delivery.app_label,
                    delivery.event.name,
                    delivery.event_id,
                    delivery.attempts,
                    reason,
                )
            else:
                delivery.next_attempt_at = now + backoff(delivery.attempts)
                logger.log(
                    logging.WARNING if refused else logging.ERROR,
                    "relay: %s failed on %s (%s) with %s, attempt %d of %d; its writes were undone and it tries "
                    "again at %s.",
                    delivery.app_label,
                    delivery.event.name,
                    delivery.event_id,
                    reason,
                    delivery.attempts,
                    max_attempts,
                    delivery.next_attempt_at.isoformat(),
                    exc_info=not refused,
                )
        else:
            delivered = True
            delivery.status, delivery.delivered_at, delivery.last_error = EventDelivery.Status.DELIVERED, now, ""
        delivery.save(update_fields=["attempts", "status", "next_attempt_at", "last_error", "delivered_at"])
    return delivery, delivered


def _hand_over(
    events: list[OutboxEvent],
    *,
    now: dt.datetime,
    depth: int,
    listeners: Callable[[OutboxEvent], list[str]],
    max_depth: int,
) -> None:
    """One delivery of each event per app that listens to it, at ``depth``; the events are taken (``delivered_at``).

    Past ``max_depth`` the deliveries are written given up, with why: a reaction that records an event another
    reaction answers with an event… never loops.
    """
    if not events:
        return
    too_deep = depth > max_depth
    rows = [
        EventDelivery(
            event=event,
            app_label=app_label,
            depth=depth,
            next_attempt_at=now,
            status=EventDelivery.Status.DEAD if too_deep else EventDelivery.Status.PENDING,
            last_error=TOO_DEEP.format(depth=depth, limit=max_depth) if too_deep else "",
        )
        for event in events
        for app_label in listeners(event)
    ]
    EventDelivery.objects.bulk_create(rows)
    OutboxEvent.objects.filter(pk__in=[event.pk for event in events]).update(delivered_at=now)
    for row in rows if too_deep else ():
        logger.error(
            "relay: %s (%s) not delivered to %s: %s", row.event.name, row.event_id, row.app_label, row.last_error
        )
    for scope in {Scope(row.event.scope_kind, row.event.scope_key) for row in rows} if too_deep else ():
        _tell_failed(scope)


def _tell_failed(scope: Scope) -> None:
    """After the COMMIT, ``scope``'s hub hears that a failed event appeared: its bell and System › Failed events follow
    at once. A notice, not an outbox event: a listener of every event that failed on it would
    feed itself; and none after a rollback."""
    transaction.on_commit(partial(notify, scope, [events.FAILED_EVENT_CREATED]), robust=True)
