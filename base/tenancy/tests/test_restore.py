"""A hub's database put back as it was at a moment, from a copy on a temporary cluster (hub#1198; PLAN-DB §13
«Restaurar un hub»).

``control.hub.restore`` asks; the worker restores (``base.tenancy.restore.run_due``), under the hub's lease, one hub at
a time, with the move's own steps (``base.tenancy.move``) and its origin and destination the other way round:

1. the copy of the hub's database is dumped from the temporary cluster (a point-in-time restore of its own, closed to
   new hubs); its host answers 503 «maintenance» already;
2. its database is closed to the app (``CONNECT`` taken from the environment's ``hub_app`` and ``hub_admin``, their
   sessions ended), so nothing writes in it from here on;
3. with nothing writing any more, each production VeriFactu record of it is compared with the copy's: one the copy
   lacks or has otherwise (made, sent, answered or changed after the moment) stops the restore, nothing changed;
4. it is kept aside as ``<control>_old_<hex>`` (its own UUIDv7), noted in control first (``MovedCopy``);
5. a new database of its name is made from its vertical's template on its own cluster, emptied and filled with the
   copy's ``pg_restore``, its identity checked and its schema brought to the code's leaf (``ensure_schema``);
6. control ends the restore and dates the kept copy, in one transaction.

Any failure before the end puts the hub's own database back, nothing lost: the new database dropped, the kept copy
renamed back and opened to the app again, the hub ready with the reason in ``last_error``. A lease that went to another
worker is left to it. The kept copies are dropped after ``move.MOVED_COPY_DAYS`` with the moves' copies.

Real databases on the session's server: the temporary cluster's row points at the same server (CI has one), so the
copy there has a name of its own (``run_due(source=…)``); in AWS it has the hub's, as a restore of the whole cluster
keeps it.
"""

import datetime as dt
import itertools
import uuid

import psycopg
import pytest
from django.apps import apps as django_apps
from django.db import connections as django_connections
from psycopg import sql
from psycopg.types.json import Jsonb

from base import services
from base.tenancy import bootstrap, identity, move, names, restore
from base.tenancy import connections as tenancy_connections
from base.tenancy.context import use_control
from base.tenancy.tests import hubs
from control import services as control_services
from control.models import Cluster, Hub, HubDue, MovedCopy

pytestmark = pytest.mark.usefixtures("no_test_fallback")

AT = dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.UTC)
#: The moment the copy is of.
THEN = AT - dt.timedelta(days=2)
BEFORE = THEN - dt.timedelta(days=1)
AFTER = THEN + dt.timedelta(hours=1)
AS_THEN = "as it was at the moment"
SINCE = "written after the moment"


@pytest.fixture(autouse=True)
def nothing_checked_yet(monkeypatch):
    monkeypatch.setattr(identity, "_verified", set())


def databases() -> set[str]:
    control = tenancy_connections.control_name()
    with hubs._maintenance() as conn:
        return {row[0] for row in conn.execute("SELECT datname FROM pg_database") if row[0].startswith(control)}


def marker(name: str) -> list[str]:
    """What the hub's own table says in the database ``name``."""
    with hubs._maintenance(name) as conn:
        return [row[0] for row in conn.execute("SELECT note FROM w8a_marker ORDER BY note")]


def says_it_is(name: str) -> list[uuid.UUID]:
    with hubs._maintenance(name) as conn:
        return [row[0] for row in conn.execute("SELECT hub_id FROM base_hub_identity")]


def write(name: str, note: str) -> None:
    with hubs._maintenance(name) as conn:
        conn.execute("INSERT INTO w8a_marker VALUES (%s)", [note])


_numbers = itertools.count(1)


