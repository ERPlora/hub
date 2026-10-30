"""``manage.py migrate_hubs``: what the ``hub-migrate`` task runs on every deploy (aws-next README; PLAN-DB §7).

Control (``base.tenancy.migrator.migrate_control``, its lock: ``test_migrator.py``), then the templates of every
server the hubs live on (``clusters_to_migrate``, ``ensure_template``), then every hub behind, each through its own
server (``ensure_schema``, ``base/tenancy/tests/test_migrator.py``). The command is thin: a summary, and any failure
exits non-zero (a ``CommandError``), which the infra's ``task_failed`` rule reports. ``--check`` applies nothing: it
lists what a run would apply and exits 1 if anything (the e2e's ``global-setup.ts``).

The migrator registers ``<db_name>__ddl`` aliases, which a Django test case refuses, so the tests that reach a template
or a hub run without one (``hubs.committed_database``, as ``db``), with this module's two small templates
(``small_templates``) instead of the catalog's: the platform's and a vertical's with ``tax``.
"""

import threading
import time
import uuid
from dataclasses import replace
from io import StringIO

import psycopg
import pytest
from django.core.management import CommandError, call_command
from django.db import DatabaseError, OperationalError, connection, connections
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

from base.tenancy import connections as tenancy_connections
from base.tenancy import migrator, names
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

PLATFORM = ("base", "live")
SMALL_VERTICAL = "small"


def leaves() -> dict[str, str]:
    return dict(MigrationLoader(None, ignore_no_migrations=True).graph.leaf_nodes())


def small_templates(control: str | None = None) -> list[migrator.Template]:
    """The platform's template and one vertical's, with ``tax``: what ``migrator.templates`` gives in this module."""
    control = tenancy_connections.control_name() if control is None else control
    platform = migrator.Template(db_name=names.template_db_name(control), apps=PLATFORM)
    vertical = migrator.Template(
        db_name=names.template_db_name(control, SMALL_VERTICAL),
        apps=(*PLATFORM, "tax"),
        source=platform.db_name,
        left_out=("staff",),
    )
    return [platform, vertical]


@pytest.fixture(scope="module")
def templates_built(django_db_setup, django_db_blocker):
    """This module's templates, built once on the test database's server and dropped at its end."""
    with pytest.MonkeyPatch.context() as patch, django_db_blocker.unblock():
        patch.setattr(migrator, "templates", small_templates)
        before = connections.settings
        try:
            hubs.bootstrap_template(small_templates()[0].db_name)  # db-bootstrap's, never the migrator's
            for template in small_templates():
                migrator.ensure_template(template)
        finally:
            # Its aliases would outlive the module, and a later test case refuses an alias it was not told about.
            hubs.forget_aliases(before)
        yield small_templates()
        for template in reversed(small_templates()):
            hubs.drop_database(template.db_name)


@pytest.fixture
def small(templates_built, monkeypatch):
    """``migrator.templates`` is this module's two templates, already up to date."""
    monkeypatch.setattr(migrator, "templates", small_templates)
    return templates_built


def migrate_hubs() -> str:
    out = StringIO()
    call_command("migrate_hubs", stdout=out)
    return out.getvalue()


def migrate_hubs_check() -> tuple[int, str]:
    """``migrate_hubs --check``: its exit status (1 if anything is pending) and its output."""
    out = StringIO()
    try:
        call_command("migrate_hubs", "--check", stdout=out)
    except SystemExit as exit_:
        return exit_.code, out.getvalue()
    return 0, out.getvalue()


def applied() -> set[tuple[str, str]]:
    return set(MigrationRecorder(connection).applied_migrations())


def missing_database() -> str:
    """A hub's database name of this control database that no database has."""
    return names.hub_db_name(tenancy_connections.control_name(), uuid.uuid7())


def at_the_leaf() -> dict[str, str]:
    leaf = leaves()
    return {label: leaf[label] for label in PLATFORM}


# ── A run ───────────────────────────────────────────────────────────────────────────────────────────────────────


def test_migrates_the_control_database_and_a_second_run_applies_nothing(small, db):
    # A control database one module behind: demo's tables are gone, as before its first deploy.
    call_command("migrate", "demo", "zero", database="default", verbosity=0)
    try:
        first = migrate_hubs()
        second = migrate_hubs()
    finally:
        call_command("migrate", database="default", verbosity=0)

    assert "migrate_hubs: control database migrated, 1 migration(s) applied." in first
    assert "migrate_hubs: control database migrated, 0 migration(s) applied." in second
    assert second.splitlines()[-4:] == [
        f"migrate_hubs: template {small[0].db_name} up to date.",
        f"migrate_hubs: template {small[1].db_name} up to date.",
        f"migrate_hubs: template {small[1].db_name} leaves out staff: its tables still reference control's users.",
        "migrate_hubs: hubs: 0 migrated, 0 left behind, 0 up to date.",
    ]


