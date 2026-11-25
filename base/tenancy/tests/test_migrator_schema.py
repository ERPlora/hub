"""``ensure_schema``, the only function that changes a hub's schema, and ``migrate_apps``, which it runs on the
hub's ``__ddl`` alias."""

import threading
import time

import pytest
from django.db import connections
from django.db.backends.signals import connection_created

from base.tenancy.migrator import app_sets, schema
from base.tenancy.tests import hubs
from base.tenancy.tests.hubs import (  # noqa: F401 (fixtures)
    committed_database,
    make_cluster,
    make_database,
    make_hub,
    new_database,
)
from base.tenancy.tests.test_migrator import PLATFORM, leaves, migrate_to, tables_of
from control.models import Hub

WAIT = 120


@pytest.fixture
def opened():
    """The databases every connection opened during the test reached (Django's ``connection_created``)."""
    names_opened: list[str] = []

    def record(sender, connection, **kwargs):
        names_opened.append(connection.settings_dict["NAME"])

    connection_created.connect(record)
    yield names_opened
    connection_created.disconnect(record)


# ── ensure_schema ───────────────────────────────────────────────────────────────────────────────────────────────


def test_a_hub_without_its_own_database_is_refused_and_nothing_is_opened(make_hub, opened):
    hub = make_hub("")
    opened.clear()

    with pytest.raises(schema.HubWithoutDatabase):
        schema.ensure_schema(hub)

    assert opened == []


def test_a_new_database_gets_the_platform_at_the_codes_leaf_and_control_learns_it(new_database, make_hub):
    hub = make_hub(new_database, schema_state=Hub.SchemaState.BEHIND)
    leaf = leaves()

    applied = schema.ensure_schema(hub)

    assert {f"base.{leaf['base']}", f"live.{leaf['live']}", "base.0001_initial"} <= set(applied)
    assert hubs.table_names(new_database) == tables_of(PLATFORM)
    hub.refresh_from_db()
    assert hub.schema_apps == {label: leaf[label] for label in PLATFORM}
    assert hub.schema_state == Hub.SchemaState.CURRENT


def test_a_second_run_applies_nothing(new_database, make_hub):
    hub = make_hub(new_database)
    schema.ensure_schema(hub)
    first = Hub.objects.get(pk=hub.pk).schema_apps

    assert schema.ensure_schema(hub) == []
    assert Hub.objects.get(pk=hub.pk).schema_apps == first


def test_add_creates_only_that_app_and_what_it_requires(new_database, make_hub):
    hub = make_hub(new_database)
    leaf = leaves()

    schema.ensure_schema(hub, add=["inventory"])  # inventory requires tax

    assert hubs.table_names(new_database) == tables_of({*PLATFORM, "inventory", "tax"})
    hub.refresh_from_db()
    assert hub.schema_apps == {label: leaf[label] for label in (*PLATFORM, "inventory", "tax")}


def test_a_database_whose_migrations_counter_went_back_records_what_it_applies(new_database, make_hub):
    """The counter of ``django_migrations`` of a hub cloned before its clone wrote its counters down can go back to the
    value it was cloned at (its page rebuilt from its own WAL): the next migration recorded would repeat an id and the
    deploy would stop on it. The migrator puts it at the highest id before it applies anything."""
    hub = make_hub(new_database)
    schema.ensure_schema(hub)
    with hubs._maintenance(new_database) as conn:
        conn.execute("SELECT setval(pg_get_serial_sequence('django_migrations', 'id'), 1)")

    applied = schema.ensure_schema(hub, add=["tax"])

    assert f"tax.{leaves()['tax']}" in applied
    with hubs._maintenance(new_database) as conn:
        counter, highest = conn.execute(
            "SELECT last_value, (SELECT max(id) FROM django_migrations) FROM django_migrations_id_seq"
        ).fetchone()
    assert counter == highest


def test_the_migrations_counter_is_left_alone_while_another_run_holds_the_schema_lock(new_database, make_hub):
    """The run that holds the lock is recording migrations: a counter moved under it could repeat one of its ids."""
    hub = make_hub(new_database)
    schema.ensure_schema(hub)
    counter = "SELECT last_value FROM django_migrations_id_seq"

    with hubs._maintenance(new_database) as holder:
        holder.execute("SELECT setval(pg_get_serial_sequence('django_migrations', 'id'), 1)")
        holder.execute("SELECT pg_advisory_lock(hashtext('erplora.schema'))")
        with pytest.raises(schema.SchemaLocked):
            schema.ensure_schema(hub, add=["tax"], lock_wait=0.2)

        assert holder.execute(counter).fetchone()[0] == 1


