"""The worker's side of a recovery from a separate copy on control: under the recovery's own lease."""

import datetime as dt
import uuid

import pytest
from django.utils import timezone

from control.models import CopyRecovery, RestoredCopy
from control.services import worker_move, worker_recovery
from control.tests.conftest import a_cluster, a_ready_hub

pytestmark = pytest.mark.django_db

LEASE = dt.timedelta(minutes=5)
MOMENT = dt.datetime(2026, 11, 9, 14, 30, tzinfo=dt.UTC)


def a_recovery(slug: str, copy_status: str = "made") -> CopyRecovery:
    hub = a_ready_hub(slug=slug, cluster=a_cluster(name=slug, host=f"{slug}.example"))
    copy = RestoredCopy.objects.create(
        hub=hub,
        cluster=hub.cluster,
        restore_point=MOMENT,
        db_name=f"copy_{uuid.uuid7().hex}",
        status=copy_status,
        asked_by="root",
    )
    return CopyRecovery.objects.create(copy=copy, apps=["customer"], asked_by="root")


def test_only_the_recoveries_of_made_copies_are_due_and_one_worker_at_a_time_does_each():
    due = a_recovery("acme")
    a_recovery("bravo", copy_status="copying")
    now = timezone.now()

    assert worker_recovery.recoveries_due() == [due.pk]
    assert worker_recovery.claim_recovery(due.pk, now, LEASE, "worker-a:1") == due
    assert worker_recovery.claim_recovery(due.pk, now, LEASE, "worker-b:1") is None
    worker_recovery.still_recovering(due.pk, LEASE, "worker-a:1")
    with pytest.raises(worker_move.MoveTaken):
        worker_recovery.still_recovering(due.pk, LEASE, "worker-b:1")


def test_a_recovery_ends_once_with_what_it_gave_back_and_its_lease_given_back():
    recovery = a_recovery("acme")
    worker_recovery.claim_recovery(recovery.pk, timezone.now(), LEASE, "worker-a:1")
    results = [{"app": "customer", "created": 3}]

    with pytest.raises(worker_move.MoveTaken):
        worker_recovery.recovery_done(recovery.pk, results, MOMENT, "worker-b:1")
    worker_recovery.recovery_done(recovery.pk, results, MOMENT, "worker-a:1")

    recovery.refresh_from_db()
    assert (recovery.status, recovery.results, recovery.done_at, recovery.lease_owner) == ("done", results, MOMENT, "")
    with pytest.raises(worker_move.MoveTaken):
        worker_recovery.recovery_failed(recovery.pk, "too late", [], MOMENT, "worker-a:1")
