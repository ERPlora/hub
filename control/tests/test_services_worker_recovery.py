"""The worker's side of a recovery from a separate copy on control: under the recovery's own lease."""

import datetime as dt

import pytest
from django.utils import timezone

from control.models import CopyRecovery
from control.services import worker_move, worker_recovery
from control.tests.conftest import COPY_MOMENT, a_cluster, a_ready_hub, a_separate_copy

pytestmark = pytest.mark.django_db

RECOVERY_LEASE = dt.timedelta(minutes=5)


def a_recovery(slug: str, copy_status: str = "made") -> CopyRecovery:
    hub = a_ready_hub(slug=slug, cluster=a_cluster(name=slug, host=f"{slug}.example"))
    copy = a_separate_copy(hub, status=copy_status)
    return CopyRecovery.objects.create(copy=copy, apps=["customer"], asked_by="root")


def test_only_the_recoveries_of_made_copies_are_due_and_one_worker_at_a_time_does_each():
    due = a_recovery("acme")
    a_recovery("bravo", copy_status="copying")
    now = timezone.now()

    assert worker_recovery.recoveries_due() == [due.pk]
    assert worker_recovery.claim_recovery(due.pk, now, RECOVERY_LEASE, "worker-a:1") == due
    assert worker_recovery.claim_recovery(due.pk, now, RECOVERY_LEASE, "worker-b:1") is None
    worker_recovery.still_recovering(due.pk, RECOVERY_LEASE, "worker-a:1")
    with pytest.raises(worker_move.MoveTaken):
        worker_recovery.still_recovering(due.pk, RECOVERY_LEASE, "worker-b:1")


def test_a_recovery_ends_once_with_what_it_gave_back_and_its_lease_given_back():
    recovery = a_recovery("acme")
    worker_recovery.claim_recovery(recovery.pk, timezone.now(), RECOVERY_LEASE, "worker-a:1")
    results = [{"app": "customer", "created": 3}]

    with pytest.raises(worker_move.MoveTaken):
        worker_recovery.recovery_done(recovery.pk, results, COPY_MOMENT, "worker-b:1")
    worker_recovery.recovery_done(recovery.pk, results, COPY_MOMENT, "worker-a:1")

    recovery.refresh_from_db()
    assert (recovery.status, recovery.results, recovery.done_at, recovery.lease_owner) == (
        "done",
        results,
        COPY_MOMENT,
        "",
    )
    with pytest.raises(worker_move.MoveTaken):
        worker_recovery.recovery_failed(recovery.pk, "too late", [], COPY_MOMENT, "worker-a:1")
