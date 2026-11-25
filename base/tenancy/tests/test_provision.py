"""A hub's database made at sign-up and a demo's dropped when it ends.

``base.tenancy.provision`` takes a hub ``requested`` through ``creating`` (its database cloned from its vertical's
template on its cluster, private, with its identity), ``migrating`` (the clone brought to the code's leaf, its
``schema_apps`` noted) and ``seeding`` (the SaaS's photo kept on its row) to ``ready``, the SaaS told; a step that
fails leaves it ``failed`` with a readable error and its next attempt, never an exception. Whoever works on a hub holds
its ``hub_due`` lease: two at once make one database. A new hub goes to the open cluster with the fewest hubs under its
limit, or to the settings' own server when there are no clusters. A demo's database is dropped alone when it ends.

These tests make real databases next to the session's (``base/tenancy/tests/hubs.py``), so they run outside a test
case (``django_db_blocker``; Django's test case only lets a test reach the aliases it names) and clean up after
themselves: the rows they wrote in control and the databases they made.

Where a new hub goes, demos, ``hub_due`` and its lease, the apps a business is born with and no hub sharing control's
database are each tested in their own ``test_provision_<topic>.py``.
"""

import datetime as dt
import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.db import connections as django_connections
from django.db.migrations.loader import MigrationLoader
from django.utils import timezone

from base import services
from base.models.activation import AppActivation
from base.models.locations import Location
from base.tenancy import connections as tenancy_connections, identity, ops, provision
from base.tenancy.context import use_control, use_hub
from base.tenancy.tests import hubs
from control.models.hubs import Hub, HubDue


def databases() -> set[str]:
    """The databases of this session's control database (other sessions make and drop theirs meanwhile)."""
    control = tenancy_connections.control_name()
    with hubs._maintenance() as conn:
        return {row[0] for row in conn.execute("SELECT datname FROM pg_database") if row[0].startswith(control)}


@pytest.fixture(autouse=True)
def nothing_checked_yet(monkeypatch):
    monkeypatch.setattr(identity, "_verified", set())


def fresh(hub: Hub) -> Hub:
    return Hub.objects.select_related("cluster").get(pk=hub.pk)


def test_a_business_is_born_with_its_own_database_its_identity_and_its_schema(registry, hub_databases, told):
    hub = registry.hub()

    assert provision.provision(hub) is True

    hub = fresh(hub)
    graph = MigrationLoader(None, ignore_no_migrations=True).graph
    expected = {app: leaf for app, leaf in graph.leaf_nodes() if app in {"base", "live", *hub_databases.apps}}
    assert (hub.status, hub.attempts, hub.last_error, hub.next_attempt_at) == ("ready", 0, "", None)
    assert hub.ready_at is not None and hub.schema_state == "current"
    assert hub.schema_apps == expected
    assert hub.db_name in databases()
    assert hubs.table_names(hub.db_name) == hubs.table_names(hub_databases.template)
    assert not HubDue.objects.filter(pk=hub.pk).exists()
    assert told == [hub.id]


def test_a_preparation_leaves_no_connection_open_to_the_database_it_made(registry, told):
    """Each hub's migrator connection and its own are closed when its preparation ends, not at
    the end of the worker's pass (twenty hubs a pass would hold twenty, and a demo's DROP would have to force them)."""
    hub = registry.hub()

    assert provision.provision(hub) is True

    hubs.assert_nobody_on(hub.db_name)


def test_a_failed_preparation_leaves_no_connection_open_either(registry, monkeypatch, told):
    hub = registry.hub()

    def broken(*args, **kwargs):
        raise RuntimeError("the migrator broke")

    monkeypatch.setattr(provision.migrator.schema, "migrate_apps", broken)

    assert provision.provision(hub) is False

    assert fresh(hub).status == "failed"
    hubs.assert_nobody_on(hub.db_name)


@contextmanager
def control_hears() -> Iterator[list[str]]:
    """The statements control's own connection runs meanwhile."""
    heard: list[str] = []

    def record(execute, sql, params, many, context):
        heard.append(sql)
        return execute(sql, params, many, context)

    with django_connections["default"].execute_wrapper(record):
        yield heard