def a_record(name: str, *, environment: str = "production", **fields) -> uuid.UUID:
    """A VeriFactu record in the database ``name``, every column the table requires filled, ``fields`` over them. The
    table's foreign keys are taken out of that database first: a record stands here without its invoice, and a copy of
    it restores as it is."""
    record_id = uuid.uuid7()
    number = next(_numbers)
    by_type = {
        "uuid": lambda length: uuid.uuid7(),
        "character varying": lambda length: f"x{number}"[: length or 64],
        "text": lambda length: "",
        "integer": lambda length: number,
        "bigint": lambda length: number,
        "smallint": lambda length: number,
        "boolean": lambda length: False,
        "date": lambda length: BEFORE.date(),
        "timestamp with time zone": lambda length: BEFORE,
        "jsonb": lambda length: Jsonb({}),
    }
    with hubs._maintenance(name) as conn:
        for (constraint,) in conn.execute(
            "SELECT conname FROM pg_constraint WHERE conrelid = 'verifactu_record'::regclass AND contype = 'f'"
        ).fetchall():
            conn.execute(sql.SQL("ALTER TABLE verifactu_record DROP CONSTRAINT {}").format(sql.Identifier(constraint)))
        required = conn.execute(
            "SELECT column_name, data_type, character_maximum_length FROM information_schema.columns "
            "WHERE table_name = 'verifactu_record' AND is_nullable = 'NO'"
        ).fetchall()
        values = {column: by_type[kind](length) for column, kind, length in required}
        lengths = {column: length for column, _kind, length in required}
        # A cancellation: no amounts to fill (``verifactu_record_amounts_by_type``); its fingerprint as long as one is.
        values |= {
            "id": record_id,
            "record_type": "anulacion",
            "fingerprint": "f" * lengths["fingerprint"],
            "environment": environment,
            "status": "accepted",
            "created_at": BEFORE,
            "updated_at": BEFORE,
        }
        values |= fields
        conn.execute(
            sql.SQL("INSERT INTO verifactu_record ({}) VALUES ({})").format(
                sql.SQL(", ").join(map(sql.Identifier, values)), sql.SQL(", ").join(sql.Placeholder() * len(values))
            ),
            list(values.values()),
        )
    return record_id


def change_record(name: str, record_id: uuid.UUID, **fields) -> None:
    with hubs._maintenance(name) as conn:
        conn.execute(
            sql.SQL("UPDATE verifactu_record SET {} WHERE id = %s").format(
                sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(column)) for column in fields)
            ),
            [*fields.values(), record_id],
        )


class Restores:
    """The rows and databases of one test (committed: no test case here), dropped and deleted after it."""

    def __init__(self, template: str):
        self.template = template
        self.hubs: list[Hub] = []
        self.clusters: list[Cluster] = []
        #: The copy of each hub on its temporary cluster (the session's server: a name of its own).
        self.copies: dict[uuid.UUID, str] = {}

    def cluster(self, name: str = "restore", **fields) -> Cluster:
        """A temporary cluster: closed to new hubs, on the session's server."""
        default = django_connections.settings["default"]
        values = {"host": default["HOST"], "port": default["PORT"], "pooler_host": "", "is_open": False}
        self.clusters.append(row := Cluster.objects.create(name=f"{name}-{uuid.uuid4().hex[:8]}", **(values | fields)))
        return row

    def hub(self, *, source: Cluster | None, cluster: Cluster | None = None, **fields) -> Hub:
        """A ready hub on the settings' own server whose database is a clone of the template with its identity and a
        table of its own; its copy on ``source`` is that database as it was at the moment, and the hub wrote one more
        row since. Asked to be restored from ``source``."""
        hub_id = uuid.uuid7()
        control = tenancy_connections.control_name()
        name = names.hub_db_name(control, hub_id)
        copy = names.hub_db_name(control, uuid.uuid7())
        with hubs._maintenance() as conn:
            conn.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    names.identifier(name, control=control), names.identifier(self.template, control=control)
                )
            )
        with hubs._maintenance(name) as conn:
            conn.execute("INSERT INTO base_hub_identity (hub_id) VALUES (%s)", [hub_id])
            conn.execute("CREATE TABLE w8a_marker (note text)")
            conn.execute("INSERT INTO w8a_marker VALUES (%s)", [AS_THEN])
        with hubs._maintenance() as conn:
            conn.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    names.identifier(copy, control=control), names.identifier(name, control=control)
                )
            )
        write(name, SINCE)
        self.copies[hub_id] = copy
        values = {
            "id": hub_id,
            "slug": f"acme-{hub_id.hex[-8:]}",
            "status": Hub.Status.READY,
            "db_name": name,
            "vertical": hubs.TEMPLATE_VERTICAL,
            "cluster": cluster,
            "restoring_from": source,
            "restore_point": THEN if source is not None else None,
        }
        self.hubs.append(row := Hub.objects.create(**(values | fields)))
        return row

    def source(self, hub) -> str:
        return self.copies[hub.id]


