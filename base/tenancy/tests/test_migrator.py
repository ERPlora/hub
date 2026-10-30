"""``ensure_schema`` and the templates: the only code that changes a hub's schema (PLAN-DB §7; plan
2026-10-22-fase-2-tenencia, S3; PLAN-DB round 2026-10-30, proposals (g) and (h)).

A test that migrates makes a database of its own, empty and named as one of this session's control database's
(``base.tenancy.names``), and drops it after; the session's hubs A and B (``hubs.py``) are only read. The migrator
registers its ``<db_name>__ddl`` alias as it goes, which a Django test case refuses (an alias in the settings and not
in its ``databases``), so these tests run without one, on the committed test database (``hubs.committed_database``,
as ``db``): the rows they write in control are deleted after each (``make_hub``).
"""

import re
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest
from django.db import connections
from django.db.backends.signals import connection_created
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader

from base import catalog
from base.models import AppActivation
from base.tenancy import connections as tenancy_connections
from base.tenancy import migrator, names
from base.tenancy.bootstrap import admin_conninfo as bootstrap_conninfo
from base.tenancy.tests import hubs
from base.tenancy.tests.hubs import (  # noqa: F401 (fixtures)
    committed_database,
    make_cluster,
    make_database,
    make_hub,
    new_database,
    opened_at,
    same_server_by_another_name,
    template_name,
)
from control.models import Hub

WAIT = 120
PLATFORM = ("base", "live")


def leaves() -> dict[str, str]:
    """``{label: its leaf migration}`` in the code."""
    return dict(MigrationLoader(None, ignore_no_migrations=True).graph.leaf_nodes())


def control() -> str:
    return tenancy_connections.control_name()


def sessions_on(name: str) -> int:
    with hubs._maintenance() as conn:
        return conn.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s", [name]).fetchone()[0]


def database_oid(name: str) -> int | None:
    with hubs._maintenance() as conn:
        row = conn.execute("SELECT oid FROM pg_database WHERE datname = %s", [name]).fetchone()
    return None if row is None else row[0]


def rows(name: str, table: str) -> int:
    with hubs._maintenance(name) as conn:
        query = psycopg.sql.SQL("SELECT count(*) FROM {}").format(psycopg.sql.Identifier(table))
        return conn.execute(query).fetchone()[0]


def tables_of(apps) -> set[str]:
    return hubs.hub_tables(apps) | {"django_migrations"}


def migrate_to(db_name: str, node: tuple[str, str]) -> None:
    """Bring the database ``db_name`` to the migration ``node``, as an older code would have left it."""
    alias = tenancy_connections.register_ddl_alias(db_name)
    try:
        MigrationExecutor(connections[alias]).migrate([node])
    finally:
        connections[alias].close()


@pytest.fixture
def opened():
    """The databases every connection opened during the test reached (Django's ``connection_created``)."""
    names_opened: list[str] = []

    def record(sender, connection, **kwargs):
        names_opened.append(connection.settings_dict["NAME"])

    connection_created.connect(record)
    yield names_opened
    connection_created.disconnect(record)


# ── What a hub's database may hold ──────────────────────────────────────────────────────────────────────────────


def test_the_platform_is_what_every_hubs_database_has():
    assert set(migrator.platform_apps()) == set(PLATFORM)


def test_the_apps_linked_to_controls_users_cannot_live_in_a_hubs_database_yet():
    """PLAN-DB round 2026-10-22 «Tests»: their tables reference control's user until the hub's own staff comes."""
    portable = set(migrator.portable_apps())

    assert {*PLATFORM, "tax", "inventory", "sale"} <= portable
    assert not {"staff", "attendance", "task", "whatsapp_inbox"} & portable


