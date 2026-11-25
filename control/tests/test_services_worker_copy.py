"""The worker's side of a separate copy on control: under the copy's own lease, never the hub's."""

import datetime as dt
import uuid

import pytest
from django.utils import timezone

from control.models import RestoredCopy
from control.services import worker_copy, worker_move
from control.tests.conftest import a_cluster, a_ready_hub

pytestmark = pytest.mark.django_db

LEASE = dt.timedelta(minutes=5)
MOMENT = dt.datetime(2026, 11, 9, 14, 30, tzinfo=dt.UTC)


def a_copy_to_make() -> RestoredCopy:
    source = a_cluster(name="temporary", host="temporary.example", is_open=False)
    hub = a_ready_hub(cluster=a_cluster())
    return RestoredCopy.objects.create(
        hub=hub,
        cluster=hub.cluster,
        source=source,
        restore_point=MOMENT,
        db_name=f"copy_{uuid.uuid7().hex}",
        asked_by="root",
    )


def test_one_worker_at_a_time_makes_a_copy_and_the_next_goes_on_once_it_is_given_back():
    copy = a_copy_to_make()
    now = timezone.now()

    assert worker_copy.copies_to_make() == [copy.pk]
    assert worker_copy.claim_copy(copy.pk, now, LEASE, "worker-a:1") == copy
    assert worker_copy.claim_copy(copy.pk, now, LEASE, "worker-b:1") is None
    worker_copy.release_copy(copy.pk, "worker-a:1")
    assert worker_copy.claim_copy(copy.pk, now, LEASE, "worker-b:1") == copy


def test_only_the_worker_that_holds_it_says_it_is_made():
    copy = a_copy_to_make()
    worker_copy.claim_copy(copy.pk, timezone.now(), LEASE, "worker-a:1")

    with pytest.raises(worker_move.MoveTaken):
        worker_copy.copy_made(copy.pk, MOMENT, "worker-b:1")
    worker_copy.copy_made(copy.pk, MOMENT, "worker-a:1")

    copy.refresh_from_db()
    assert (copy.status, copy.made_at, copy.source_id, copy.lease_owner) == ("made", MOMENT, None, "")
    assert worker_copy.copies_to_make() == []
    assert worker_copy.aside_copies_due(MOMENT) == [copy]