@pytest.fixture
def restores(django_db_blocker, hub_databases):
    made = Restores(hub_databases.template)
    with django_db_blocker.unblock():
        before = databases()
        yield made
        control = tenancy_connections.control_name()
        with hubs._maintenance() as conn:
            for name in sorted(databases() - before):
                hubs._drop(conn, name, control)
        Hub.objects.filter(pk__in=[row.pk for row in made.hubs]).delete()
        Cluster.objects.filter(pk__in=[row.pk for row in made.clusters]).delete()


def fresh(hub: Hub) -> Hub:
    return Hub.objects.select_related("cluster", "restoring_from").get(pk=hub.pk)


def run(restores: Restores, now: dt.datetime = AT, **kwargs) -> int:
    with use_control():
        return restore.run_due(now, source=restores.source, **kwargs)


def kept_copy(hub: Hub) -> MovedCopy:
    [kept] = MovedCopy.objects.filter(hub=hub)
    return kept


class TestARestore:
    def test_the_hub_gets_the_copys_data_and_its_own_is_kept_aside(self, restores):
        source = restores.cluster()
        # Its schema noted behind (the copy is from before a deploy): brought to the code's leaf.
        hub = restores.hub(source=source, schema_state=Hub.SchemaState.BEHIND)
        control = tenancy_connections.control_name()

        assert run(restores) == 1

        hub = fresh(hub)
        assert (hub.restoring_from_id, hub.restore_point, hub.cluster_id) == (None, None, None)
        assert (hub.status, hub.last_error, hub.schema_state) == ("ready", "", "current")
        assert marker(hub.db_name) == [AS_THEN] and says_it_is(hub.db_name) == [hub.id]
        kept = kept_copy(hub)
        assert (kept.cluster_id, kept.moved_at) == (None, AT)
        assert names.is_kept(kept.db_name, control=control)
        assert marker(kept.db_name) == [AS_THEN, SINCE]
        # The temporary cluster's copy is only read.
        assert marker(restores.copies[hub.id]) == [AS_THEN]
        assert not HubDue.objects.filter(pk=hub.pk).exists()

    def test_a_hub_on_a_cluster_is_restored_on_it_and_its_copy_is_kept_there(self, restores):
        own = restores.cluster("own", is_open=True)
        hub = restores.hub(source=restores.cluster(), cluster=own)

        run(restores)

        hub = fresh(hub)
        assert (hub.cluster_id, hub.restoring_from_id) == (own.pk, None)
        assert kept_copy(hub).cluster_id == own.pk
        assert marker(hub.db_name) == [AS_THEN]

    def test_one_hub_a_pass_the_longest_asked_first(self, restores):
        source = restores.cluster()
        first, second = restores.hub(source=source), restores.hub(source=source)

        assert run(restores) == 1

        assert (fresh(first).restoring_from_id, fresh(second).restoring_from_id) == (None, source.pk)

    def test_a_hub_whose_lease_another_worker_holds_is_left_to_it(self, restores):
        source = restores.cluster()
        hub = restores.hub(source=source)
        with use_control():
            HubDue.objects.create(hub=hub, due_at=AT, lease_until=AT + dt.timedelta(minutes=1), lease_owner="other:1")

        assert run(restores) == 0

        assert fresh(hub).restoring_from_id == source.pk
        assert marker(hub.db_name) == [AS_THEN, SINCE]

    def test_nothing_asked_nothing_done(self, restores):
        hub = restores.hub(source=None)

        assert run(restores) == 0

        assert marker(hub.db_name) == [AS_THEN, SINCE]

    def test_its_copy_on_the_temporary_cluster_has_the_hubs_own_name_by_default(self, restores):
        hub = restores.hub(source=restores.cluster())

        assert restore.source_name(hub) == hub.db_name


