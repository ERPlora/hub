"""A demo is born with its database and, when it ends, its database is dropped alone, then its files, outside any
transaction of control and before its rows; a store that fails leaves it ``dropping`` and tried again."""

import datetime as dt

from django.db import connections as django_connections
from django.utils import timezone

from base import services
from base.tenancy import connections as tenancy_connections, names, ops, provision
from base.tenancy.tests.s3 import (  # noqa: F401
    aws_test_credentials,
    hub_files_bucket,
    hub_files_entry,
    keep_files,
    moto_s3,
    objects,
    spy_on_the_purge,
)
from base.tenancy.tests.test_provision import databases, fresh, nothing_checked_yet
from control.models import Hub, HubDue

#: The provisioning tests' own autouse fixture.
__all__ = ["nothing_checked_yet"]


def worked_on(monkeypatch) -> list:
    """The hubs a pass over ``hub_due`` works on, as it counts them: each demo it dropped and each preparation that
    ended. Compared with what ``provision.run_due`` returns, never a fixed total: the pass also works on whatever else
    its process left due."""
    seen = []
    drop, prepare = provision._drop, provision._prepare

    def dropped(hub_id, now):
        if result := drop(hub_id, now):
            seen.append(hub_id)
        return result

    def prepared(hub_id, **kwargs):
        prepare(hub_id, **kwargs)
        seen.append(hub_id)

    monkeypatch.setattr(provision, "_drop", dropped)
    monkeypatch.setattr(provision, "_prepare", prepared)
    return seen


def test_a_demo_is_born_with_its_database_and_dropped_alone_when_it_ends(registry, told):
    demo = registry.hub(demo=True)
    assert demo.db_name == names.demo_db_name(tenancy_connections.control_name(), demo.id)
    assert provision.provision(demo) is True
    assert fresh(demo).status == "ready" and told == []  # a demo's SaaS asks; it is not told
    Hub.objects.filter(pk=demo.pk).update(expires_at=timezone.now() - dt.timedelta(minutes=1))
    before = databases()

    services.demos.reap_demos()

    demo = fresh(demo)
    assert (demo.status, demo.purged_at is not None) == ("purged", True)
    assert databases() == before - {demo.db_name}
    assert not HubDue.objects.filter(pk=demo.pk).exists()


def test_a_demos_database_is_dropped_outside_any_transaction_of_control_and_before_its_rows(registry, monkeypatch, told):
    demo = registry.hub(demo=True)
    provision.provision(demo)
    Hub.objects.filter(pk=demo.pk).update(expires_at=timezone.now() - dt.timedelta(minutes=1))
    real, seen = ops.drop_database, []

    def spied(name, **kwargs):
        seen.append((name, django_connections["default"].in_atomic_block, fresh(demo).status))
        return real(name, **kwargs)

    monkeypatch.setattr(ops, "drop_database", spied)

    services.demos.reap_demos()

    assert seen == [(demo.db_name, False, "dropping")]
    assert fresh(demo).status == "purged"


def test_a_demo_that_ends_goes_with_its_files_and_every_other_keeps_theirs(registry, told, hub_files_bucket, moto_s3):
    ended, live_demo, business = registry.hub(demo=True), registry.hub(demo=True), registry.hub()
    for hub in (ended, live_demo, business):
        assert provision.provision(hub) is True
    keep_files(ended)
    kept = keep_files(live_demo) | keep_files(business)
    Hub.objects.filter(pk=ended.pk).update(expires_at=timezone.now() - dt.timedelta(minutes=1))

    services.demos.reap_demos()

    assert (fresh(ended).status, fresh(live_demo).status, fresh(business).status) == ("purged", "ready", "ready")
    assert set(objects(moto_s3, hub_files_bucket)) == kept


def test_a_demos_files_go_right_after_its_database_outside_any_transaction_and_before_its_rows(
    registry, monkeypatch, told, hub_files_bucket
):
    demo = registry.hub(demo=True)
    provision.provision(demo)
    Hub.objects.filter(pk=demo.pk).update(expires_at=timezone.now() - dt.timedelta(minutes=1))
    seen = spy_on_the_purge(monkeypatch, lambda: fresh(demo).status)

    services.demos.reap_demos()

    assert seen == ["drop", ("files", demo.pk, False, "dropping")]
    assert fresh(demo).status == "purged"


def test_a_store_that_fails_leaves_the_demo_dropping_noted_and_tried_again_never_purged(
    registry, told, hub_files_bucket, moto_s3, settings, caplog
):
    demo = registry.hub(demo=True)
    provision.provision(demo)
    keep_files(demo)
    Hub.objects.filter(pk=demo.pk).update(expires_at=timezone.now() - dt.timedelta(minutes=1))
    settings.STORAGES = {**settings.STORAGES, "hub_files": hub_files_entry(moto_s3, "erplora-test-no-such-bucket")}
    now = timezone.now()

    services.demos.reap_demos(now)

    failed = fresh(demo)
    assert (failed.status, failed.purged_at) == ("dropping", None), "a purge that left files behind is not done"
    assert failed.last_error.startswith("drop_failed: HubFilesNotDeleted: ")
    assert failed.attempts == 1
    assert failed.next_attempt_at > now
    assert HubDue.objects.get(pk=demo.pk).due_at == failed.next_attempt_at, "its turn waits for its next attempt"
    assert failed.db_name not in databases(), "the database went first"
    assert "base.demo.purge_failed" in caplog.text

    settings.STORAGES = {**settings.STORAGES, "hub_files": hub_files_entry(moto_s3, hub_files_bucket)}
    provision.run_due(failed.next_attempt_at + dt.timedelta(seconds=1))

    purged = fresh(demo)
    assert purged.status == "purged"
    assert objects(moto_s3, hub_files_bucket) == {}


def test_a_demos_database_that_is_not_dropped_keeps_its_files(registry, monkeypatch, told, hub_files_bucket, moto_s3):
    demo = registry.hub(demo=True)
    provision.provision(demo)
    kept = keep_files(demo)
    Hub.objects.filter(pk=demo.pk).update(expires_at=timezone.now() - dt.timedelta(minutes=1))

    def refused(name, **kwargs):
        raise ops.DatabaseOpsError("no")

    monkeypatch.setattr(ops, "drop_database", refused)

    services.demos.reap_demos()

    assert fresh(demo).status == "dropping"
    assert set(objects(moto_s3, hub_files_bucket)) == kept


def test_a_demo_that_ends_while_it_is_made_is_dropped_not_finished(registry, monkeypatch, told):
    demo = registry.hub(demo=True, status=Hub.Status.CREATING, expires_at=timezone.now() - dt.timedelta(minutes=1))
    HubDue.mark_due(demo)
    seen = worked_on(monkeypatch)

    worked = provision.run_due()

    assert fresh(demo).status == "purged" and demo.db_name not in databases()
    assert not HubDue.objects.filter(pk=demo.pk).exists()
    # A drop is work it counts, as a preparation is.
    assert demo.pk in seen and worked == len(seen)