def test_the_migrator_moves_no_counter_but_the_one_of_its_migrations(new_database, make_hub):
    """Every other counter is written by the hub's own work while the migrator runs: setting one to a value read a
    moment before could hand that value out twice."""
    hub = make_hub(new_database)
    schema.ensure_schema(hub)
    credit = "SELECT log_cnt FROM in_use_by_the_hub"
    with hubs._maintenance(new_database) as conn:
        conn.execute("CREATE SEQUENCE in_use_by_the_hub")
        conn.execute("SELECT nextval('in_use_by_the_hub')")
        left = conn.execute(credit).fetchone()[0]
    assert left > 0

    schema.ensure_schema(hub, add=["tax"])

    with hubs._maintenance(new_database) as conn:
        assert conn.execute(credit).fetchone()[0] == left


def test_ensure_schema_beats_once_per_app_it_migrates(new_database, make_hub):
    """A long migration renews its caller's lease between apps (the worker's ``hub_due``), so
    two workers of a deploy never take the same hub while it is being made."""
    hub = make_hub(new_database)
    beats = []

    applied = schema.ensure_schema(hub, add=["inventory"], heartbeat=lambda: beats.append(len(beats)))

    assert len(beats) == len({name.split(".")[0] for name in applied}) > 2


def test_an_app_the_hubs_database_has_is_brought_to_the_leaf_even_if_control_never_learnt_it(new_database, make_hub):
    """When control and the hub's database disagree, the hub's own ``django_migrations`` wins."""
    hub = make_hub(new_database)
    schema.ensure_schema(hub)
    migrate_to(new_database, ("tax", "0001_initial"))  # created by an older code; control knows only the platform
    leaf = leaves()["tax"]

    applied = schema.ensure_schema(hub)

    assert f"tax.{leaf}" in applied
    hub.refresh_from_db()
    assert hub.schema_apps == {**{label: leaves()[label] for label in PLATFORM}, "tax": leaf}


def test_an_app_the_code_no_longer_knows_stays_in_schema_apps(new_database, make_hub):
    """A rollback ignores the labels it does not know and forgets nothing."""
    hub = make_hub(new_database, schema_apps={"gone": "0009_later"})

    schema.ensure_schema(hub)

    hub.refresh_from_db()
    assert hub.schema_apps["gone"] == "0009_later"


def test_a_database_control_s_row_does_not_name_yet_never_changes_that_row(new_database, make_hub):
    """Control's row learns what a database has only once it names that database: a cut migrates a business's database
    before its last step names it (``base.hub.cut_finish`` records its schema then, in one transaction), so a cut that
    breaks before leaves the row as it was. The hub in hand learns it all the same: the last step reads it."""
    hub = make_hub("", schema_state=Hub.SchemaState.BEHIND, schema_apps={"gone": "0009_later"})
    hub.db_name = new_database  # in hand only, as a cut holds it until its last step
    leaf = leaves()

    schema.ensure_schema(hub)

    assert hub.schema_apps == {"gone": "0009_later", **{label: leaf[label] for label in PLATFORM}}
    assert hub.schema_state == Hub.SchemaState.CURRENT
    row = Hub.objects.get(pk=hub.pk)
    assert (row.db_name, row.schema_apps, row.schema_state) == ("", {"gone": "0009_later"}, Hub.SchemaState.BEHIND)


def test_add_creates_the_people_apps_and_what_waited_for_them(new_database, make_hub):
    # An appointment hangs from a staff record, and a staff record from the business's own person.
    hub = make_hub(new_database)

    schema.ensure_schema(hub, add=["appointment"])

    assert {"base_hubuser", "staff_member", "service_service", "appointment_appointment"} <= hubs.table_names(new_database)
    hub.refresh_from_db()
    assert {"staff", "service", "appointment"} <= set(hub.schema_apps)


def test_add_refuses_an_app_that_cannot_live_in_a_hubs_database(new_database, make_hub, monkeypatch):
    # None today (tests/test_guardrails.py, «(h)»); one whose tables linked control's again would be refused.
    hub = make_hub(new_database)
    monkeypatch.setattr(app_sets, "portable_apps", lambda: tuple(sorted(app_sets.hub_apps() - {"staff"})))

    with pytest.raises(app_sets.AppNotPortable, match="staff"):
        schema.ensure_schema(hub, add=["staff"])

    assert hubs.table_names(new_database) == set()


def test_add_refuses_an_app_the_code_does_not_have(new_database, make_hub):
    hub = make_hub(new_database)

    with pytest.raises(app_sets.UnknownApp, match="nonexistent"):
        schema.ensure_schema(hub, add=["nonexistent"])

    assert hubs.table_names(new_database) == set()