class TestClosedToTheApp:
    """While it is restored, the environment's app roles reach neither its database nor the new one; after it, the new
    one is theirs and the kept copy is not; after a failure, its own is theirs again. A role of the test plays
    ``hub_app``."""

    @pytest.fixture
    def app_role(self, restores):
        role = f"w8a_app_{uuid.uuid4().hex[:8]}"
        with hubs._maintenance() as conn:
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD 'app'").format(sql.Identifier(role)))
        yield role
        with hubs._maintenance() as conn:
            for name in sorted(databases()):
                revoke = sql.SQL("REVOKE ALL ON DATABASE {} FROM {}")
                conn.execute(revoke.format(sql.Identifier(name), sql.Identifier(role)))
            conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))

    @staticmethod
    def roles(role: str) -> bootstrap.Names:
        return bootstrap.Names(hub_app=role, hub_admin="pg_monitor")

    @staticmethod
    def reaches(role: str, name: str) -> bool:
        default = django_connections.settings["default"]
        try:
            with psycopg.connect(
                dbname=name, user=role, password="app", host=default["HOST"], port=default["PORT"], connect_timeout=5
            ):
                return True
        except psycopg.OperationalError:
            return False

    @staticmethod
    def grant(role: str, name: str) -> None:
        with hubs._maintenance() as conn:
            grant = sql.SQL("GRANT CONNECT ON DATABASE {} TO {}")
            conn.execute(grant.format(sql.Identifier(name), sql.Identifier(role)))

    def test_while_it_is_restored_the_app_is_out_and_after_it_reaches_the_new_database_only(
        self, restores, app_role, monkeypatch
    ):
        hub = restores.hub(source=restores.cluster())
        self.grant(app_role, hub.db_name)
        seen: list[tuple[bool, bool]] = []
        real = move._restore

        def restoring(path, name, cluster, heartbeat, cancelled=None):
            kept = control_services.pending_copy(hub.id).db_name
            seen.append((self.reaches(app_role, name), self.reaches(app_role, kept)))
            return real(path, name, cluster, heartbeat, cancelled)

        monkeypatch.setattr(move, "_restore", restoring)

        run(restores, roles=self.roles(app_role))

        assert seen == [(False, False)]
        kept = kept_copy(fresh(hub)).db_name
        assert (self.reaches(app_role, hub.db_name), self.reaches(app_role, kept)) == (True, False)

    def test_after_a_failure_the_app_reaches_its_own_database_again(self, restores, app_role, monkeypatch):
        hub = restores.hub(source=restores.cluster())
        self.grant(app_role, hub.db_name)

        def broken(*args, **kwargs):
            raise move.MoveFailed("move_restore_failed", "the restore broke on purpose")

        monkeypatch.setattr(move, "_restore", broken)

        run(restores, roles=self.roles(app_role))

        assert fresh(hub).restoring_from_id is None
        assert self.reaches(app_role, hub.db_name)
        assert marker(hub.db_name) == [AS_THEN, SINCE]


class TestAFailurePutsItsOwnBack:
    """Whatever step fails before the end, the hub is ready on its own database with every row it had."""

    @pytest.mark.parametrize(
        ("where", "step"),
        [
            (move, "_dump"),
            (move, "_restore"),
            (move, "_verify_identity"),
            (move, "_ensure_schema"),
            (restore, "_finish"),
        ],
    )
    def test_the_hub_is_ready_on_its_own_data_and_says_why(self, restores, monkeypatch, where, step):
        hub = restores.hub(source=restores.cluster(), schema_state=Hub.SchemaState.BEHIND, schema_apps={"w8a": "0001"})

        def broken(*args, **kwargs):
            raise RuntimeError(f"{step} broke on purpose")

        monkeypatch.setattr(where, step, broken)

        assert run(restores) == 1

        hub = fresh(hub)
        assert (hub.restoring_from_id, hub.restore_point, hub.move_undo_asked_at) == (None, None, None)
        assert hub.status == "ready"
        assert hub.last_error.startswith("restore_") and "broke on purpose" in hub.last_error
        assert marker(hub.db_name) == [AS_THEN, SINCE] and says_it_is(hub.db_name) == [hub.id]
        # Its schema record as it was: the new database's migration had written its own meanwhile.
        assert (hub.schema_state, hub.schema_apps) == ("behind", {"w8a": "0001"})
        control = tenancy_connections.control_name()
        assert not [name for name in databases() if names.is_kept(name, control=control)]
        assert not MovedCopy.objects.filter(hub=hub).exists()
        assert not HubDue.objects.filter(pk=hub.pk).exists()

    def test_a_copy_that_says_it_is_another_hub_is_refused(self, restores):
        hub = restores.hub(source=restores.cluster())
        with hubs._maintenance(restores.copies[hub.id]) as conn:
            conn.execute("UPDATE base_hub_identity SET hub_id = %s", [uuid.uuid7()])

        run(restores)

        hub = fresh(hub)
        assert hub.restoring_from_id is None and hub.last_error.startswith("restore_identity_mismatch")
        assert marker(hub.db_name) == [AS_THEN, SINCE] and says_it_is(hub.db_name) == [hub.id]

    def test_a_copy_missing_on_the_temporary_cluster_ends_it_with_why_its_own_untouched(self, restores):
        hub = restores.hub(source=restores.cluster())
        with hubs._maintenance() as conn:
            hubs._drop(conn, restores.copies[hub.id], tenancy_connections.control_name())

        run(restores)

        hub = fresh(hub)
        assert hub.restoring_from_id is None and hub.last_error.startswith("restore_dump_failed")
        assert marker(hub.db_name) == [AS_THEN, SINCE]

    def test_its_own_database_missing_ends_it_with_why(self, restores):
        hub = restores.hub(source=restores.cluster())
        with hubs._maintenance() as conn:
            hubs._drop(conn, hub.db_name, tenancy_connections.control_name())

        run(restores)

        hub = fresh(hub)
        assert hub.restoring_from_id is None and hub.last_error.startswith("restore_database_missing")
        assert hub.db_name not in databases()

    def test_the_new_database_is_never_made_while_its_own_is_not_kept_aside(self, restores, monkeypatch):
        # A rename that did not happen: the hub's name still holds its data, which nothing drops for a new one.
        hub = restores.hub(source=restores.cluster())
        monkeypatch.setattr(move, "_rename", lambda conn, old, new: None)

        run(restores)

        hub = fresh(hub)
        assert hub.restoring_from_id is None and hub.last_error.startswith("restore_copy_missing")
        assert marker(hub.db_name) == [AS_THEN, SINCE]