def test_a_run_goes_control_then_templates_then_the_hubs_behind(small, new_database, make_hub, monkeypatch):
    hub = make_hub(new_database)
    order = []
    for name in ("migrate_control", "ensure_template", "ensure_schema"):
        real = getattr(migrator, name)

        def spied(*args, _real=real, _name=name, **kwargs):
            order.append(_name)
            return _real(*args, **kwargs)

        monkeypatch.setattr(migrator, name, spied)

    out = migrate_hubs()

    assert order == ["migrate_control", "ensure_template", "ensure_template", "ensure_schema"]
    assert [alias for alias in connections.settings if alias.endswith(names.DDL_SUFFIX)] == []
    assert "migrate_hubs: hubs: 1 migrated, 0 left behind, 0 up to date." in out
    hub.refresh_from_db()
    assert hub.schema_apps == at_the_leaf()
    assert hub.schema_state == Hub.SchemaState.CURRENT
    assert hubs.table_names(new_database) == hubs.hub_tables(PLATFORM) | {"django_migrations"}


def test_a_missing_template_is_created_by_a_run(small, template_name, monkeypatch):
    extra = migrator.Template(db_name=template_name(), apps=(*PLATFORM, "customer"), source=small[0].db_name)
    monkeypatch.setattr(migrator, "templates", lambda control=None: [*small_templates(control), extra])

    out = migrate_hubs()

    assert f"migrate_hubs: template {extra.db_name}: " in out
    assert hubs.table_names(extra.db_name) == hubs.hub_tables(extra.apps) | {"django_migrations"}


def test_a_hub_that_fails_is_left_behind_and_the_others_still_migrate(small, new_database, make_hub):
    broken = make_hub(missing_database())  # its database is gone: the connection fails
    fine = make_hub(new_database)

    with pytest.raises(CommandError, match=f"1 hub\\(s\\) left behind: {broken.slug} ") as raised:
        migrate_hubs()

    assert raised.value.returncode != 0
    broken.refresh_from_db()
    fine.refresh_from_db()
    assert broken.schema_state == Hub.SchemaState.BEHIND
    assert fine.schema_state == Hub.SchemaState.CURRENT
    assert fine.schema_apps == at_the_leaf()


def test_hubs_at_the_leaf_are_not_opened(small, make_hub):
    """A deploy without migrations opens no hub's database (PLAN-DB §7): this one does not even exist."""
    make_hub(missing_database(), schema_apps=at_the_leaf())

    assert "migrate_hubs: hubs: 0 migrated, 0 left behind, 1 up to date." in migrate_hubs()


def test_only_the_hubs_with_a_complete_database_of_their_own_are_migrated(small, make_database, make_hub):
    """Ready, cancelled (kept to come back) and expired (until its purge); never one on control's database, one
    being made (the worker's), a failed one or a purged one."""
    alive = [
        make_hub(make_database(), status=status)
        for status in (Hub.Status.READY, Hub.Status.CANCELLED, Hub.Status.EXPIRED)
    ]
    make_hub("")
    for status in (Hub.Status.REQUESTED, Hub.Status.FAILED, Hub.Status.PURGED):
        make_hub(missing_database(), status=status)

    out = migrate_hubs()

    assert "migrate_hubs: hubs: 3 migrated, 0 left behind, 0 up to date." in out
    for hub in alive:
        hub.refresh_from_db()
        assert hub.schema_apps == at_the_leaf()


def test_erploras_own_hub_goes_first_then_at_most_four_at_once(small, make_hub, monkeypatch):
    platform = make_hub(missing_database(), is_platform=True)
    others = [make_hub(missing_database()) for _ in range(7)]
    guard = threading.Lock()
    events: list[tuple[str, str]] = []
    inside = [0]
    peak = [0]

    def ensure_schema(hub, **kwargs):
        with guard:
            events.append(("start", hub.slug))
            inside[0] += 1
            peak[0] = max(peak[0], inside[0])
        time.sleep(0.5)  # long enough for every worker of the pool to be inside at once
        with guard:
            inside[0] -= 1
            events.append(("end", hub.slug))
        return []

    monkeypatch.setattr(migrator, "ensure_schema", ensure_schema)

    out = migrate_hubs()

    assert events[:2] == [("start", platform.slug), ("end", platform.slug)]  # alone, before any other
    assert sorted(slug for event, slug in events[2:] if event == "start") == sorted(hub.slug for hub in others)
    assert peak[0] == migrator.HUB_WORKERS == 4
    assert "migrate_hubs: hubs: 8 migrated, 0 left behind, 0 up to date." in out


