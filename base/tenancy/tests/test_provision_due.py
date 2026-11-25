"""Whoever works on a hub holds its ``hub_due`` lease, one worker at a time, and the due pass works on what is due when
it is due: two provisionings at once make one database, a lease lost stops its holder, a frozen platform waits."""

import datetime as dt
import logging
import threading

import pytest
from django.db import connections as django_connections
from django.utils import timezone

from base import services
from base.tenancy import migrator, ops, provision
from base.tenancy.context import use_control
from base.tenancy.tests.test_provision import databases, fresh, nothing_checked_yet
from control.models.hubs import Hub, HubDue

#: The provisioning tests' own autouse fixture.
__all__ = ["nothing_checked_yet"]


def test_two_provisionings_of_one_hub_at_once_make_one_database_once(registry, monkeypatch, told):
    hub = registry.hub()
    real, made = ops.clone_database, []

    def spied(*args, **kwargs):
        made.append(real(*args, **kwargs))
        return made[-1]

    monkeypatch.setattr(ops, "clone_database", spied)
    start, results = threading.Barrier(2), []

    def run():
        try:
            start.wait(5)
            results.append(provision.provision(hub))
        finally:
            django_connections.close_all()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)

    hub = fresh(hub)
    assert made == [True], made
    assert (hub.status, hub.attempts) == ("ready", 0)
    assert told == [hub.id]
    assert sorted(results) in ([False, True], [True, True])


def test_the_due_pass_prepares_what_is_due_and_leaves_what_waits_for_its_retry(registry, told):
    due = registry.hub()
    later = timezone.now() + dt.timedelta(minutes=5)
    waiting = registry.hub(status=Hub.Status.FAILED, attempts=1, next_attempt_at=later)
    HubDue.mark_due(due)
    HubDue.mark_due(waiting, later)

    provision.run_due()

    assert fresh(due).status == "ready"
    assert (fresh(waiting).status, fresh(waiting).attempts) == ("failed", 1)
    assert HubDue.objects.get(pk=waiting.pk).due_at == later
    assert not HubDue.objects.filter(pk=due.pk).exists()


def test_a_failed_hub_made_due_early_for_something_else_waits_for_its_retry(registry, told):
    now = timezone.now()
    later = now + dt.timedelta(minutes=5)
    hub = registry.hub(status=Hub.Status.FAILED, attempts=1, next_attempt_at=later)
    HubDue.mark_due(hub, now)

    provision.run_due(now)

    hub = fresh(hub)
    assert (hub.status, hub.attempts) == ("failed", 1) and hub.db_name not in databases()
    assert HubDue.objects.get(pk=hub.pk).due_at == later


def test_a_sign_up_while_frozen_waits_and_is_made_on_the_worker_s_first_tick_after_the_freeze_is_lifted(
    registry, monkeypatch, told
):
    """The staff freezes the platform for a database upgrade; a business that signs up meanwhile is kept waiting, its
    database not made, and the worker makes it on its own on the first tick after the freeze is lifted, which notifies
    it. Every other pass of the tick is left out: their own tests are ``base/tests/test_worker.py``'s."""
    from live.context import system_context

    from base import catalog, worker
    from base.catalog.register_apps import RegisterResult
    from base.registry import REGISTRY_SCOPE
    from control.schemas import FreezeIn
    from control.services.freeze import freeze_set

    platform = system_context(REGISTRY_SCOPE)
    monkeypatch.setattr(catalog.register_apps, "register_apps", lambda: RegisterResult(0, 0, 0, True))
    for target, name in ((worker, "_relay"), (worker.hub_visits.HubVisits, "serve"), (worker, "_activations"), (worker, "_reap")):
        monkeypatch.setattr(target, name, lambda *_, **__: None)
    hub = registry.hub()
    HubDue.mark_due(hub)
    with use_control():
        freeze_set(platform, FreezeIn(frozen=True, reason="Aurora upgrade"))
    seen: list[str] = []
    stop = threading.Event()

    def wait(seconds: float) -> bool:
        seen.append(fresh(hub).status)
        if len(seen) == 1:
            with use_control():
                freeze_set(platform, FreezeIn(frozen=False))
            stop.wait(0.3)  # its notice reaches the worker's LISTEN; two real ticks are 5 s apart
        else:
            stop.set()
        return stop.is_set()

    try:
        assert worker.run(stop, tick_seconds=0, wait=wait) == 0
    finally:
        with use_control():
            freeze_set(platform, FreezeIn(frozen=False))

    assert seen == ["requested", "ready"]
    assert hub.db_name in databases()
    assert told == [hub.pk]


