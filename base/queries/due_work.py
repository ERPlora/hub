"""When the worker has something to do next in the business whose database is open (``base.hub_visits``)."""

import datetime as dt
from collections.abc import Collection
from dataclasses import dataclass

from django.db.models import Min
from live.operations import atomic

from base.models import EventDelivery, TaskSchedule


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
