"""The worker's side of a move on control: each step is written only while the worker holds the hub's lease and the
hub still moves where it was going."""

import datetime as dt

import pytest
from django.utils import timezone

from control.models.copies import MovedCopy
from control.models.hubs import HubDue
from control.services import worker_move
from control.tests.conftest import a_cluster, a_ready_hub

pytestmark = pytest.mark.django_db

OWNER = "worker-a:1"
MOMENT = dt.datetime(2026, 11, 9, 14, 30, tzinfo=dt.UTC)


def a_hub_moving(**fields):
    origin, target = a_cluster(), a_cluster(name="cluster-2", host="writer-2.example")
    hub = a_ready_hub(cluster=origin, moving_to=target, **fields)
    now = timezone.now()
    HubDue.objects.create(hub=hub, due_at=now, lease_owner=OWNER, lease_until=now + dt.timedelta(minutes=5))
    return hub, origin, target


def test_a_move_is_still_the_workers_while_it_holds_the_lease_and_the_hub_moves_there():
    hub, origin, target = a_hub_moving()

    worker_move.still_ours(hub.pk, target.pk, OWNER)

    for elsewhere, owner in [(origin.pk, OWNER), (target.pk, "worker-b:1")]:
        with pytest.raises(worker_move.MoveTaken):
            worker_move.still_ours(hub.pk, elsewhere, owner)


def test_a_move_asked_to_be_undone_goes_no_further_but_may_go_back():
    hub, _, target = a_hub_moving(move_undo_asked_at=timezone.now())

    with pytest.raises(worker_move.MoveTaken):
        worker_move.still_ours(hub.pk, target.pk, OWNER)
    worker_move.still_ours(hub.pk, target.pk, OWNER, forward=False)


def test_the_switch_puts_the_hub_on_its_destination_and_dates_the_copy_left_behind():
    hub, origin, target = a_hub_moving()
    worker_move.copy_pending(hub.pk, origin.pk, "hub_old", schema_state="", schema_apps=None)
    assert worker_move.pending_copy(hub.pk).db_name == "hub_old"

    worker_move.move_finished(hub.pk, target.pk, origin.pk, "hub_old", MOMENT, owner=OWNER)

    hub.refresh_from_db()
    assert (hub.cluster_id, hub.moving_to_id, worker_move.pending_copy(hub.pk)) == (target.pk, None, None)
    [copy] = worker_move.copies_due(MOMENT)
    assert (copy.cluster_id, copy.db_name, copy.moved_at) == (origin.pk, "hub_old", MOMENT)
    worker_move.forget_copy(origin.pk, "hub_old")
    assert not MovedCopy.objects.exists()