def lock_timeout() -> OperationalError:
    """What Django raises when ``lock_timeout`` cuts a statement (SQLSTATE 55P03)."""
    error = OperationalError("canceling statement due to lock timeout")
    error.__cause__ = psycopg.errors.LockNotAvailable("canceling statement due to lock timeout")
    return error


def test_a_lock_timeout_is_tried_again_up_to_three_times(small, make_hub, monkeypatch):
    late = make_hub(missing_database())
    stuck = make_hub(missing_database())
    calls = {late.slug: 0, stuck.slug: 0}
    guard = threading.Lock()

    def ensure_schema(hub, **kwargs):
        with guard:
            calls[hub.slug] += 1
            attempt = calls[hub.slug]
        if hub.slug == stuck.slug or attempt < 3:
            raise lock_timeout()
        return []

    monkeypatch.setattr(migrator, "ensure_schema", ensure_schema)

    with pytest.raises(CommandError, match=f"1 hub\\(s\\) left behind: {stuck.slug} "):
        migrate_hubs()

    assert calls == {late.slug: 3, stuck.slug: 3}
    stuck.refresh_from_db()
    assert stuck.schema_state == Hub.SchemaState.BEHIND


def test_a_missing_platform_template_stops_the_run_before_any_hub(small, template_name, make_hub, monkeypatch):
    missing = migrator.Template(db_name=template_name(), apps=PLATFORM)
    monkeypatch.setattr(migrator, "templates", lambda control=None: [missing, *small_templates(control)[1:]])
    make_hub(missing_database())
    touched = []
    monkeypatch.setattr(migrator, "ensure_schema", lambda hub, **kwargs: touched.append(hub))

    with pytest.raises(CommandError, match=f"{missing.db_name} does not exist on the settings' server: run db-boot"):
        migrate_hubs()

    assert touched == []
    assert not migrator.database_exists(missing.db_name)


def test_a_template_that_fails_stops_the_run_before_any_hub(small, make_hub, monkeypatch):
    make_hub(missing_database())
    touched = []

    def broken(template, **kwargs):
        raise DatabaseError("relation already exists")

    monkeypatch.setattr(migrator, "ensure_template", broken)
    monkeypatch.setattr(migrator, "ensure_schema", lambda hub, **kwargs: touched.append(hub))

    with pytest.raises(CommandError, match=f"the template {small[0].db_name} was not migrated: relation already"):
        migrate_hubs()

    assert touched == []


def test_every_server_gets_its_templates_and_each_hub_migrates_on_its_own(
    small, make_cluster, make_hub, new_database, opened_at, monkeypatch
):
    """``CREATE DATABASE … TEMPLATE`` clones only within one server (round 2026-10-30b): two «clusters» on the tests'
    own Postgres, named apart (``control``) so their templates do not meet; a closed one without hubs is never
    reached (its writer does not even resolve)."""
    other_host = same_server_by_another_name()
    second = make_cluster("second")
    holding = make_cluster("closed-holding", is_open=False, host=other_host)
    make_cluster("closed-empty", is_open=False, host="closed-empty.invalid")
    hub = make_hub(new_database, cluster=holding)
    second_control = f"{tenancy_connections.control_name()}_c2"
    real = migrator.clusters_to_migrate

    def apart(**kwargs):
        return [
            replace(target, control=second_control) if target.name == second.name else target
            for target in real(**kwargs)
        ]

    monkeypatch.setattr(migrator, "clusters_to_migrate", apart)
    made = [template.db_name for template in small_templates(second_control)]
    hubs.bootstrap_template(made[0], control=second_control)  # db-bootstrap ran on the second cluster
    try:
        out = migrate_hubs()

        for name in made:
            assert hubs.table_names(name) >= hubs.hub_tables(PLATFORM)
            assert f"migrate_hubs: template {name} on cluster {second.name}: " in out
        assert hubs.database_access(made[1]) == hubs.database_access(made[0])
        assert "closed-empty.invalid" not in {host for host, _name in opened_at}
        assert {host for host, name in opened_at if name == new_database} == {other_host}
        hub.refresh_from_db()
        assert hub.schema_apps == at_the_leaf()
    finally:
        for name in reversed(made):
            hubs.drop_database(name, control=second_control)