class TestTheFiscalGuard:
    """It only reads: a production record of the hub's database that the copy lacks or has otherwise stops it with the
    business closed, nothing changed; the restore would repeat numbers the AEAT has and drop invoices to keep."""

    def test_a_production_record_made_after_the_moment_stops_it(self, restores):
        hub = restores.hub(source=restores.cluster())
        a_record(hub.db_name, created_at=AFTER, updated_at=AFTER)

        run(restores)

        hub = fresh(hub)
        assert hub.restoring_from_id is None and hub.last_error.startswith("restore_fiscal_records")
        assert "1 " in hub.last_error
        assert marker(hub.db_name) == [AS_THEN, SINCE]
        assert not MovedCopy.objects.filter(hub=hub).exists()

    def test_a_record_made_before_and_sent_after_stops_it(self, restores):
        hub = restores.hub(source=restores.cluster())
        record = a_record(restores.copies[hub.id], status="pending")
        a_record(hub.db_name, id=record, status="pending")
        change_record(hub.db_name, record, status="accepted", transmitted_at=AFTER, updated_at=AFTER)

        run(restores)

        assert fresh(hub).last_error.startswith("restore_fiscal_records")
        assert marker(hub.db_name) == [AS_THEN, SINCE]

    @pytest.mark.parametrize(
        "changed",
        [{"updated_at": AFTER}, {"transmitted_at": AFTER}, {"status": "accepted_with_errors"}],
    )
    def test_a_record_that_changed_in_anything_compared_stops_it(self, restores, changed):
        hub = restores.hub(source=restores.cluster())
        record = a_record(restores.copies[hub.id])
        a_record(hub.db_name, id=record)
        change_record(hub.db_name, record, **changed)

        run(restores)

        assert fresh(hub).last_error.startswith("restore_fiscal_records")

    def test_testing_records_and_production_ones_as_they_were_do_not_stop_it(self, restores):
        hub = restores.hub(source=restores.cluster())
        unchanged = a_record(restores.copies[hub.id])
        a_record(hub.db_name, id=unchanged)
        a_record(hub.db_name, environment="testing", created_at=AFTER, updated_at=AFTER)

        run(restores)

        hub = fresh(hub)
        assert (hub.restoring_from_id, hub.last_error) == (None, "")
        assert marker(hub.db_name) == [AS_THEN]

    def test_it_looks_again_once_the_business_is_closed(self, restores, monkeypatch):
        # The business could invoice until it was closed: a record made right before is seen.
        hub = restores.hub(source=restores.cluster())
        real = move._close
        made: list[uuid.UUID] = []

        def close(conn, name, roles):
            if not made:
                made.append(a_record(hub.db_name, created_at=AFTER, updated_at=AFTER))
            real(conn, name, roles)

        monkeypatch.setattr(move, "_close", close)

        run(restores)

        assert made and fresh(hub).last_error.startswith("restore_fiscal_records")
        assert marker(hub.db_name) == [AS_THEN, SINCE]

    def test_without_verifactus_table_nothing_stops_it(self, restores):
        hub = restores.hub(source=restores.cluster())
        for name in (hub.db_name, restores.copies[hub.id]):
            with hubs._maintenance(name) as conn:
                conn.execute("DROP TABLE verifactu_record CASCADE")

        run(restores)

        assert (fresh(hub).restoring_from_id, fresh(hub).last_error) == (None, "")

    def test_a_production_record_the_copy_does_not_have_the_table_for_stops_it(self, restores):
        hub = restores.hub(source=restores.cluster())
        with hubs._maintenance(restores.copies[hub.id]) as conn:
            conn.execute("DROP TABLE verifactu_record CASCADE")
        a_record(hub.db_name)

        run(restores)

        assert fresh(hub).last_error.startswith("restore_fiscal_records")