def test_the_templates_are_the_platforms_and_one_per_vertical_cloned_from_it():
    """Proposal (h): ``hub_template_<vertical>`` = ``hub_template`` + the tables of ``template_apps(vertical)``."""
    platform, *verticals = migrator.templates()
    portable = set(migrator.portable_apps())

    assert platform == migrator.Template(db_name=names.template_db_name(control()), apps=PLATFORM)
    assert [template.db_name for template in verticals] == [
        names.template_db_name(control(), vertical) for vertical in catalog.known_verticals()
    ]
    for vertical, template in zip(catalog.known_verticals(), verticals, strict=True):
        wanted = set(catalog.template_apps(vertical))
        assert template.source == platform.db_name
        assert set(template.apps) == set(PLATFORM) | (wanted & portable)
        assert set(template.left_out) == wanted - portable


# ── Clusters: CREATE DATABASE … TEMPLATE clones only within a server, so each has its templates ─────────────────


def test_without_clusters_only_the_settings_own_server_is_migrated(db):
    settings = connections.settings["default"]

    assert migrator.clusters_to_migrate() == [
        migrator.ClusterTarget(
            name="",
            host=settings["HOST"],
            port=int(settings["PORT"]),
            migrator_user=settings["USER"],
            migrator_password=settings["PASSWORD"],
            control=control(),
        )
    ]


def test_the_open_clusters_and_the_closed_ones_with_hubs_are_migrated_through_their_writer(make_cluster, make_hub):
    opened_one = make_cluster("open", host="writer.open.internal", port=5433)
    closed_with_hubs = make_cluster("closed-with-hubs", is_open=False)
    make_hub(names.hub_db_name(control(), uuid.uuid7()), cluster=closed_with_hubs)
    make_cluster("closed-empty", is_open=False)
    asked = []

    def credentials(cluster):
        asked.append(cluster.name)
        return f"migrator-{cluster.name}", "its-secret"

    targets = migrator.clusters_to_migrate(credentials=credentials)

    assert [target.name for target in targets] == sorted([opened_one.name, closed_with_hubs.name])
    assert sorted(asked) == sorted([opened_one.name, closed_with_hubs.name])
    target = next(target for target in targets if target.name == opened_one.name)
    assert target == migrator.ClusterTarget(
        name=opened_one.name,
        host="writer.open.internal",
        port=5433,
        migrator_user=f"migrator-{opened_one.name}",
        migrator_password="its-secret",
        control=control(),
        cluster_id=opened_one.id,
    )
    assert "its-secret" not in repr(target)  # never in a log or a test's report


def test_without_the_migrators_credentials_it_refuses_never_falling_back_to_defaults(settings, monkeypatch):
    """The web's and the worker's ``default`` is ``hub_app``: the migrator never runs as it (review of hub#469)."""
    settings.DEBUG = False
    monkeypatch.setenv("DB_MIGRATOR_USER", "")
    monkeypatch.setenv("DB_MIGRATOR_PASSWORD", "")

    with pytest.raises(migrator.MigratorCredentialsMissing, match="DB_MIGRATOR_USER") as raised:
        migrator.migrator_credentials(None)

    assert raised.value.code == "migrator_credentials_missing"


def test_the_migrators_credentials_come_from_the_environment(settings, monkeypatch):
    settings.DEBUG = False
    monkeypatch.setenv("DB_MIGRATOR_USER", "hub_migrator")
    monkeypatch.setenv("DB_MIGRATOR_PASSWORD", "its-password")

    assert migrator.migrator_credentials(None) == ("hub_migrator", "its-password")


def test_local_development_migrates_as_its_one_role(settings, monkeypatch):
    """``DEBUG`` (a developer's machine, compose's Postgres): one role does everything, as in db-bootstrap's local
    mode."""
    settings.DEBUG = True
    monkeypatch.setenv("DB_MIGRATOR_USER", "")
    monkeypatch.setenv("DB_MIGRATOR_PASSWORD", "")
    default = connections.settings["default"]

    assert migrator.migrator_credentials(None) == (default["USER"], default["PASSWORD"])


