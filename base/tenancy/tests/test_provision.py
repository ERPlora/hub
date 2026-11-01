"""A hub's database made at sign-up and a demo's dropped when it ends (round 2026-10-30 of PLAN-DB, S2a; PLAN-DB §6).

``base.tenancy.provision`` takes a hub ``requested`` through ``creating`` (its database cloned from its vertical's
template on its cluster, private, with its identity), ``migrating`` (the clone brought to the code's leaf, its
``schema_apps`` noted) and ``seeding`` (the SaaS's photo kept on its row) to ``ready``, the SaaS told; a step that
fails leaves it ``failed`` with a readable error and its next attempt, never an exception. Whoever works on a hub holds
its ``hub_due`` lease: two at once make one database. A new hub goes to the open cluster with the fewest hubs under its
limit, or to the settings' own server when there are no clusters. A demo's database is dropped alone when it ends.

These tests make real databases next to the session's (``base/tenancy/tests/hubs.py``), so they run outside a test
case (``django_db_blocker``; Django's test case only lets a test reach the aliases it names) and clean up after
themselves: the rows they wrote in control and the databases they made.
"""

import ast
import datetime as dt
import logging
import threading
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from psycopg import sql
from django.db import connections as django_connections
from django.db.migrations.loader import MigrationLoader
from django.utils import timezone
from live.models import OutboxEvent

from base import services
from base.models import AppActivation, Location
from base.tenancy import connections as tenancy_connections
from base.tenancy import identity, migrator, names, ops, provision
from base.tenancy.context import use_control, use_hub
from base.tenancy.tests import hubs
from control.models import Cluster, Hub, HubDue

pytestmark = pytest.mark.usefixtures("no_test_fallback")

HUB_DIR = Path(__file__).resolve().parents[3]


def databases() -> set[str]:
    """The databases of this session's control database (other sessions make and drop theirs meanwhile)."""
    control = tenancy_connections.control_name()
    with hubs._maintenance() as conn:
        return {row[0] for row in conn.execute("SELECT datname FROM pg_database") if row[0].startswith(control)}


@pytest.fixture(autouse=True, scope="session")
def on_the_tests_control_database(django_db_setup):
    """These tests make and drop real databases next to control's: only ever the tests' own. pytest-django sets the
    test databases up only when the session has a ``django_db`` test (this module has one); without it control would
    still be the developer's database, and ``hub_databases`` would make and drop its templates there. Session-scoped
    and autouse, it runs before ``hub_databases`` builds anything."""
    from django.conf import settings

    control = tenancy_connections.control_name()
    if not control.startswith(settings.DATABASES["default"]["TEST"]["NAME"]):
        pytest.fail(f"The control database is {control!r}, not the tests': run this module whole, not one test of it.")


@pytest.fixture(autouse=True)
def nothing_checked_yet(monkeypatch):
    monkeypatch.setattr(identity, "_verified", set())


@pytest.fixture
def told(monkeypatch):
    """The SaaS's ``ready`` notices (``services.report_ready``), recorded instead of sent."""
    heard: list[uuid.UUID] = []
    monkeypatch.setattr(services, "report_ready", heard.append)
    return heard


@pytest.fixture
def registry(django_db_blocker, hub_databases):
    """Rows of control this test writes (committed: no test case here), deleted after it with their databases."""
    started = timezone.now()
    made: list[Hub] = []
    clusters: list[Cluster] = []

    def hub(*, demo: bool = False, vertical: str = hubs.TEMPLATE_VERTICAL, **fields) -> Hub:
        hub_id = uuid.uuid7()
        control = tenancy_connections.control_name()
        build = names.demo_db_name if demo else names.hub_db_name
        values = {
            "id": hub_id,
            "slug": f"{'demo-' if demo else 'acme-'}{hub_id.hex[-8:]}",
            "status": Hub.Status.REQUESTED,
            "db_name": build(control, hub_id),
            "vertical": vertical,
            "is_demo": demo,
            "expires_at": timezone.now() + dt.timedelta(hours=1) if demo else None,
        }
        made.append(row := Hub.objects.create(**(values | fields)))
        return row

    def cluster(name: str, **fields) -> Cluster:
        default = django_connections.settings["default"]
        values = {"host": default["HOST"], "port": default["PORT"], "pooler_host": ""}
        clusters.append(row := Cluster.objects.create(name=name, **(values | fields)))
        return row

    with django_db_blocker.unblock():
        yield SimpleRegistry(hub=hub, cluster=cluster)
        with hubs._maintenance() as conn:
            for row in made:
                if row.db_name:
                    hubs._drop(conn, row.db_name, hub_databases.control)
        Hub.objects.filter(pk__in=[row.pk for row in made]).delete()
        Cluster.objects.filter(pk__in=[row.pk for row in clusters]).delete()
        with use_control():
            OutboxEvent.objects.filter(created_at__gte=started).delete()