def test_once_born_its_hub_reads_its_own_database_and_control_hears_none_of_its_business(registry, told):
    hub = registry.hub()
    provision.provision(hub)

    with control_hears() as heard, use_hub(fresh(hub)) as active:
        assert active.alias == tenancy_connections.hub_alias(hub)
        Location.objects.count()
        AppActivation.objects.count()

    assert not [sql for sql in heard if "base_location" in sql or "base_appactivation" in sql]
    # Its template carries no app turned on: it is born with only what its country requires that the platform turns
    # on by itself (Taxes), every other app off.
    with use_hub(fresh(hub)):
        assert set(AppActivation.objects.filter(state="on").values_list("app", flat=True)) == {"tax"}


def test_a_hub_already_ready_is_left_as_it_is(registry, monkeypatch, told):
    hub = registry.hub(status=Hub.Status.READY)
    cloned, written = [], []
    monkeypatch.setattr(ops, "clone_database", lambda *args, **kwargs: cloned.append(args))

    def record(execute, sql, params, many, context):
        if not sql.lstrip().upper().startswith("SELECT"):
            written.append(sql)
        return execute(sql, params, many, context)

    with django_connections["default"].execute_wrapper(record):
        assert provision.provision(hub) is True

    # Read once, nothing written: no lease taken, no row of hub_due made and dropped.
    assert cloned == [] and told == [] and written == []
    assert fresh(hub).status == "ready" and not HubDue.objects.filter(pk=hub.pk).exists()
    assert hub.db_name not in databases()


def test_a_preparation_cut_short_goes_on_from_where_it_was(registry, hub_databases, told):
    hub = registry.hub(status=Hub.Status.CREATING)
    ops.clone_database(hub.db_name, template=hub_databases.template)

    assert provision.provision(hub) is True

    assert fresh(hub).status == "ready"
    with use_hub(fresh(hub)):
        assert Location.objects.count() >= 0  # its identity was written: use_hub opened it


def test_a_missing_template_leaves_it_failed_with_a_readable_error_and_its_retry(registry, told):
    hub = registry.hub(vertical="nowhere")
    before = timezone.now()

    assert provision.provision(hub) is False

    hub = fresh(hub)
    due = HubDue.objects.get(pk=hub.pk)
    assert (hub.status, hub.attempts) == ("failed", 1)
    assert hub.last_error.startswith("template_missing: ") and "template_nowhere" in hub.last_error
    assert before + dt.timedelta(minutes=1) <= hub.next_attempt_at <= timezone.now() + dt.timedelta(minutes=1)
    assert (due.due_at, due.lease_until) == (hub.next_attempt_at, None)
    assert hub.db_name not in databases() and told == []


def test_each_failure_waits_longer_one_five_fifteen_minutes_then_every_hour():
    assert [services.provisioning.retry_delay(attempts) for attempts in range(1, 7)] == [
        dt.timedelta(minutes=1),
        dt.timedelta(minutes=5),
        dt.timedelta(minutes=15),
        dt.timedelta(hours=1),
        dt.timedelta(hours=1),
        dt.timedelta(hours=1),
    ]


def test_a_second_failure_waits_five_minutes(registry, told):
    hub = registry.hub(vertical="nowhere")
    provision.provision(hub)
    Hub.objects.filter(pk=hub.pk).update(next_attempt_at=timezone.now())
    before = timezone.now()

    provision.provision(hub)

    hub = fresh(hub)
    assert (hub.status, hub.attempts) == ("failed", 2)
    assert before + dt.timedelta(minutes=5) <= hub.next_attempt_at <= timezone.now() + dt.timedelta(minutes=5)


def test_a_hub_cancelled_while_it_is_made_stops_there_and_is_no_failure(registry, monkeypatch, told):
    hub = registry.hub()

    def cancelled_meanwhile(name, **kwargs):
        Hub.objects.filter(pk=hub.pk).update(status=Hub.Status.CANCELLED)
        return True

    monkeypatch.setattr(ops, "clone_database", cancelled_meanwhile)

    assert provision.provision(hub) is False

    hub = fresh(hub)
    assert (hub.status, hub.attempts, hub.last_error) == ("cancelled", 0, "")
    assert not HubDue.objects.filter(pk=hub.pk).exists() and told == []


def test_its_seeding_runs_inside_its_own_database(registry, monkeypatch, told):
    hub = registry.hub()
    seeded = []

    def seed(row):
        from base.tenancy.context import current

        seeded.append((row.pk, current().alias))

    monkeypatch.setattr(services.photo, "apply_kept_photo", seed)

    provision.provision(hub)

    assert seeded == [(hub.pk, tenancy_connections.hub_alias(hub))]