class TestTheRecordsAfterTheMoment:
    """What ``control.hub.restore`` refuses on, before anything is closed: the production records of the hub's database
    made, changed or sent after the moment. It only reads."""

    def test_made_changed_or_sent_after_it_count_testing_and_before_do_not(self, restores):
        hub = restores.hub(source=None)
        a_record(hub.db_name, created_at=AFTER, updated_at=AFTER)
        a_record(hub.db_name, updated_at=AFTER)
        a_record(hub.db_name, transmitted_at=AFTER)
        a_record(hub.db_name, transmitted_at=BEFORE)
        a_record(hub.db_name, environment="testing", created_at=AFTER, updated_at=AFTER, transmitted_at=AFTER)

        assert restore.records_after(hub, THEN) == 3
        assert restore.records_after(hub, AFTER) == 0

    def test_without_verifactus_table_there_are_none(self, restores):
        hub = restores.hub(source=None)
        with hubs._maintenance(hub.db_name) as conn:
            conn.execute("DROP TABLE verifactu_record CASCADE")

        assert restore.records_after(hub, THEN) == 0

    def test_the_columns_read_are_verifactus_own(self):
        record = django_apps.get_model("verifactu", "Record")
        assert record._meta.db_table == restore.RECORDS_TABLE
        assert record.Environment.PRODUCTION == restore.PRODUCTION
        for column in ("environment", "status", "created_at", "updated_at", "transmitted_at"):
            assert record._meta.get_field(column).column == column


class TestTwoWorkers:
    """A worker whose lease ran out never acts on a restore another one took over: before each drop, rename or the end
    it checks it still holds the lease and that the hub is still restored from its cluster."""

    def test_a_lease_lost_meanwhile_is_left_to_its_new_holder_untouched(self, restores, monkeypatch):
        source = restores.cluster()
        hub = restores.hub(source=source)

        def stolen(*args, **kwargs):
            raise services.ProvisioningStopped("another worker holds it now")

        monkeypatch.setattr(move, "_restore", stolen)

        run(restores)

        hub = fresh(hub)
        # Nothing undone nor noted: the holder goes on from the kept copy (see TestResuming).
        assert (hub.restoring_from_id, hub.last_error) == (source.pk, "")
        assert marker(kept_copy(hub).db_name) == [AS_THEN, SINCE]

    def test_a_lease_another_worker_took_before_the_end_is_never_ended_here(self, restores, monkeypatch, caplog):
        source = restores.cluster()
        hub = restores.hub(source=source)
        real = move._ensure_schema

        def then_taken(restored, cluster, heartbeat=None):
            real(restored, cluster, heartbeat)
            with use_control():
                HubDue.objects.filter(pk=hub.pk).update(lease_owner="other:1")

        monkeypatch.setattr(move, "_ensure_schema", then_taken)

        run(restores)

        hub = fresh(hub)
        assert (hub.restoring_from_id, hub.last_error) == (source.pk, "")
        assert kept_copy(hub).moved_at is None
        assert "base.tenancy.restore.stopped" in caplog.text

    def test_a_restore_another_worker_ended_meanwhile_is_never_touched_again(self, restores, monkeypatch, caplog):
        source = restores.cluster()
        hub = restores.hub(source=source)
        real = move._dump

        def dump(copied, cluster, path, heartbeat, cancelled=None):
            real(copied, cluster, path, heartbeat, cancelled)
            with use_control():
                Hub.objects.filter(pk=hub.pk).update(restoring_from=None, restore_point=None)

        monkeypatch.setattr(move, "_dump", dump)

        run(restores)

        assert marker(fresh(hub).db_name) == [AS_THEN, SINCE]
        assert not MovedCopy.objects.filter(hub=hub).exists()
        assert "base.tenancy.restore.stopped" in caplog.text

    def test_an_undo_asked_is_never_taken_forward(self, restores):
        hub = restores.hub(source=restores.cluster())
        with use_control():
            Hub.objects.filter(pk=hub.pk).update(move_undo_asked_at=AT, last_error="restore_unexpected: before")

        run(restores)

        hub = fresh(hub)
        assert (hub.restoring_from_id, hub.move_undo_asked_at) == (None, None)
        assert hub.last_error == "restore_unexpected: before"
        assert marker(hub.db_name) == [AS_THEN, SINCE]


