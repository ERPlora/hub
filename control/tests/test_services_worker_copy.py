"""The worker's side of a separate copy on control: under the copy's own lease, never the hub's."""

import datetime as dt

import pytest
from django.utils import timezone

from control.models.copies import RestoredCopy
from control.services import worker_copy, worker_move
from control.tests.conftest import COPY_MOMENT, a_cluster, a_ready_hub, a_separate_copy

pytestmark = pytest.mark.django_db

LEASE = dt.timedelta(minutes=5)


def a_copy_to_make() -> RestoredCopy:
    source = a_cluster(name="temporary", host="temporary.example", is_open=False)
    return a_separate_copy(a_ready_hub(cluster=a_cluster()), source=source)


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
        worker_copy.copy_made(copy.pk, COPY_MOMENT, "worker-b:1")
    worker_copy.copy_made(copy.pk, COPY_MOMENT, "worker-a:1")

    copy.refresh_from_db()
    assert (copy.status, copy.made_at, copy.source_id, copy.lease_owner) == ("made", COPY_MOMENT, None, "")
    assert worker_copy.copies_to_make() == []
    assert worker_copy.aside_copies_due(COPY_MOMENT) == [copy]