def test_the_settings_own_server_stays_while_a_hub_without_a_cluster_lives_on_it(make_cluster, make_hub):
    cluster = make_cluster("open")
    make_hub(names.hub_db_name(control(), uuid.uuid7()))  # on the settings' own server
    make_hub(names.hub_db_name(control(), uuid.uuid7()), cluster=cluster)

    assert [target.name for target in migrator.clusters_to_migrate()] == ["", cluster.name]


def test_a_template_is_made_on_the_server_it_is_asked_for(template_name, opened_at, monkeypatch):
    target = replace(migrator.clusters_to_migrate()[0], host=same_server_by_another_name())
    platform = migrator.Template(db_name=template_name(), apps=PLATFORM)
    hubs.bootstrap_template(platform.db_name)
    template = migrator.Template(db_name=template_name(), apps=PLATFORM, source=platform.db_name)
    ops_hosts = []
    connect = psycopg.connect

    def watched(*args, **kwargs):
        if kwargs.get("dbname") == migrator.OPS_DATABASE:
            ops_hosts.append(kwargs.get("host"))
        return connect(*args, **kwargs)

    monkeypatch.setattr(psycopg, "connect", watched)

    migrator.ensure_template(template, target=target)

    assert hubs.table_names(template.db_name) == tables_of(PLATFORM)
    assert ops_hosts and set(ops_hosts) == {target.host}  # CREATE DATABASE on that server
    assert {name for host, name in opened_at if host == target.host} == {template.db_name}
    assert not [name for host, name in opened_at if name == template.db_name and host != target.host]


def test_a_hub_on_a_cluster_is_migrated_through_that_clusters_writer(new_database, make_cluster, make_hub, opened_at):
    cluster = make_cluster("other-name", host=same_server_by_another_name())
    hub = make_hub(new_database, cluster=cluster)

    migrator.ensure_schema(hub)

    assert {host for host, name in opened_at if name == new_database} == {cluster.host}
    assert hubs.table_names(new_database) == tables_of(PLATFORM)


# ── ensure_schema ───────────────────────────────────────────────────────────────────────────────────────────────


def test_a_hub_without_its_own_database_is_refused_and_nothing_is_opened(make_hub, opened):
    hub = make_hub("")
    opened.clear()

    with pytest.raises(migrator.HubWithoutDatabase):
        migrator.ensure_schema(hub)

    assert opened == []


def test_a_new_database_gets_the_platform_at_the_codes_leaf_and_control_learns_it(new_database, make_hub):
    hub = make_hub(new_database, schema_state=Hub.SchemaState.BEHIND)
    leaf = leaves()

    applied = migrator.ensure_schema(hub)

    assert {f"base.{leaf['base']}", f"live.{leaf['live']}", "base.0001_initial"} <= set(applied)
    assert hubs.table_names(new_database) == tables_of(PLATFORM)
    hub.refresh_from_db()
    assert hub.schema_apps == {label: leaf[label] for label in PLATFORM}
    assert hub.schema_state == Hub.SchemaState.CURRENT


def test_a_second_run_applies_nothing(new_database, make_hub):
    hub = make_hub(new_database)
    migrator.ensure_schema(hub)
    first = Hub.objects.get(pk=hub.pk).schema_apps

    assert migrator.ensure_schema(hub) == []
    assert Hub.objects.get(pk=hub.pk).schema_apps == first


def test_add_creates_only_that_app_and_what_it_requires(new_database, make_hub):
    hub = make_hub(new_database)
    leaf = leaves()

    migrator.ensure_schema(hub, add=["inventory"])  # inventory requires tax

    assert hubs.table_names(new_database) == tables_of({*PLATFORM, "inventory", "tax"})
    hub.refresh_from_db()
    assert hub.schema_apps == {label: leaf[label] for label in (*PLATFORM, "inventory", "tax")}


