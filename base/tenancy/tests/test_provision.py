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
import threading
import uuid
from pathlib import Path

import pytest
from django.db import connections as django_connections
from django.utils import timezone
from live.models import OutboxEvent

from base import services
from base.models import AppActivation, Location
from base.tenancy import connections as tenancy_connections
from base.tenancy import identity, names, ops, provision
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


@pytest.fixture(autouse=True)
def on_the_tests_control_database(settings):
    """These tests make and drop real databases next to control's: only ever the tests' own. pytest-django sets the
    test databases up only when the session has a ``django_db`` test (this module has one); without it control would
    still be the developer's database."""
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
    expected = provision.schema_leaves({"base", "live", *hub_databases.apps})
    assert (hub.status, hub.attempts, hub.last_error, hub.next_attempt_at) == ("ready", 0, "", None)
    assert hub.ready_at is not None and hub.schema_state == "current"
    assert hub.schema_apps == expected
    assert hub.db_name in databases()
    assert hubs.table_names(hub.db_name) == hubs.table_names(hub_databases.template)
    assert not HubDue.objects.filter(pk=hub.pk).exists()
    assert told == [hub.id]


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


def test_a_hub_already_ready_is_left_as_it_is(registry, monkeypatch, told):
    hub = registry.hub(status=Hub.Status.READY)
    cloned = []
    monkeypatch.setattr(ops, "clone_database", lambda *args, **kwargs: cloned.append(args))

    assert provision.provision(hub) is True

    assert cloned == [] and told == []
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


# ── Guardrail (round 2026-10-30, proposal (c)): no new hub is ever born sharing control's database ──────────────────

#: The ``Hub.objects.create`` calls of ``base/services.py`` that may leave ``db_name`` empty, each with its reason.
SHARED_HUB_CREATES = {
    "hub_seed_local": (
        "the local hubs a and b of a developer's database keep sharing it until the apps whose tables refer to "
        "control's users (staff, attendance, task, whatsapp_inbox and what needs them) can live in a hub's own "
        "database (W2a report, 2026-10-30)."
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