def test_its_lease_is_renewed_while_its_schema_is_migrated(registry, monkeypatch, told):
    hub = registry.hub()
    real = migrator.schema.ensure_schema
    renewed = []

    def beating(row, **kwargs):
        before = HubDue.objects.get(pk=row.pk).lease_until
        kwargs["heartbeat"]()
        renewed.append(HubDue.objects.get(pk=row.pk).lease_until > before)
        return real(row, **kwargs)

    monkeypatch.setattr(migrator.schema, "ensure_schema", beating)

    assert provision.provision(hub) is True
    assert renewed == [True]


def test_a_lease_lost_while_its_schema_is_migrated_stops_it_there_without_failing_it(
    registry, monkeypatch, told, caplog
):
    hub = registry.hub()

    def taken_meanwhile(row, **kwargs):
        HubDue.objects.filter(pk=row.pk).update(lease_owner="another-worker")
        kwargs["heartbeat"]()

    monkeypatch.setattr(migrator.schema, "ensure_schema", taken_meanwhile)

    with caplog.at_level(logging.INFO, logger="base.tenancy.provision"):
        assert provision.provision(hub) is False

    hub = fresh(hub)
    assert (hub.status, hub.attempts, hub.last_error) == ("migrating", 0, "")
    # Said as what it is: another worker holds it now, nothing failed.
    assert "provision.stopped" in caplog.text and "provision.failed" not in caplog.text


def test_a_hub_held_by_another_worker_is_not_taken(registry, told):
    hub = registry.hub()
    now = timezone.now()
    HubDue.mark_due(hub, now)
    HubDue.objects.filter(pk=hub.pk).update(lease_until=now + dt.timedelta(seconds=60))

    provision.run_due(now)
    assert provision.provision(hub, now=now) is False

    assert fresh(hub).status == "requested" and hub.db_name not in databases()


# ── The lease is its holder's ───────────────────────────────────────────────────────────────────────────────────────


def test_a_lease_another_worker_took_over_once_it_expired_is_never_touched_by_its_first_holder(registry, told):
    hub = registry.hub()
    now = timezone.now()
    assert services.provisioning.claim_hub(hub.pk, now, provision.LEASE, owner="worker-1") is not None
    later = now + provision.LEASE + dt.timedelta(seconds=1)
    assert services.provisioning.claim_hub(hub.pk, later, provision.LEASE, owner="worker-2") is not None

    with pytest.raises(services.provisioning.ProvisioningStopped, match="lease"):
        services.provisioning.provision_step(hub.pk, Hub.Status.CREATING, later, provision.LEASE, owner="worker-1")
    assert services.provisioning.provision_failed(hub.pk, later, "too late", owner="worker-1") is None
    services.provisioning.release_hub(hub.pk, later, owner="worker-1")

    due = HubDue.objects.get(pk=hub.pk)
    assert (due.lease_owner, due.lease_until) == ("worker-2", later + provision.LEASE)
    assert (fresh(hub).status, fresh(hub).attempts) == ("requested", 0)


def test_a_lease_is_never_taken_while_its_holder_keeps_it(registry, told):
    hub = registry.hub()
    now = timezone.now()
    services.provisioning.claim_hub(hub.pk, now, provision.LEASE, owner="worker-1")

    assert services.provisioning.claim_hub(hub.pk, now + dt.timedelta(seconds=30), provision.LEASE, owner="worker-2") is None
    assert services.provisioning.claim_next_due_hub(now + dt.timedelta(seconds=30), provision.LEASE, owner="worker-2") is None


def test_the_due_pass_leases_one_hub_at_a_time_right_before_it_works_on_it(registry, monkeypatch, told):
    first, second = registry.hub(), registry.hub()
    now = timezone.now()
    HubDue.mark_due(first, now - dt.timedelta(seconds=2))
    HubDue.mark_due(second, now - dt.timedelta(seconds=1))
    seen = []

    def prepare(hub_id, **kwargs):
        other = second if hub_id == first.pk else first
        seen.append((hub_id, HubDue.objects.get(pk=other.pk).lease_owner))

    monkeypatch.setattr(provision, "_prepare", prepare)

    worked = provision.run_due(now)

    # Theirs, in their turn, and how many it worked on: whatever else its process left due is worked on too.
    ours = [entry for entry in seen if entry[0] in (first.pk, second.pk)]
    assert [hub_id for hub_id, _ in ours] == [first.pk, second.pk]
    assert worked == len(seen)
    # While the first is worked on, the second is nobody's yet: its lease starts when its turn comes.
    assert ours[0] == (first.pk, "")