def test_an_app_the_hubs_database_has_is_brought_to_the_leaf_even_if_control_never_learnt_it(new_database, make_hub):
    """«Si discrepan, manda el django_migrations de la BD del hub» (PLAN-DB §7)."""
    hub = make_hub(new_database)
    migrator.ensure_schema(hub)
    migrate_to(new_database, ("tax", "0001_initial"))  # created by an older code; control knows only the platform
    leaf = leaves()["tax"]

    applied = migrator.ensure_schema(hub)

    assert f"tax.{leaf}" in applied
    hub.refresh_from_db()
    assert hub.schema_apps == {**{label: leaves()[label] for label in PLATFORM}, "tax": leaf}


def test_an_app_the_code_no_longer_knows_stays_in_schema_apps(new_database, make_hub):
    """A rollback ignores the labels it does not know and forgets nothing (PLAN-DB §7, «Rollback»)."""
    hub = make_hub(new_database, schema_apps={"gone": "0009_later"})

    migrator.ensure_schema(hub)

    hub.refresh_from_db()
    assert hub.schema_apps["gone"] == "0009_later"


def test_add_refuses_an_app_that_cannot_live_in_a_hubs_database_yet(new_database, make_hub):
    hub = make_hub(new_database)

    with pytest.raises(migrator.AppNotPortable, match="staff"):
        migrator.ensure_schema(hub, add=["staff"])

    assert hubs.table_names(new_database) == set()


def test_add_refuses_an_app_the_code_does_not_have(new_database, make_hub):
    hub = make_hub(new_database)

    with pytest.raises(migrator.UnknownApp, match="nonexistent"):
        migrator.ensure_schema(hub, add=["nonexistent"])

    assert hubs.table_names(new_database) == set()


def test_the_migrator_runs_with_plan_db_session_limits(new_database, monkeypatch, make_hub):
    """PLAN-DB §7, «Conexión»: lock_timeout 5 s, statement_timeout and idle_in_transaction 5 min."""
    hub = make_hub(new_database)
    seen = {}
    real = migrator.migrate_apps

    def watching(alias, labels):
        with connections[alias].cursor() as cursor:
            for setting in ("lock_timeout", "statement_timeout", "idle_in_transaction_session_timeout"):
                cursor.execute(f"SHOW {setting}")
                seen[setting] = cursor.fetchone()[0]
        return real(alias, labels)

    monkeypatch.setattr(migrator, "migrate_apps", watching)

    migrator.ensure_schema(hub)

    assert seen == {
        "lock_timeout": "5s",
        "statement_timeout": "5min",
        "idle_in_transaction_session_timeout": "5min",
    }


def test_a_schema_lock_held_elsewhere_fails_after_the_wait_as_schema_locked(new_database, make_hub):
    hub = make_hub(new_database)

    with hubs._maintenance(new_database) as holder:
        holder.execute("SELECT pg_advisory_lock(hashtext('erplora.schema'))")
        started = time.monotonic()
        with pytest.raises(migrator.SchemaLocked) as raised:
            migrator.ensure_schema(hub, lock_wait=0.5)
        waited = time.monotonic() - started

    assert raised.value.code == "schema_locked"
    assert waited >= 0.5
    assert hubs.table_names(new_database) == set()
    hub.refresh_from_db()
    assert hub.schema_apps == {}


def test_a_failed_run_leaves_neither_the_lock_nor_the_connection(new_database, monkeypatch, make_hub):
    hub = make_hub(new_database)

    def broken(alias, labels):
        raise RuntimeError("the migration broke")

    monkeypatch.setattr(migrator, "migrate_apps", broken)

    with pytest.raises(RuntimeError, match="the migration broke"):
        migrator.ensure_schema(hub)

    assert sessions_on(new_database) == 0
    with hubs._maintenance(new_database) as other:
        assert other.execute("SELECT pg_try_advisory_lock(hashtext('erplora.schema'))").fetchone()[0]
    hub.refresh_from_db()
    assert hub.schema_apps == {}


