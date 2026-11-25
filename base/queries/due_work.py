"""When the worker has something to do next: in the business whose database is open (``base.hub_visits``), and on
control (``base.control_pace``)."""

import datetime as dt
from collections.abc import Collection
from dataclasses import dataclass

from django.db.models import Min
from django.db.models.functions import Coalesce, Greatest
from live.operations import atomic

from base.models.relay import EventDelivery
from base.models.scheduler import TaskSchedule
from control.models.hubs import Hub, HubDue


@dataclass(frozen=True)
class DueWork:
    """The next run of a task of an app that is on, and the next try of a delivery waiting; ``None`` when none."""

    task_at: dt.datetime | None
    delivery_at: dt.datetime | None


def next_due(apps: Collection[str]) -> DueWork:
    """What comes next in the open business, ``apps`` being those it has on (a task of another app waits for it and
    wakes nobody), read in one transaction."""
    with atomic():
        task_at = TaskSchedule.objects.filter(app_label__in=list(apps)).aggregate(at=Min("next_run"))["at"]
        delivery_at = EventDelivery.objects.filter(status=EventDelivery.Status.PENDING).aggregate(
            at=Min("next_attempt_at")
        )["at"]
    return DueWork(task_at=task_at, delivery_at=delivery_at)


def next_on_control(now: dt.datetime) -> dt.datetime | None:
    """The first time after ``now`` that control has work for the worker: a hub due in ``hub_due`` then, or free then
    from another worker's lease, or a move asked for its night; ``None`` when none is to come. What is due already was
    offered to the pass that just ran. Read in one transaction, on control."""
    with atomic():
        free_at = Greatest("due_at", Coalesce("lease_until", "due_at"))
        hub_due = HubDue.objects.annotate(at=free_at).filter(at__gt=now).aggregate(first=Min("at"))["first"]
        moves = Hub.objects.filter(move_scheduled_to__isnull=False, move_scheduled_for__gt=now)
        night = moves.aggregate(first=Min("move_scheduled_for"))["first"]
    return min((at for at in (hub_due, night) if at is not None), default=None)