def test_the_migrator_runs_with_its_session_limits(new_database, monkeypatch, make_hub):
    """lock_timeout 5 s, statement_timeout and idle_in_transaction 5 min."""
    hub = make_hub(new_database)
    seen = {}
    real = schema.migrate_apps

    def watching(alias, labels, **kwargs):
        with connections[alias].cursor() as cursor:
            for setting in ("lock_timeout", "statement_timeout", "idle_in_transaction_session_timeout"):
                cursor.execute(f"SHOW {setting}")
                seen[setting] = cursor.fetchone()[0]
        return real(alias, labels, **kwargs)

    monkeypatch.setattr(schema, "migrate_apps", watching)

    schema.ensure_schema(hub)

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
        with pytest.raises(schema.SchemaLocked) as raised:
            schema.ensure_schema(hub, lock_wait=0.5)
        waited = time.monotonic() - started

    assert raised.value.code == "schema_locked"
    assert waited >= 0.5
    assert hubs.table_names(new_database) == set()
    hub.refresh_from_db()
    assert hub.schema_apps == {}


def test_a_failed_run_leaves_neither_the_lock_nor_the_connection(new_database, monkeypatch, make_hub):
    hub = make_hub(new_database)

    def broken(alias, labels, **kwargs):
        raise RuntimeError("the migration broke")

    monkeypatch.setattr(schema, "migrate_apps", broken)

    with pytest.raises(RuntimeError, match="the migration broke"):
        schema.ensure_schema(hub)

    hubs.assert_nobody_on(new_database)
    with hubs._maintenance(new_database) as other:
        assert other.execute("SELECT pg_try_advisory_lock(hashtext('erplora.schema'))").fetchone()[0]
    hub.refresh_from_db()
    assert hub.schema_apps == {}


def test_a_failed_run_reports_its_own_error_even_when_its_connection_died(new_database, make_hub, monkeypatch):
    hub = make_hub(new_database)

    def dying(alias, labels, **kwargs):
        connections[alias].connection.close()  # the server went away in the middle of the run
        raise RuntimeError("the migration broke")

    monkeypatch.setattr(schema, "migrate_apps", dying)

    with pytest.raises(RuntimeError, match="the migration broke"):
        schema.ensure_schema(hub)


def test_two_runs_on_one_hub_at_once_one_waits_and_neither_fails(new_database, monkeypatch, make_hub):
    """Without the schema lock both would create the same tables, and one would fail with 42P07."""
    hub = make_hub(new_database)
    real = schema.migrate_apps
    guard = threading.Lock()
    inside = [0]
    peak = [0]

    def tracked(alias, labels, **kwargs):
        with guard:
            inside[0] += 1
            peak[0] = max(peak[0], inside[0])
        try:
            time.sleep(0.3)  # widens the window two unlocked runs would overlap in
            return real(alias, labels, **kwargs)
        finally:
            with guard:
                inside[0] -= 1

    monkeypatch.setattr(schema, "migrate_apps", tracked)
    start = threading.Barrier(2)
    results: list[list[str]] = []
    errors: list[Exception] = []

    def run():
        try:
            start.wait(WAIT)
            results.append(schema.ensure_schema(Hub.objects.get(pk=hub.pk)))
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

    assert schema.ensure_schema(hub_a) == []  # a clone of the template, at the code's leaf

    assert hub_databases.a in opened
    assert hub_databases.b not in opened
    hub_a.refresh_from_db()
    assert set(hub_a.schema_apps) == set(hub_databases.apps)


# ── A hub's database migrates only its own apps, through its __ddl alias ─────────────────────────────────────────


def test_migrate_apps_refuses_an_alias_that_is_no_migrators():
    with pytest.raises(ValueError, match="__ddl"):
        schema.migrate_apps("default", ["demo"])


def test_the_template_has_the_hub_tables_of_its_apps_and_nothing_of_controls(hub_databases):
    """A hub's database has exactly the tables of base and of its created apps."""
    from base.tenancy.tests import hubs

    assert hubs.table_names(hub_databases.template) == hubs.hub_tables(hub_databases.apps) | {"django_migrations"}
    assert "base_hub" not in hubs.table_names(hub_databases.a)
    assert "auth_user" not in hubs.table_names(hub_databases.a)


def test_migrate_apps_with_nothing_pending_applies_nothing(hub_databases, django_db_blocker):
    """A clone of the template is at the code's leaf: nothing to apply, and ``migrate`` is not even called."""
    from django.db import connections as django_connections

    from base.tenancy import connections

    with django_db_blocker.unblock():
        alias = connections.register_ddl_alias(hub_databases.a)
        try:
            assert schema.migrate_apps(alias, hub_databases.apps) == []
        finally:
            django_connections[alias].close()