def test_a_failed_run_reports_its_own_error_even_when_its_connection_died(new_database, make_hub, monkeypatch):
    hub = make_hub(new_database)

    def dying(alias, labels):
        connections[alias].connection.close()  # the server went away in the middle of the run
        raise RuntimeError("the migration broke")

    monkeypatch.setattr(migrator, "migrate_apps", dying)

    with pytest.raises(RuntimeError, match="the migration broke"):
        migrator.ensure_schema(hub)


def test_two_runs_on_one_hub_at_once_one_waits_and_neither_fails(new_database, monkeypatch, make_hub):
    """Without the schema lock both would create the same tables, and one would fail with 42P07."""
    hub = make_hub(new_database)
    real = migrator.migrate_apps
    guard = threading.Lock()
    inside = [0]
    peak = [0]

    def tracked(alias, labels):
        with guard:
            inside[0] += 1
            peak[0] = max(peak[0], inside[0])
        try:
            time.sleep(0.3)  # widens the window two unlocked runs would overlap in
            return real(alias, labels)
        finally:
            with guard:
                inside[0] -= 1

    monkeypatch.setattr(migrator, "migrate_apps", tracked)
    start = threading.Barrier(2)
    results: list[list[str]] = []
    errors: list[Exception] = []

    def run():
        try:
            start.wait(WAIT)
            results.append(migrator.ensure_schema(Hub.objects.get(pk=hub.pk)))
        except Exception as error:  # reported by the assertions below
            errors.append(error)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(WAIT)

    assert errors == []
    assert peak[0] == 1
    assert sorted(len(applied) > 0 for applied in results) == [False, True]


def test_ensure_schema_of_a_never_opens_bs_database(hub_databases, make_hub, opened):
    hub_a = make_hub(hub_databases.a, id=hubs.HUB_A_ID)

    assert migrator.ensure_schema(hub_a) == []  # a clone of the template, at the code's leaf

    assert hub_databases.a in opened
    assert hub_databases.b not in opened
    hub_a.refresh_from_db()
    assert set(hub_a.schema_apps) == set(hub_databases.apps)


# ── is_behind: whether migrate_hubs opens a hub at all ─────────────────────────────────────────────────────────


def test_a_hub_is_behind_when_an_app_it_has_is_not_at_the_codes_leaf():
    leaf = leaves()
    current = {label: leaf[label] for label in PLATFORM}

    assert not migrator.is_behind(Hub(schema_apps=current))
    assert migrator.is_behind(Hub(schema_apps={}))  # never confirmed
    assert migrator.is_behind(Hub(schema_apps={**current, "base": "0001_initial"}))
    assert migrator.is_behind(Hub(schema_apps={**current, "tax": "0001_initial"}))  # an older one of the code
    assert migrator.is_behind(Hub(schema_apps=current, schema_state=Hub.SchemaState.BEHIND))
    assert not migrator.is_behind(Hub(schema_apps={**current, "gone": "0009_later"}))  # a rollback's unknown label
    # A later code's migration (after a rollback): the database is ahead, not behind.
    assert not migrator.is_behind(Hub(schema_apps={**current, "base": "0099_from_a_later_code"}))


# ── Templates ───────────────────────────────────────────────────────────────────────────────────────────────────


def platform_and_vertical(template_name, apps=("tax",)) -> tuple[migrator.Template, migrator.Template]:
    """A platform's template as db-bootstrap leaves it, migrated, and a vertical's (not made yet) cloned from it."""
    platform = migrator.Template(db_name=template_name(), apps=PLATFORM)
    hubs.bootstrap_template(platform.db_name)
    migrator.ensure_template(platform)
    return platform, migrator.Template(db_name=template_name(), apps=(*PLATFORM, *apps), source=platform.db_name)


def test_a_missing_platform_template_is_refused_naming_its_server(template_name, make_cluster):
    """Only db-bootstrap makes a platform's template, with its roles, grants and default privileges (ruling of the
    review of hub#469): a plain one would let every role of the cluster in, and stay so."""
    template = migrator.Template(db_name=template_name(), apps=PLATFORM)
    cluster = make_cluster("second")
    on_cluster = migrator.cluster_target(cluster)

    with pytest.raises(migrator.TemplateMissing, match="db-bootstrap") as settings_own:
        migrator.ensure_template(template)
    with pytest.raises(migrator.TemplateMissing, match=f"cluster {cluster.name}"):
        migrator.ensure_template(template, target=on_cluster)

    assert "the settings' server" in str(settings_own.value)
    assert settings_own.value.code == "template_missing"
    assert database_oid(template.db_name) is None