def test_the_templates_of_this_module_leave_no_migrator_alias_behind(small):
    """A ``__ddl`` alias left in the settings breaks every later test case of the process that reaches all of them
    (``makemigrations --check``'s consistency check: «queries to '…__ddl' are not allowed in this test»)."""
    assert [alias for alias in connections.settings if alias.endswith(names.DDL_SUFFIX)] == []


def test_a_failure_exits_non_zero_with_the_reason(monkeypatch):
    def broken_migrate_control(**kwargs):
        raise DatabaseError("could not connect to server")

    monkeypatch.setattr(migrator, "migrate_control", broken_migrate_control)

    with pytest.raises(CommandError, match="could not connect to server") as raised:
        migrate_hubs()

    assert raised.value.returncode != 0


# ── --check ─────────────────────────────────────────────────────────────────────────────────────────────────────


def test_check_lists_the_pending_migrations_exits_1_and_applies_nothing(small, db):
    # The control database one module behind, as a local database another branch left.
    call_command("migrate", "demo", "zero", database="default", verbosity=0)
    try:
        before = applied()
        status, out = migrate_hubs_check()
        after = applied()
    finally:
        call_command("migrate", database="default", verbosity=0)

    assert status == 1
    assert out.splitlines() == [
        "migrate_hubs: unapplied migrations in the control database:",
        "demo.0001_initial",
    ]
    assert after == before


def test_check_with_everything_up_to_date_exits_0(small, db, make_hub):
    make_hub(missing_database(), schema_apps=at_the_leaf())

    status, out = migrate_hubs_check()

    assert status == 0
    assert out.splitlines() == [
        "migrate_hubs: the control database, 2 template(s) and 1 hub(s) are up to date.",
    ]


def test_check_sees_a_new_migration_of_a_templates_app(small, db):
    vertical = small[1].db_name
    leaf = leaves()["tax"]
    with hubs._maintenance(vertical) as conn:  # as if the code had just gained tax's leaf
        conn.execute("DELETE FROM django_migrations WHERE app = 'tax' AND name = %s", [leaf])
    try:
        status, out = migrate_hubs_check()
    finally:
        with hubs._maintenance(vertical) as conn:
            conn.execute("INSERT INTO django_migrations (app, name, applied) VALUES ('tax', %s, now())", [leaf])

    assert status == 1
    assert out.splitlines() == [f"migrate_hubs: unapplied migrations in {vertical}:", f"tax.{leaf}"]


def test_check_lists_a_missing_verticals_template_and_creates_nothing(small, template_name, monkeypatch):
    extra = migrator.Template(db_name=template_name(), apps=(*PLATFORM, "customer"), source=small[0].db_name)
    monkeypatch.setattr(migrator, "templates", lambda control=None: [*small_templates(control), extra])

    status, out = migrate_hubs_check()

    lines = out.splitlines()
    assert status == 1
    assert lines[0] == (
        f"migrate_hubs: {extra.db_name} does not exist; a run clones it from {small[0].db_name} and applies:"
    )
    assert "customer.0001_initial" in lines[1:]
    assert not migrator.database_exists(extra.db_name)


def test_check_says_a_missing_platform_template_is_db_bootstraps(small, template_name, monkeypatch):
    missing = migrator.Template(db_name=template_name(), apps=PLATFORM)
    monkeypatch.setattr(migrator, "templates", lambda control=None: [missing, *small_templates(control)[1:]])

    status, out = migrate_hubs_check()

    assert status == 1
    assert out.splitlines() == [
        f"migrate_hubs: {missing.db_name} does not exist on the settings' server: run db-bootstrap there.",
    ]
    assert not migrator.database_exists(missing.db_name)


def test_check_lists_the_hubs_behind_without_opening_them(small, make_hub):
    behind = make_hub(missing_database())  # never confirmed: behind, and its database does not even exist

    status, out = migrate_hubs_check()

    assert status == 1
    assert out.splitlines() == ["migrate_hubs: hubs behind the code:", f"{behind.slug} ({behind.db_name})"]


def test_check_that_cannot_read_the_database_exits_non_zero_with_the_reason(monkeypatch):
    def broken_pending_control():
        raise DatabaseError("could not connect to server")

    monkeypatch.setattr(migrator, "pending_control", broken_pending_control)

    with pytest.raises(CommandError, match="could not connect to server") as raised:
        migrate_hubs_check()

    assert raised.value.returncode != 0
