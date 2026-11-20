"""When the worker has something to do next (``base.queries.due_work``): in a business's own database, the next run of a
task of one of its apps that are on and the next try of a delivery waiting; on control, the next time a hub is due in
``hub_due`` or free from a lease, or a move asked for its night comes. Each read in one transaction."""

import datetime as dt

import pytest
from django.utils import timezone
from live.models import OutboxEvent

from base.models import EventDelivery, TaskSchedule
from base.queries import due_work
from base.tenancy.context import use_control, use_hub
from base.tenancy.tests import hubs
from control.models import Cluster, Hub, HubDue

pytestmark = pytest.mark.django_db(databases=hubs.HUB_DATABASES)

def task(app_label: str, name: str, at: dt.datetime) -> None:
    TaskSchedule.objects.create(app_label=app_label, name=name, operation=f"{app_label}.x.run", cron="* * * * *", next_run=at)


def delivery(status: str, at: dt.datetime) -> None:
    event = OutboxEvent.objects.create(scope_kind="host", scope_key="tenant-a", name="demo.item.created", payload={})
    EventDelivery.objects.create(event=event, app_label="flow", status=status, next_attempt_at=at)


def test_nothing_waiting_has_no_time(hub_a):
    with use_hub(hub_a):
        assert due_work.next_due(frozenset({"verifactu"})) == due_work.DueWork(task_at=None, delivery_at=None)


def test_the_earliest_task_of_an_app_that_is_on_and_the_earliest_delivery_waiting(hub_a):
    now = timezone.now()
    with use_hub(hub_a):
        task("verifactu", "process_queue", now + dt.timedelta(minutes=1))
        task("printing", "prune", now + dt.timedelta(minutes=30))
        task("flow", "fire_due", now - dt.timedelta(days=3))  # off: it waits, untouched, for its app
        delivery(EventDelivery.Status.PENDING, now + dt.timedelta(seconds=8))
        delivery(EventDelivery.Status.PENDING, now + dt.timedelta(minutes=5))
        delivery(EventDelivery.Status.DEAD, now - dt.timedelta(hours=1))
        delivery(EventDelivery.Status.DELIVERED, now - dt.timedelta(hours=1))

        due = due_work.next_due(frozenset({"verifactu", "printing"}))

    assert due == due_work.DueWork(task_at=now + dt.timedelta(minutes=1), delivery_at=now + dt.timedelta(seconds=8))


def test_control_keeps_no_time_when_nothing_is_to_come(hub_a):
    now = timezone.now()
    HubDue.mark_due(hub_a, now - dt.timedelta(minutes=1))  # due already: the pass just offered it

    with use_control():
        assert due_work.next_on_control(now) is None


def test_the_first_time_to_come_of_a_hub_due_a_lease_running_out_and_a_move_asked_for_its_night(hub_a, hub_b):
    now = timezone.now()
    HubDue.mark_due(hub_a, now + dt.timedelta(minutes=9))
    HubDue.mark_due(hub_b, now - dt.timedelta(minutes=1))
    HubDue.objects.filter(pk=hub_b.pk).update(lease_until=now + dt.timedelta(minutes=4))  # another worker's
    elsewhere = Cluster.objects.create(name="elsewhere", host="writer-elsewhere.example")
    Hub.objects.filter(pk=hub_a.pk).update(move_scheduled_to=elsewhere, move_scheduled_for=now + dt.timedelta(minutes=6))

    with use_control():
        assert due_work.next_on_control(now) == now + dt.timedelta(minutes=4)
        HubDue.objects.filter(pk=hub_b.pk).update(lease_until=None)
        assert due_work.next_on_control(now) == now + dt.timedelta(minutes=6)
        Hub.objects.filter(pk=hub_a.pk).update(move_scheduled_to=None, move_scheduled_for=None)
        assert due_work.next_on_control(now) == now + dt.timedelta(minutes=9)