class SimpleRegistry:
    def __init__(self, *, hub, cluster):
        self.hub, self.cluster = hub, cluster


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


def connected_to(name: str) -> int:
    """How many sessions the server has open on the database ``name``."""
    with hubs._maintenance() as conn:
        return conn.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s", [name]).fetchone()[0]


def test_a_preparation_leaves_no_connection_open_to_the_database_it_made(registry, told):
    """Review of hub#471 (I1): each hub's migrator connection and its own are closed when its preparation ends, not at
    the end of the worker's pass (twenty hubs a pass would hold twenty, and a demo's DROP would have to force them)."""
    hub = registry.hub()

    assert provision.provision(hub) is True

    assert connected_to(hub.db_name) == 0


def test_a_failed_preparation_leaves_no_connection_open_either(registry, monkeypatch, told):
    hub = registry.hub()

    def broken(*args, **kwargs):
        raise RuntimeError("the migrator broke")

    monkeypatch.setattr(provision.migrator, "migrate_apps", broken)

    assert provision.provision(hub) is False

    assert fresh(hub).status == "failed" and connected_to(hub.db_name) == 0


def test_once_born_its_hub_reads_its_own_database_and_control_hears_none_of_its_business(registry, told):
    hub = registry.hub()
    provision.provision(hub)
    heard: list[str] = []

    def record(execute, sql, params, many, context):
        heard.append(sql)
        return execute(sql, params, many, context)

    with django_connections["default"].execute_wrapper(record), use_hub(fresh(hub)) as active:
        assert active.alias == tenancy_connections.hub_alias(hub)
        Location.objects.count()
        AppActivation.objects.count()

    assert not [sql for sql in heard if "base_location" in sql or "base_appactivation" in sql]
    # Born with every app off (PLAN §33): its template carries no app turned on.
    with use_hub(fresh(hub)):
        assert AppActivation.objects.count() == 0


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
    assert [services.retry_delay(attempts) for attempts in range(1, 7)] == [
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


def test_a_new_hub_goes_to_the_open_cluster_with_the_fewest_hubs_under_its_limit(registry, hub_databases, told):
    busy = registry.cluster("busy")
    roomy = registry.cluster("roomy", max_hubs=1)
    registry.cluster("closed", is_open=False)
    for _ in range(2):
        registry.hub(status=Hub.Status.READY, db_name="", cluster=busy)
    hub = registry.hub()

    assert provision.provision(hub) is True

    hub = fresh(hub)
    assert (hub.status, hub.cluster) == ("ready", roomy)
    # The template its database was cloned from is that cluster's own (here, the same local server).
    assert hubs.table_names(hub.db_name) == hubs.table_names(hub_databases.template)
    with use_hub(hub) as active:
        assert django_connections.settings[active.alias]["HOST"] == roomy.host
        assert Location.objects.count() >= 0


def test_a_full_or_closed_cluster_never_takes_a_new_hub_nor_does_the_settings_server(registry, told):
    full = registry.cluster("full", max_hubs=1)
    registry.cluster("closed", is_open=False)
    registry.hub(status=Hub.Status.READY, db_name="", cluster=full)
    hub = registry.hub()

    assert provision.provision(hub) is False

    hub = fresh(hub)
    assert (hub.status, hub.cluster, hub.attempts) == ("failed", None, 1)
    assert hub.last_error.startswith("no_cluster_available: ")
    assert hub.db_name not in databases()


def test_a_hub_on_its_way_to_a_cluster_takes_its_place_there(registry, told):
    # A hub moving to a cluster (control.hub.move) counts against its limit, as it will be on it in a moment.
    full = registry.cluster("full", max_hubs=1)
    registry.hub(status=Hub.Status.READY, db_name="", moving_to=full)
    hub = registry.hub()

    assert provision.provision(hub) is False

    hub = fresh(hub)
    assert (hub.status, hub.cluster) == ("failed", None)
    assert hub.last_error.startswith("no_cluster_available: ")


def test_a_purged_hub_frees_its_place_on_a_cluster(registry, told):
    small = registry.cluster("small", max_hubs=1)
    registry.hub(status=Hub.Status.PURGED, db_name="", cluster=small)
    hub = registry.hub()

    services.place_hub(hub.pk)

    assert fresh(hub).cluster == small


def test_a_demo_is_born_with_its_database_and_dropped_alone_when_it_ends(registry, told):
    demo = registry.hub(demo=True)
    assert demo.db_name == names.demo_db_name(tenancy_connections.control_name(), demo.id)
    assert provision.provision(demo) is True
    assert fresh(demo).status == "ready" and told == []  # a demo's SaaS asks; it is not told
    Hub.objects.filter(pk=demo.pk).update(expires_at=timezone.now() - dt.timedelta(minutes=1))
    before = databases()

    assert services.reap_demos() == 1

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

    assert services.reap_demos() == 1

    assert seen == [(demo.db_name, False, "dropping")]
    assert fresh(demo).status == "purged"


def test_a_demo_that_ends_while_it_is_made_is_dropped_not_finished(registry, told):
    demo = registry.hub(demo=True, status=Hub.Status.CREATING, expires_at=timezone.now() - dt.timedelta(minutes=1))
    HubDue.mark_due(demo)

    assert provision.run_due() == 1

    assert fresh(demo).status == "purged" and demo.db_name not in databases()
    assert not HubDue.objects.filter(pk=demo.pk).exists()


def test_the_due_pass_prepares_what_is_due_and_leaves_what_waits_for_its_retry(registry, told):
    due = registry.hub()
    later = timezone.now() + dt.timedelta(minutes=5)
    waiting = registry.hub(status=Hub.Status.FAILED, attempts=1, next_attempt_at=later)
    HubDue.mark_due(due)
    HubDue.mark_due(waiting, later)

    assert provision.run_due() == 1

    assert fresh(due).status == "ready" and fresh(waiting).status == "failed"
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


def test_its_seeding_runs_inside_its_own_database(registry, monkeypatch, told):
    hub = registry.hub()
    seeded = []

    def seed(row):
        from base.tenancy.context import current

        seeded.append((row.pk, current().alias))

    monkeypatch.setattr(services, "apply_kept_photo", seed)

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
        services.apply_kept_photo(fresh(hub))
        assert not HubUser.objects.get(username=f"saas:{gone}").is_active


def test_a_photo_that_arrives_while_it_is_seeded_is_in_its_database_when_it_is_ready(registry, told):
    """Review of round 4 (2): the photo the SaaS sends between the seeding's read and ``ready`` is applied too; the
    SaaS never sends it again (its version is not newer than the one the row keeps)."""
    from live.context import system_context

    from base.models import HubUser
    from base.registry import REGISTRY_SCOPE
    from base.schemas import HubStateIn

    hub = registry.hub()
    late = uuid.uuid7()
    members = [{"user_id": str(late), "role": "hub_employee", "email": "luis@example.com", "name": "Luis"}]

    def photo_meanwhile(row):
        # The SaaS's photo, through its own door, while the seeding still runs: the hub is not ready, so it is kept.
        with use_control():
            services.hub_state_apply(
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
    monkeypatch.setattr(services, "provision_ready", lambda *args, **kwargs: asked.append(kwargs) or None)

    before = timezone.now()
    assert provision.provision(hub) is False

    hub = fresh(hub)
    assert len(asked) == provision.SEED_ROUNDS
    assert hub.status == "failed" and hub.last_error.startswith("photo_moving: ")
    # Tried again after its wait, like any failed preparation: its next attempt and its due time are the same.
    assert hub.attempts == 1 and hub.next_attempt_at >= before + services.retry_delay(1)
    assert HubDue.objects.get(pk=hub.pk).due_at == hub.next_attempt_at


def test_its_lease_is_renewed_while_its_schema_is_migrated(registry, monkeypatch, told):
    hub = registry.hub()
    real = migrator.ensure_schema
    renewed = []

    def beating(row, **kwargs):
        before = HubDue.objects.get(pk=row.pk).lease_until
        kwargs["heartbeat"]()
        renewed.append(HubDue.objects.get(pk=row.pk).lease_until > before)
        return real(row, **kwargs)

    monkeypatch.setattr(migrator, "ensure_schema", beating)

    assert provision.provision(hub) is True
    assert renewed == [True]


def test_a_lease_lost_while_its_schema_is_migrated_stops_it_there_without_failing_it(
    registry, monkeypatch, told, caplog
):
    hub = registry.hub()

    def taken_meanwhile(row, **kwargs):
        HubDue.objects.filter(pk=row.pk).update(lease_owner="another-worker")
        kwargs["heartbeat"]()

    monkeypatch.setattr(migrator, "ensure_schema", taken_meanwhile)

    with caplog.at_level(logging.INFO, logger="base.tenancy.provision"):
        assert provision.provision(hub) is False

    hub = fresh(hub)
    assert (hub.status, hub.attempts, hub.last_error) == ("migrating", 0, "")
    # Said as what it is: another worker holds it now, nothing failed.
    assert "provision.stopped" in caplog.text and "provision.failed" not in caplog.text


def test_each_step_of_a_preparation_is_logged_with_how_long_it_took(registry, told, caplog, monkeypatch):
    """Verification of hub#471 in pre: only ready/failed were logged, and each step's time had to be guessed. Each
    line says its own step's time, not the time since the start, and names the hub by its slug, as ``ready`` does."""
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


def test_a_hub_held_by_another_worker_is_not_taken(registry, told):
    hub = registry.hub()
    now = timezone.now()
    HubDue.mark_due(hub, now)
    HubDue.objects.filter(pk=hub.pk).update(lease_until=now + dt.timedelta(seconds=60))

    assert provision.run_due(now) == 0
    assert provision.provision(hub, now=now) is False

    assert fresh(hub).status == "requested" and hub.db_name not in databases()


@pytest.mark.django_db
def test_a_hub_without_a_name_for_its_database_fails_readably_and_nothing_reaches_control(told):
    hub = Hub.objects.create(slug="nameless", status=Hub.Status.REQUESTED, vertical=hubs.TEMPLATE_VERTICAL)

    assert provision.provision(hub) is False

    hub.refresh_from_db()
    assert (hub.status, hub.attempts) == ("failed", 1)
    assert hub.last_error.startswith("unexpected: InvalidDatabaseName: ")
    assert told == []


# ── The lease is its holder's (review of hub#471, I2) ──────────────────────────────────────────────────────────────


def test_a_lease_another_worker_took_over_once_it_expired_is_never_touched_by_its_first_holder(registry, told):
    hub = registry.hub()
    now = timezone.now()
    assert services.claim_hub(hub.pk, now, provision.LEASE, owner="worker-1") is not None
    later = now + provision.LEASE + dt.timedelta(seconds=1)
    assert services.claim_hub(hub.pk, later, provision.LEASE, owner="worker-2") is not None

    with pytest.raises(services.ProvisioningStopped, match="lease"):
        services.provision_step(hub.pk, Hub.Status.CREATING, later, provision.LEASE, owner="worker-1")
    assert services.provision_failed(hub.pk, later, "too late", owner="worker-1") is None
    services.release_hub(hub.pk, later, owner="worker-1")

    due = HubDue.objects.get(pk=hub.pk)
    assert (due.lease_owner, due.lease_until) == ("worker-2", later + provision.LEASE)
    assert (fresh(hub).status, fresh(hub).attempts) == ("requested", 0)


def test_a_lease_is_never_taken_while_its_holder_keeps_it(registry, told):
    hub = registry.hub()
    now = timezone.now()
    services.claim_hub(hub.pk, now, provision.LEASE, owner="worker-1")

    assert services.claim_hub(hub.pk, now + dt.timedelta(seconds=30), provision.LEASE, owner="worker-2") is None
    assert services.claim_next_due_hub(now + dt.timedelta(seconds=30), provision.LEASE, owner="worker-2") is None


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

    assert provision.run_due(now) == 2

    # While the first is worked on, the second is nobody's yet: its lease starts when its turn comes.
    assert seen[0] == (first.pk, "")


# ── More apps than the template's, and a/b's own databases once every app can have one (seed_local_hubs) ────────────


@pytest.fixture
def small_template(django_db_blocker, hub_databases):
    """``<control>_template_small``: ``base`` alone (and what it needs), built as the tests' template is."""
    control = hub_databases.control
    name = names.template_db_name(control, "small")
    with django_db_blocker.unblock():
        with hubs._maintenance() as conn:
            hubs._drop(conn, name, control)
            conn.execute(sql.SQL("CREATE DATABASE {}").format(names.identifier(name, control=control)))
        ddl = tenancy_connections.register_ddl_alias(name)
        try:
            migrator.migrate_apps(ddl, ["base"])
        finally:
            migrator._forget_alias(ddl)  # closed and out of the settings: Django's test case unwraps only its own
    yield name
    with hubs._maintenance() as conn:
        hubs._drop(conn, name, control)


def test_a_hub_may_get_more_apps_than_its_template_and_a_seed_inside_its_database(registry, small_template, told):
    hub = registry.hub(vertical="small")
    seeded = []

    def seed(row):
        from base.tenancy.context import current

        seeded.append(current().alias)

    assert not {table for table in hubs.table_names(small_template) if table.startswith("tax_")}
    assert provision.provision(hub, apps=["tax"], seed=seed) is True

    hub = fresh(hub)
    assert {table for table in hubs.table_names(hub.db_name) if table.startswith("tax_")}
    assert "tax" in hub.schema_apps and "base" in hub.schema_apps
    assert seeded == [tenancy_connections.hub_alias(hub)]


def _only_its_templates_apps_are_there(hub: Hub) -> None:
    """S3: a new hub has its template's tables and nothing more, every app off; an app's tables are made the first time
    it is turned on (``base.app.enable`` → the worker's ``ensure_schema``)."""
    hub = fresh(hub)
    assert hub.status == "ready"
    assert set(hub.schema_apps) == {"base", "live"}
    tables = hubs.table_names(hub.db_name)
    assert not {table for table in tables if table.startswith(("sale_", "customer_", "tax_"))}
    with use_hub(hub):
        assert not AppActivation.objects.filter(state="on").exists()


def test_a_new_hub_gets_only_its_templates_tables_every_app_off(registry, small_template, told):
    hub = registry.hub(vertical="small")
    assert not {table for table in hubs.table_names(small_template) if table.startswith("sale_")}

    assert provision.provision(hub) is True

    _only_its_templates_apps_are_there(hub)


def test_the_due_pass_gives_a_new_business_only_its_templates_tables(registry, small_template, told):
    hub = registry.hub(vertical="small")
    HubDue.mark_due(hub)

    assert provision.run_due() == 1

    _only_its_templates_apps_are_there(hub)


@pytest.fixture
def full_template(django_db_blocker, hub_databases):
    """``<control>_template_full``: built as ``migrate_hubs`` builds the platform's (``migrator.templates()[0].apps``)."""
    control = hub_databases.control
    name = names.template_db_name(control, "full")
    with django_db_blocker.unblock():
        with hubs._maintenance() as conn:
            hubs._drop(conn, name, control)
            conn.execute(sql.SQL("CREATE DATABASE {}").format(names.identifier(name, control=control)))
        ddl = tenancy_connections.register_ddl_alias(name)
        try:
            migrator.migrate_apps(ddl, migrator.templates()[0].apps)
        finally:
            migrator._forget_alias(ddl)  # closed and out of the settings: Django's test case unwraps only its own
    yield name
    with hubs._maintenance() as conn:
        hubs._drop(conn, name, control)


def test_a_sign_up_from_a_template_up_to_date_is_the_clone_alone(registry, full_template, monkeypatch, told):
    """Review of hub#471 in pre: ~63 s of migrations per sign-up on Fargate. The templates carry every portable app
    (``migrator.templates``), so a hub made from one migrates nothing: its sign-up is the clone."""
    hub = registry.hub(vertical="full")
    applied = []
    real = migrator.ensure_schema
    monkeypatch.setattr(migrator, "ensure_schema", lambda row, **kwargs: applied.append(real(row, **kwargs)) or applied[-1])

    assert provision.provision(hub) is True

    assert applied == [[]]
    assert set(migrator.portable_apps()) <= set(fresh(hub).schema_apps)


@pytest.fixture
def full_template(django_db_blocker, hub_databases):
    """``<control>_template_full``: built as ``migrate_hubs`` builds the platform's (``migrator.templates()[0].apps``)."""
    control = hub_databases.control
    name = names.template_db_name(control, "full")
    with django_db_blocker.unblock():
        with hubs._maintenance() as conn:
            hubs._drop(conn, name, control)
            conn.execute(sql.SQL("CREATE DATABASE {}").format(names.identifier(name, control=control)))
        ddl = tenancy_connections.register_ddl_alias(name)
        try:
            migrator.migrate_apps(ddl, migrator.templates()[0].apps)
        finally:
            migrator._forget_alias(ddl)  # closed and out of the settings: Django's test case unwraps only its own
    yield name
    with hubs._maintenance() as conn:
        hubs._drop(conn, name, control)


def test_a_sign_up_from_a_template_up_to_date_is_the_clone_alone(registry, full_template, monkeypatch, told):
    """Review of hub#471 in pre: ~63 s of migrations per sign-up on Fargate. The templates carry every portable app
    (``migrator.templates``), so a hub made from one migrates nothing: its sign-up is the clone."""
    hub = registry.hub(vertical="full")
    applied = []
    real = migrator.ensure_schema
    monkeypatch.setattr(migrator, "ensure_schema", lambda row, **kwargs: applied.append(real(row, **kwargs)) or applied[-1])

    assert provision.provision(hub) is True

    assert applied == [[]]
    assert set(migrator.portable_apps()) <= set(fresh(hub).schema_apps)


@pytest.fixture
def every_app_portable():
    """Every app a and b turn on can live in a hub's own database (since W10, hub#474)."""
    assert migrator.hub_apps() == frozenset(migrator.portable_apps())


@pytest.fixture
def plain_template(django_db_blocker, hub_databases):
    """``<control>_template`` (a hub with no vertical, as a and b), a copy of the tests' own."""
    control = hub_databases.control
    name = names.template_db_name(control)
    with hubs._maintenance() as conn:
        hubs._drop(conn, name, control)
        conn.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                names.identifier(name, control=control), names.identifier(hub_databases.template, control=control)
            )
        )
    yield name
    with hubs._maintenance() as conn:
        hubs._drop(conn, name, control)