def test_a_verticals_template_is_cloned_from_the_platforms_with_every_app_off(template_name):
    platform, vertical = platform_and_vertical(template_name)

    applied = migrator.ensure_template(vertical)

    assert applied and all(name.split(".")[0] not in PLATFORM for name in applied)  # the platform came cloned
    assert hubs.table_names(vertical.db_name) == tables_of(vertical.apps)
    assert rows(vertical.db_name, AppActivation._meta.db_table) == 0  # proposal (h): everything off
    assert sessions_on(platform.db_name) == sessions_on(vertical.db_name) == 0  # nobody connected: both clonable


def test_a_verticals_template_gets_its_platforms_access_never_publics(template_name):
    """``CREATE DATABASE … TEMPLATE`` copies no grant of the database: PUBLIC would connect to the new one."""
    platform, vertical = platform_and_vertical(template_name)

    migrator.ensure_template(vertical)

    assert hubs.database_access(vertical.db_name) == hubs.database_access(platform.db_name)
    with hubs._maintenance() as conn:
        allowed = conn.execute(
            "SELECT has_database_privilege(%s, %s, 'CONNECT'), has_database_privilege(%s, %s, 'CONNECT')",
            ["pg_read_all_settings", vertical.db_name, hubs.TEMPLATE_GRANTEE, vertical.db_name],
        ).fetchone()
    assert allowed == (False, True)


def test_a_verticals_template_made_open_before_is_closed_on_the_next_run(template_name):
    platform, vertical = platform_and_vertical(template_name)
    with hubs._maintenance() as conn:  # as a template made before this fix: PUBLIC's default access, nobody else's
        conn.execute(
            psycopg.sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                psycopg.sql.Identifier(vertical.db_name), psycopg.sql.Identifier(platform.db_name)
            )
        )
        conn.execute(
            psycopg.sql.SQL("GRANT CREATE ON DATABASE {} TO pg_read_all_settings").format(
                psycopg.sql.Identifier(vertical.db_name)
            )
        )

    migrator.ensure_template(vertical)

    assert hubs.database_access(vertical.db_name) == hubs.database_access(platform.db_name)


def test_a_clone_waits_for_whoever_holds_its_source_a_bounded_number_of_times(template_name, monkeypatch):
    """55006 («source database … is being accessed by other users», PLAN-DB §6): PostgreSQL itself waits 5 s."""
    platform, vertical = platform_and_vertical(template_name)
    monkeypatch.setattr(migrator, "CLONE_RETRY_DELAY", 0.2)
    holder = psycopg.connect(**(bootstrap_conninfo() | {"dbname": platform.db_name}), autocommit=True)
    releaser = threading.Timer(6.5, holder.close)  # past the 5 s of PostgreSQL's own wait: one failed attempt
    releaser.start()
    try:
        migrator.ensure_template(vertical)
    finally:
        releaser.cancel()
        holder.close()

    assert hubs.table_names(vertical.db_name) == tables_of(vertical.apps)


def test_a_clone_gives_up_after_its_attempts(template_name, monkeypatch):
    platform, vertical = platform_and_vertical(template_name)
    monkeypatch.setattr(migrator, "CLONE_ATTEMPTS", 2)
    monkeypatch.setattr(migrator, "CLONE_RETRY_DELAY", 0)
    attempts = []
    real = migrator._clone_once

    def counted(*args, **kwargs):
        attempts.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(migrator, "_clone_once", counted)
    with psycopg.connect(**(bootstrap_conninfo() | {"dbname": platform.db_name}), autocommit=True):
        with pytest.raises(psycopg.errors.ObjectInUse):
            migrator.ensure_template(vertical)

    assert len(attempts) == 2
    assert database_oid(vertical.db_name) is None