class TestResuming:
    def test_a_restore_cut_after_its_own_was_kept_aside_goes_on_from_the_kept_copy(self, restores):
        source = restores.cluster()
        hub = restores.hub(source=source)
        control = tenancy_connections.control_name()
        kept = names.kept_db_name(control, uuid.uuid7())
        # Where a worker stopped: the kept copy noted as holding the data, then the rename.
        with use_control():
            MovedCopy.objects.create(hub=hub, cluster=None, db_name=kept, moved_at=None)
        with hubs._maintenance() as conn:
            conn.execute(
                sql.SQL("ALTER DATABASE {} RENAME TO {}").format(
                    names.identifier(hub.db_name, control=control), names.identifier(kept, control=control)
                )
            )

        run(restores)

        hub = fresh(hub)
        assert (hub.restoring_from_id, hub.last_error) == (None, "")
        assert marker(hub.db_name) == [AS_THEN] and marker(kept) == [AS_THEN, SINCE]
        assert kept_copy(hub).moved_at == AT

    def test_an_undo_that_failed_is_tried_again_as_an_undo(self, restores, monkeypatch):
        source = restores.cluster()
        hub = restores.hub(source=source)

        def broken(*args, **kwargs):
            raise RuntimeError("broke on purpose")

        with monkeypatch.context() as patched:
            patched.setattr(move, "_ensure_schema", broken)
            patched.setattr(restore, "_put_back", broken)
            run(restores)

        stuck = fresh(hub)
        assert stuck.restoring_from_id == source.pk and "restore_undo_failed" in stuck.last_error
        assert stuck.move_undo_asked_at is not None
        assert marker(kept_copy(stuck).db_name) == [AS_THEN, SINCE]

        run(restores)

        hub = fresh(hub)
        assert (hub.restoring_from_id, hub.move_undo_asked_at) == (None, None)
        # The reason of the restore's failure, not of the undo that failed meanwhile.
        assert hub.last_error == "restore_unexpected: RuntimeError: broke on purpose"
        assert marker(hub.db_name) == [AS_THEN, SINCE]
        assert not MovedCopy.objects.filter(hub=hub).exists()


class TestTheKeptCopiesGoAfterTheirDays:
    def test_a_kept_copy_past_its_days_is_dropped_with_its_row_by_the_moves_pass(self, restores):
        hub = restores.hub(source=restores.cluster())
        run(restores)
        kept = kept_copy(fresh(hub)).db_name

        with use_control():
            move.run_due(AT + dt.timedelta(days=move.MOVED_COPY_DAYS) - dt.timedelta(minutes=1))
        assert kept in databases()

        with use_control():
            move.run_due(AT + dt.timedelta(days=move.MOVED_COPY_DAYS))
        assert kept not in databases() and not MovedCopy.objects.filter(hub=hub).exists()
        assert marker(fresh(hub).db_name) == [AS_THEN]

    def test_two_restores_within_the_days_keep_both_copies(self, restores):
        source = restores.cluster()
        hub = restores.hub(source=source)
        run(restores)
        with use_control():
            Hub.objects.filter(pk=hub.pk).update(restoring_from=source, restore_point=THEN)

        run(restores, AT + dt.timedelta(hours=1))

        first, second = MovedCopy.objects.filter(hub=hub).order_by("moved_at")
        assert marker(first.db_name) == [AS_THEN, SINCE] and marker(second.db_name) == [AS_THEN]
