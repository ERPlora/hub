"""When the worker has something to do next in a business's own database (``base.queries.due_work``): the next run of a
task of one of its apps that are on and the next try of a delivery waiting, read in one transaction."""

import datetime as dt

import pytest
from django.utils import timezone
from live.models import OutboxEvent

from base.models import EventDelivery, TaskSchedule
from base.queries import due_work
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

pytestmark = pytest.mark.django_db(databases=hubs.HUB_DATABASES)

NOW = timezone.now()


def task(app_label: str, name: str, at: dt.datetime) -> None:
    TaskSchedule.objects.create(app_label=app_label, name=name, operation=f"{app_label}.x.run", cron="* * * * *", next_run=at)


def delivery(status: str, at: dt.datetime) -> None:
    event = OutboxEvent.objects.create(scope_kind="host", scope_key="tenant-a", name="demo.item.created", payload={})
    EventDelivery.objects.create(event=event, app_label="flow", status=status, next_attempt_at=at)


def test_nothing_waiting_has_no_time(hub_a):
    with use_hub(hub_a):
        assert due_work.next_due(frozenset({"verifactu"})) == due_work.DueWork(task_at=None, delivery_at=None)


def test_the_earliest_task_of_an_app_that_is_on_and_the_earliest_delivery_waiting(hub_a):
    with use_hub(hub_a):
        task("verifactu", "process_queue", NOW + dt.timedelta(minutes=1))
        task("printing", "prune", NOW + dt.timedelta(minutes=30))
        task("flow", "fire_due", NOW - dt.timedelta(days=3))  # off: it waits, untouched, for its app
        delivery(EventDelivery.Status.PENDING, NOW + dt.timedelta(seconds=8))
        delivery(EventDelivery.Status.PENDING, NOW + dt.timedelta(minutes=5))
        delivery(EventDelivery.Status.DEAD, NOW - dt.timedelta(hours=1))
        delivery(EventDelivery.Status.DELIVERED, NOW - dt.timedelta(hours=1))

        due = due_work.next_due(frozenset({"verifactu", "printing"}))

    assert due == due_work.DueWork(task_at=NOW + dt.timedelta(minutes=1), delivery_at=NOW + dt.timedelta(seconds=8))