def test_a_template_whose_list_changed_is_brought_up_to_date_never_rebuilt(template_name):
    name = template_name()
    hubs.create_database(name)
    migrator.ensure_template(migrator.Template(db_name=name, apps=(*PLATFORM, "tax")))
    oid = database_oid(name)

    # tax left the vertical's list and customer joined it.
    applied = migrator.ensure_template(migrator.Template(db_name=name, apps=(*PLATFORM, "customer")))

    assert {migration.split(".")[0] for migration in applied} == {"customer"}
    assert database_oid(name) == oid
    assert hubs.table_names(name) == tables_of({*PLATFORM, "tax", "customer"})


def test_an_app_that_left_a_templates_list_is_still_brought_to_the_leaf(template_name):
    name = template_name()
    hubs.create_database(name)
    migrator.ensure_template(migrator.Template(db_name=name, apps=PLATFORM))
    migrate_to(name, ("tax", "0001_initial"))  # on an older list, at an older code

    applied = migrator.ensure_template(migrator.Template(db_name=name, apps=PLATFORM))

    assert f"tax.{leaves()['tax']}" in applied


def test_a_template_another_run_created_meanwhile_is_migrated_not_refused(template_name, monkeypatch):
    """Two overlapping deploys may both find it missing: the second clone (42P04) is not a failure."""
    platform, vertical = platform_and_vertical(template_name)
    hubs.create_database(vertical.db_name)
    exists = migrator.database_exists
    monkeypatch.setattr(
        migrator, "database_exists", lambda name, **kwargs: False if name == vertical.db_name else exists(name, **kwargs)
    )

    assert "base.0001_initial" in migrator.ensure_template(vertical)
    assert hubs.table_names(vertical.db_name) == tables_of(vertical.apps)


def test_pending_lists_what_a_template_lacks_and_applies_nothing(template_name):
    template = migrator.Template(db_name=template_name(), apps=(*PLATFORM, "tax"))
    hubs.create_database(template.db_name)
    migrator.ensure_template(template)
    leaf = leaves()["tax"]
    with hubs._maintenance(template.db_name) as conn:  # as if the code had just gained tax's leaf
        conn.execute("DELETE FROM django_migrations WHERE app = 'tax' AND name = %s", [leaf])

    assert migrator.pending_template(template) == [f"tax.{leaf}"]
    assert migrator.pending_template(template) == [f"tax.{leaf}"]
    assert sessions_on(template.db_name) == 0


def test_pending_of_a_missing_template_is_what_making_it_applies_and_creates_nothing(template_name):
    template = migrator.Template(db_name=template_name(), apps=PLATFORM)
    leaf = leaves()

    pending = migrator.pending_template(template)

    assert {"base.0001_initial", f"base.{leaf['base']}", f"live.{leaf['live']}"} <= set(pending)
    assert database_oid(template.db_name) is None


def test_the_migrator_leaves_no_alias_of_its_own_registered(template_name, new_database, make_hub):
    """Each ``__ddl`` alias is forgotten once used: one left in the settings breaks every later test case, and in a
    long process every hub would leave one."""
    platform, vertical = platform_and_vertical(template_name)
    migrator.ensure_template(vertical)
    migrator.pending_template(vertical)
    migrator.ensure_schema(make_hub(new_database))

    assert [alias for alias in connections.settings if alias.endswith(names.DDL_SUFFIX)] == []


def test_the_migrator_never_drops_anything():
    """Tables are never deleted, and a template is brought up to date, never rebuilt (plan 2026-10-30, W2b)."""
    root = Path(__file__).resolve().parents[3]
    for path in ("base/tenancy/migrator.py", "base/management/commands/migrate_hubs.py"):
        assert re.search(r"\bDROP\b", (root / path).read_text()) is None, path