def test_seed_local_hubs_gives_a_and_b_their_own_databases_once_every_app_can_live_in_one(
    django_db_blocker, settings, every_app_portable, plain_template, told
):
    from io import StringIO

    from django.core.management import call_command

    from base.models import AppActivation

    settings.DEBUG = True
    started = timezone.now()
    out = StringIO()
    with django_db_blocker.unblock():
        try:
            call_command("seed_local_hubs", stdout=out)
            local = {hub.slug: hub for hub in Hub.objects.filter(slug__in=["a", "b"])}
            assert sorted(local) == ["a", "b"]
            for hub in local.values():
                assert (hub.status, hub.db_name) == ("ready", names.hub_db_name(tenancy_connections.control_name(), hub.id))
                assert hub.db_name in databases()
                with use_hub(hub):
                    turned_on = set(AppActivation.objects.filter(host=hub.slug, state="on").values_list("app", flat=True))
                assert {label for label in migrator.portable_apps() if label not in ("base", "live")} <= turned_on
            assert "a: created (its own database)" in out.getvalue()
            # A second run leaves them as they are; one left cancelled is ready again, on the database it has.
            with use_hub(local["b"]):
                AppActivation.objects.filter(host="b", app="task").update(state="off")
            with use_hub(local["a"]):
                a_on = set(AppActivation.objects.filter(host="a", state="on").values_list("app", flat=True))
                AppActivation.objects.filter(host="a").delete()
            again = StringIO()
            call_command("seed_local_hubs", stdout=again)
            assert "a: already ready" in again.getvalue()
            # As one that shares control's: a local hub left with no app at all has every app on again; one that
            # turned some off keeps them off.
            with use_hub(local["a"]):
                assert set(AppActivation.objects.filter(host="a", state="on").values_list("app", flat=True)) == a_on
            with use_hub(local["b"]):
                assert AppActivation.objects.get(host="b", app="task").state == "off"
            Hub.objects.filter(slug="a").update(status=Hub.Status.CANCELLED)
            back = StringIO()
            call_command("seed_local_hubs", stdout=back)
            assert "a: ready again" in back.getvalue()
            assert (fresh(local["a"]).status, fresh(local["a"]).db_name) == ("ready", local["a"].db_name)
        finally:
            leftover = list(Hub.objects.filter(slug__in=["a", "b"]))
            with hubs._maintenance() as conn:
                for hub in leftover:
                    if hub.db_name:
                        hubs._drop(conn, hub.db_name, tenancy_connections.control_name())
            Hub.objects.filter(slug__in=["a", "b"]).delete()
            with use_control():
                OutboxEvent.objects.filter(created_at__gte=started).delete()
    assert told == []  # the local hubs are no business of the SaaS's