def test_the_people_of_the_photo_kept_while_it_was_prepared_are_in_its_database_when_it_is_born(registry, told):
    from base.models import HubUser

    owner, gone = uuid.uuid7(), uuid.uuid7()
    members = [{"user_id": str(owner), "role": "hub_owner", "email": "ana@example.com", "name": "Ana"}]
    hub = registry.hub(state={"members": members}, state_version=3)

    assert provision.provision(hub) is True

    with use_hub(fresh(hub)):
        ana = HubUser.objects.get(username=f"saas:{owner}")
        assert (ana.name, ana.email, ana.is_active) == ("Ana", "ana@example.com", True)
        # A preparation that goes on again (a retry) leaves out who the photo no longer lists.
        HubUser.objects.create(username=f"saas:{gone}", name="Gone", is_active=True)
        services.photo.apply_kept_photo(fresh(hub))
        assert not HubUser.objects.get(username=f"saas:{gone}").is_active


def test_a_photo_that_arrives_while_it_is_seeded_is_in_its_database_when_it_is_ready(registry, told):
    """The photo the SaaS sends between the seeding's read and ``ready`` is applied too; the
    SaaS never sends it again (its version is not newer than the one the row keeps)."""
    from live.context import system_context

    from base.models import HubUser
    from base.registry import REGISTRY_SCOPE
    from base.schemas.hub_registry import HubStateIn

    hub = registry.hub()
    late = uuid.uuid7()
    members = [{"user_id": str(late), "role": "hub_employee", "email": "luis@example.com", "name": "Luis"}]

    def photo_meanwhile(row):
        # The SaaS's photo, through its own door, while the seeding still runs: the hub is not ready, so it is kept.
        with use_control():
            services.hub_registry.hub_state_apply(
                system_context(REGISTRY_SCOPE),
                HubStateIn(id=row.id, version=7, members=members, photo={"members": members}),
            )

    assert provision.provision(hub, seed=photo_meanwhile) is True

    hub = fresh(hub)
    assert (hub.status, hub.state_version) == ("ready", 7)
    with use_hub(hub):
        assert HubUser.objects.filter(username=f"saas:{late}", is_active=True).exists()


def test_a_photo_that_keeps_changing_while_it_is_seeded_leaves_it_failed_and_tried_again(registry, monkeypatch, told):
    hub = registry.hub()
    asked = []
    monkeypatch.setattr(services.provisioning, "provision_ready", lambda *args, **kwargs: asked.append(kwargs) or None)

    before = timezone.now()
    assert provision.provision(hub) is False

    hub = fresh(hub)
    assert len(asked) == provision.SEED_ROUNDS
    assert hub.status == "failed" and hub.last_error.startswith("photo_moving: ")
    # Tried again after its wait, like any failed preparation: its next attempt and its due time are the same.
    assert hub.attempts == 1 and hub.next_attempt_at >= before + services.provisioning.retry_delay(1)
    assert HubDue.objects.get(pk=hub.pk).due_at == hub.next_attempt_at


def test_each_step_of_a_preparation_is_logged_with_how_long_it_took(registry, told, caplog, monkeypatch):
    """Each line says its own step's time, not the time since the start, and names the hub by its slug, as ``ready``
    does."""
    import re

    hub = registry.hub()
    # Started at 100; creating ends at 103, migrating at 110, seeding at 111, and ``ready`` reads 111.
    clock = iter([100.0, 103.0, 110.0, 111.0, 111.0])
    monkeypatch.setattr(provision, "time", SimpleNamespace(monotonic=lambda: next(clock)))

    with caplog.at_level(logging.INFO, logger="base.tenancy.provision"):
        assert provision.provision(hub) is True

    steps = re.findall(r"base\.tenancy\.provision\.step hub=(\S+) step=(\w+) seconds=(\S+)", caplog.text)
    assert steps == [(hub.slug, "creating", "3.00"), (hub.slug, "migrating", "7.00"), (hub.slug, "seeding", "1.00")]
    assert f"base.tenancy.provision.ready hub={hub.slug} database={fresh(hub).db_name} seconds=11.00" in caplog.text


@pytest.mark.django_db
def test_a_hub_without_a_name_for_its_database_fails_readably_and_nothing_reaches_control(told):
    hub = Hub.objects.create(slug="nameless", status=Hub.Status.REQUESTED, vertical=hubs.TEMPLATE_VERTICAL)

    assert provision.provision(hub) is False

    hub.refresh_from_db()
    assert (hub.status, hub.attempts) == ("failed", 1)
    assert hub.last_error.startswith("unexpected: InvalidDatabaseName: ")
    assert told == []