# ── Guardrail (round 2026-10-30, proposal (c)): no new hub is ever born sharing control's database ──────────────────

#: The ``Hub.objects.create`` calls of ``base/services.py`` that may leave ``db_name`` empty, each with its reason.
SHARED_HUB_CREATES = {
    "hub_seed_local": (
        "the local hubs a and b turn every app on: they share the developer's control database only while some app "
        "cannot live in a hub's own (provision.portable_apps: staff, attendance, task, whatsapp_inbox and what needs "
        "them refer to control's users); seed_local_hubs then asks own_database=True and they get theirs."
    ),
}


#: The manager's methods that make a row.
MAKERS = ("create", "get_or_create", "update_or_create")


def _on_hub_objects(node: ast.AST) -> bool:
    """Whether the chain ``node`` hangs from is ``Hub.objects…`` (``Hub.objects.select_for_update().create`` too)."""
    while isinstance(node, (ast.Attribute, ast.Call)):
        if isinstance(node, ast.Call):
            node = node.func
            continue
        if node.attr == "objects" and isinstance(node.value, ast.Name) and node.value.id == "Hub":
            return True
        node = node.value
    return False


def hub_creates(source: str) -> list[tuple[str, bool]]:
    """``(function, names db_name)`` for every row ``Hub.objects…create(…)`` makes in ``source``."""
    found = []
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in MAKERS
                and _on_hub_objects(node.func.value)
            ):
                keywords = {keyword.arg for keyword in node.keywords}
                defaults = next((kw.value for kw in node.keywords if kw.arg in ("defaults", "create_defaults")), None)
                if isinstance(defaults, ast.Dict):
                    keywords |= {key.value for key in defaults.keys if isinstance(key, ast.Constant)}
                found.append((function.name, "db_name" in keywords))
    return found


def test_the_scanner_sees_a_hub_made_with_and_without_its_database():
    source = (
        "def good(data):\n    Hub.objects.create(id=data.id, db_name=name)\n"
        "def bad(data):\n    Hub.objects.create(id=data.id)\n"
        "def seeded(slug):\n    Hub.objects.get_or_create(slug=slug, defaults={'db_name': name})\n"
        "def locked(slug):\n    Hub.objects.select_for_update().get_or_create(slug=slug)\n"
        "def other(slug):\n    Membership.objects.create(host=slug)\n"
    )

    assert hub_creates(source) == [("good", True), ("bad", False), ("seeded", True), ("locked", False)]


def test_every_hub_the_services_make_names_its_own_database_but_the_listed_ones():
    found = hub_creates((HUB_DIR / "base" / "services.py").read_text())

    assert {"hub_register", "demo_create", "hub_seed_local"} <= {function for function, _named in found}
    offenders = sorted({function for function, named in found if not named} - set(SHARED_HUB_CREATES))
    assert offenders == [], (
        "A new hub is born with its own database (round 2026-10-30 of PLAN-DB, decision 1): name its db_name "
        f"(base.tenancy.names) or list the call in SHARED_HUB_CREATES with its reason: {offenders}"
    )
