"""A hub's database moved to another cluster (round 2026-10-30b of PLAN-DB, decision 3; tranche S7, part 1).

``control.hub.move`` asks; the worker moves (``base.tenancy.move.run_due``), under the hub's lease, one hub at a time:

1. the origin is closed to the app (``CONNECT`` taken from the environment's ``hub_app`` and ``hub_admin``, their
   sessions ended), so nothing writes in it from here on; its host answers 503 «maintenance» already;
2. it is renamed ``<control>_move_<hex>`` (an older copy of the same hub on that server goes first);
3. it is copied with ``pg_dump`` and, on the destination, its database is made from that cluster's template, emptied
   and filled with ``pg_restore`` (the template's extensions stay);
4. the destination's identity is checked and its schema brought to the code's leaf (``ensure_schema``);
5. control switches the hub to the destination in one transaction and keeps the copy's row (``MovedCopy``).

Any failure before the switch puts everything back on the origin, nothing lost: the destination's database dropped,
the copy renamed back and opened to the app again, the hub ready there with the reason in ``last_error``. A lease that
went to another worker is left to it. The copies are dropped after ``MOVED_COPY_DAYS``.

Real databases on the session's server: the destination cluster's row points at the same server (CI has one), which
the move handles as any other, since the origin is renamed before the destination is made.
"""

import datetime as dt
import uuid

import psycopg
import pytest
from django.db import connections as django_connections
from django.utils import timezone
from psycopg import sql

from base import services
from base.tenancy import bootstrap, identity, migrator, move, names
from base.tenancy import connections as tenancy_connections
from base.tenancy.context import use_control
from base.tenancy.tests import hubs
from control.models import Cluster, Hub, HubDue, LeftoverDatabase, MovedCopy

pytestmark = pytest.mark.usefixtures("no_test_fallback")

AT = dt.datetime(2026, 10, 31, 12, 0, tzinfo=dt.UTC)
MARKER = "kept across the move"


@pytest.fixture(autouse=True, scope="session")
def on_the_tests_control_database(django_db_setup):
    """These tests make, rename and drop real databases next to control's: only ever the tests' own."""
    from django.conf import settings

    control = tenancy_connections.control_name()
    if not control.startswith(settings.DATABASES["default"]["TEST"]["NAME"]):
        pytest.fail(f"The control database is {control!r}, not the tests': run this module whole, not one test of it.")


@pytest.fixture(autouse=True)
def nothing_checked_yet(monkeypatch):
    monkeypatch.setattr(identity, "_verified", set())


def databases() -> set[str]:
    control = tenancy_connections.control_name()
    with hubs._maintenance() as conn:
        return {row[0] for row in conn.execute("SELECT datname FROM pg_database") if row[0].startswith(control)}


def marker(name: str) -> list[str]:
    """What the hub's own table says in the database ``name`` (only the hub's database has it, never a template)."""
    with hubs._maintenance(name) as conn:
        return [row[0] for row in conn.execute("SELECT note FROM w8a_marker ORDER BY note")]


def says_it_is(name: str) -> list[uuid.UUID]:
    with hubs._maintenance(name) as conn:
        return [row[0] for row in conn.execute("SELECT hub_id FROM base_hub_identity")]


class Moves:
    """The rows and databases of one test (committed: no test case here), dropped and deleted after it."""

    def __init__(self, template: str):
        self.template = template
        self.hubs: list[Hub] = []
        self.clusters: list[Cluster] = []

    def cluster(self, name: str = "next", **fields) -> Cluster:
        default = django_connections.settings["default"]
        values = {"host": default["HOST"], "port": default["PORT"], "pooler_host": ""}
        self.clusters.append(row := Cluster.objects.create(name=f"{name}-{uuid.uuid4().hex[:8]}", **(values | fields)))
        return row

    def hub(self, *, to: Cluster | None, cluster: Cluster | None = None, **fields) -> Hub:
        """A ready hub on the settings' own server whose database is a clone of the template with its identity and a
        table of its own, asked to move ``to``."""
        hub_id = uuid.uuid7()
        control = tenancy_connections.control_name()
        name = names.hub_db_name(control, hub_id)
        with hubs._maintenance() as conn:
            conn.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    names.identifier(name, control=control), names.identifier(self.template, control=control)
                )
            )
        with hubs._maintenance(name) as conn:
            conn.execute("INSERT INTO base_hub_identity (hub_id) VALUES (%s)", [hub_id])
            conn.execute("CREATE TABLE w8a_marker (note text)")
            conn.execute("INSERT INTO w8a_marker VALUES (%s)", [MARKER])
        values = {
            "id": hub_id,
            "slug": f"acme-{hub_id.hex[-8:]}",
            "status": Hub.Status.READY,
            "db_name": name,
            "vertical": hubs.TEMPLATE_VERTICAL,
            "cluster": cluster,
            "moving_to": to,
        }
        self.hubs.append(row := Hub.objects.create(**(values | fields)))
        return row


@pytest.fixture
def moves(django_db_blocker, hub_databases):
    made = Moves(hub_databases.template)
    with django_db_blocker.unblock():
        yield made
        control = tenancy_connections.control_name()
        with hubs._maintenance() as conn:
            for row in made.hubs:
                for name in (row.db_name, names.moved_db_name(control, row.id)):
                    hubs._drop(conn, name, control)
        Hub.objects.filter(pk__in=[row.pk for row in made.hubs]).delete()
        Cluster.objects.filter(pk__in=[row.pk for row in made.clusters]).delete()


def fresh(hub: Hub) -> Hub:
    return Hub.objects.select_related("cluster", "moving_to").get(pk=hub.pk)


def run(now: dt.datetime = AT, **kwargs) -> int:
    with use_control():
        return move.run_due(now, **kwargs)


class TestAMove:
    def test_the_hub_moves_with_its_data_and_leaves_its_copy_behind(self, moves):
        target = moves.cluster()
        # Its schema noted behind (a deploy in course): brought to the code's leaf on its new cluster.
        hub = moves.hub(to=target, schema_state=Hub.SchemaState.BEHIND)
        control = tenancy_connections.control_name()
        copy = names.moved_db_name(control, hub.id)

        assert run() == 1

        hub = fresh(hub)
        assert (hub.cluster_id, hub.moving_to_id, hub.status, hub.last_error) == (target.pk, None, "ready", "")
        assert hub.schema_state == "current"
        assert marker(hub.db_name) == [MARKER] and says_it_is(hub.db_name) == [hub.id]
        assert marker(copy) == [MARKER]
        [kept] = MovedCopy.objects.filter(hub=hub)
        assert (kept.cluster_id, kept.db_name, kept.moved_at) == (None, copy, AT)
        # Its lease given back: nothing more is due for it.
        assert not HubDue.objects.filter(pk=hub.pk).exists()

    def test_the_destination_is_exactly_the_source_not_its_template(self, moves, hub_databases):
        # A template on the destination with a table of its own: the moved database has only what the hub had.
        vertical = f"w{uuid.uuid4().hex[:10]}"
        control = tenancy_connections.control_name()
        template = names.template_db_name(control, vertical)
        with hubs._maintenance() as conn:
            conn.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    names.identifier(template, control=control),
                    names.identifier(hub_databases.template, control=control),
                )
            )
        try:
            with hubs._maintenance(template) as conn:
                conn.execute("CREATE TABLE only_in_the_template (id int)")
            hub = moves.hub(to=moves.cluster(), vertical=vertical)

            run()

            assert fresh(hub).moving_to_id is None and fresh(hub).last_error == ""
            assert "only_in_the_template" not in hubs.table_names(hub.db_name)
            assert "w8a_marker" in hubs.table_names(hub.db_name)
            assert hubs.table_names(hub.db_name) == hubs.table_names(names.moved_db_name(control, hub.id))
        finally:
            hubs.drop_database(template)

    def test_a_hub_already_on_a_cluster_moves_off_it_and_its_copy_stays_there(self, moves):
        origin, target = moves.cluster("old"), moves.cluster()
        hub = moves.hub(cluster=origin, to=target)

        run()

        assert fresh(hub).cluster_id == target.pk
        assert MovedCopy.objects.get(hub=hub).cluster_id == origin.pk

    def test_one_hub_a_pass_the_longest_asked_first(self, moves):
        target = moves.cluster()
        first, second = moves.hub(to=target), moves.hub(to=target)

        assert run() == 1

        assert (fresh(first).moving_to_id, fresh(second).moving_to_id) == (None, target.pk)

    def test_a_hub_whose_lease_another_worker_holds_is_left_to_it(self, moves):
        target = moves.cluster()
        hub = moves.hub(to=target)
        with use_control():
            HubDue.objects.create(hub=hub, due_at=AT, lease_until=AT + dt.timedelta(minutes=1), lease_owner="other:1")

        assert run() == 0

        assert fresh(hub).moving_to_id == target.pk
        assert marker(hub.db_name) == [MARKER]

    def test_nothing_asked_nothing_done(self, moves):
        moves.hub(to=None)

        assert run() == 0


class TestTheOriginIsClosedToTheApp:
    """While it moves, the environment's app roles cannot reach the origin; after it, the moved database is theirs and
    the copy is not; after a failure, the origin is theirs again. A role of this test's own plays ``hub_app``."""

    @pytest.fixture
    def app_role(self, moves):
        role = f"w8a_app_{uuid.uuid4().hex[:8]}"
        with hubs._maintenance() as conn:
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD 'app'").format(sql.Identifier(role)))
        yield role
        with hubs._maintenance() as conn:
            for name in sorted(databases()):
                conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(sql.Identifier(name), sql.Identifier(role)))
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

    def grant(self, role: str, name: str) -> None:
        with hubs._maintenance() as conn:
            conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(name), sql.Identifier(role)))

    def test_while_it_moves_the_app_is_out_and_after_it_reaches_the_moved_database_only(
        self, moves, app_role, monkeypatch
    ):
        hub = moves.hub(to=moves.cluster())
        self.grant(app_role, hub.db_name)
        # A session of the app open on the origin before the move: ended by it.
        default = django_connections.settings["default"]
        open_session = psycopg.connect(
            dbname=hub.db_name, user=app_role, password="app", host=default["HOST"], port=default["PORT"]
        )
        seen: list[bool] = []
        real = move._dump

        def dump(source, cluster, path, heartbeat, cancelled=None):
            seen.append(self.reaches(app_role, source))
            return real(source, cluster, path, heartbeat, cancelled)

        monkeypatch.setattr(move, "_dump", dump)

        run(roles=self.roles(app_role))

        assert seen == [False]
        assert open_session.closed or open_session.broken or self._dead(open_session)
        copy = names.moved_db_name(tenancy_connections.control_name(), hub.id)
        assert (self.reaches(app_role, hub.db_name), self.reaches(app_role, copy)) == (True, False)

    @staticmethod
    def _dead(session) -> bool:
        try:
            session.execute("SELECT 1")
        except psycopg.OperationalError:
            return True
        return False

    def test_after_a_failure_the_app_reaches_the_origin_again(self, moves, app_role, monkeypatch):
        hub = moves.hub(to=moves.cluster())
        self.grant(app_role, hub.db_name)
        monkeypatch.setattr(move, "_restore", self.fails("restore"))

        run(roles=self.roles(app_role))

        assert fresh(hub).moving_to_id is None
        assert self.reaches(app_role, hub.db_name)

    @staticmethod
    def fails(step: str):
        def failing(*args, **kwargs):
            raise move.MoveFailed(f"move_{step}_failed", f"the {step} broke on purpose")

        return failing


class TestAFailurePutsEverythingBack:
    """Whatever step fails before the switch, the hub stays ready on its origin with every row it had."""

    @pytest.mark.parametrize("step", ["_dump", "_restore", "_verify_identity", "_ensure_schema", "_switch"])
    def test_the_hub_is_ready_on_its_origin_with_its_data_and_says_why(self, moves, monkeypatch, step):
        target = moves.cluster()
        hub = moves.hub(to=target)

        def broken(*args, **kwargs):
            raise RuntimeError(f"{step} broke on purpose")

        monkeypatch.setattr(move, step, broken)

        assert run() == 1

        hub = fresh(hub)
        control = tenancy_connections.control_name()
        assert (hub.cluster_id, hub.moving_to_id, hub.status) == (None, None, "ready")
        assert hub.last_error.startswith("move_") and "broke on purpose" in hub.last_error
        assert marker(hub.db_name) == [MARKER] and says_it_is(hub.db_name) == [hub.id]
        assert names.moved_db_name(control, hub.id) not in databases()
        assert not MovedCopy.objects.filter(hub=hub).exists()
        assert not HubDue.objects.filter(pk=hub.pk).exists()

    def test_a_destination_that_says_it_is_another_hub_is_refused(self, moves, monkeypatch):
        hub = moves.hub(to=moves.cluster())
        real = move._restore

        def restore_and_lie(path, name, cluster, heartbeat, cancelled=None):
            real(path, name, cluster, heartbeat, cancelled)
            with hubs._maintenance(name) as conn:
                conn.execute("UPDATE base_hub_identity SET hub_id = %s", [uuid.uuid7()])

        monkeypatch.setattr(move, "_restore", restore_and_lie)

        run()

        hub = fresh(hub)
        assert hub.moving_to_id is None and hub.last_error.startswith("move_identity_mismatch")
        assert says_it_is(hub.db_name) == [hub.id]

    def test_a_missing_template_on_the_destination_is_said(self, moves):
        hub = moves.hub(to=moves.cluster(), vertical="w8anotemplate")

        run()

        hub = fresh(hub)
        assert hub.moving_to_id is None and hub.last_error.startswith("move_template_missing")
        assert marker(hub.db_name) == [MARKER]

    def test_a_lease_lost_meanwhile_is_left_to_its_new_holder_untouched(self, moves, monkeypatch):
        target = moves.cluster()
        hub = moves.hub(to=target)

        def stolen(*args, **kwargs):
            raise services.ProvisioningStopped("another worker holds it now")

        monkeypatch.setattr(move, "_restore", stolen)

        run()

        hub = fresh(hub)
        # Nothing undone nor noted: the holder goes on from the copy (see TestResuming).
        assert (hub.moving_to_id, hub.last_error) == (target.pk, "")
        assert names.moved_db_name(tenancy_connections.control_name(), hub.id) in databases()


class TestResuming:
    def test_a_move_cut_after_the_rename_goes_on_from_the_copy(self, moves):
        target = moves.cluster()
        hub = moves.hub(to=target)
        control = tenancy_connections.control_name()
        copy = names.moved_db_name(control, hub.id)
        # Where a worker stopped: the copy noted as holding the data, then the rename.
        with use_control():
            MovedCopy.objects.create(hub=hub, cluster=None, db_name=copy, moved_at=None)
        with hubs._maintenance() as conn:
            conn.execute(
                sql.SQL("ALTER DATABASE {} RENAME TO {}").format(
                    names.identifier(hub.db_name, control=control), names.identifier(copy, control=control)
                )
            )

        run()

        hub = fresh(hub)
        assert (hub.cluster_id, hub.moving_to_id) == (target.pk, None)
        assert marker(hub.db_name) == [MARKER] and marker(copy) == [MARKER]

    def test_an_undo_that_failed_is_tried_again_as_an_undo_never_from_a_database_that_only_has_the_name(
        self, moves, monkeypatch
    ):
        # Review of round 2: a move that could not be undone is not taken forward on the next pass; it goes back to its
        # origin. The destination is on the origin's server here: after the rename, the hub's name there is the
        # destination's, never the data, which stays in the copy until it is renamed back.
        target = moves.cluster()
        hub = moves.hub(to=target)
        control = tenancy_connections.control_name()
        copy = names.moved_db_name(control, hub.id)

        def broken(*args, **kwargs):
            raise RuntimeError("broke on purpose")

        with monkeypatch.context() as patched:
            patched.setattr(move, "_ensure_schema", broken)
            patched.setattr(move, "_rename_back", broken)
            run()

        stuck = fresh(hub)
        assert stuck.moving_to_id == target.pk and "move_undo_failed" in stuck.last_error
        assert marker(copy) == [MARKER]
        [pending] = MovedCopy.objects.filter(hub=hub)
        assert pending.moved_at is None and stuck.move_undo_asked_at is not None

        run()

        hub = fresh(hub)
        assert (hub.cluster_id, hub.moving_to_id) == (None, None)
        # The reason of the move's failure, not of the undo that failed meanwhile.
        assert hub.last_error == "move_unexpected: RuntimeError: broke on purpose"
        assert marker(hub.db_name) == [MARKER] and copy not in databases()
        assert not MovedCopy.objects.filter(hub=hub).exists()

    def test_an_older_copy_of_the_same_hub_on_the_origin_gives_way_to_the_newer(self, moves):
        target = moves.cluster()
        hub = moves.hub(to=target)
        control = tenancy_connections.control_name()
        copy = names.moved_db_name(control, hub.id)
        with hubs._maintenance() as conn:
            conn.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    names.identifier(copy, control=control), names.identifier(moves.template, control=control)
                )
            )
        with use_control():
            MovedCopy.objects.create(hub=hub, cluster=None, db_name=copy, moved_at=AT - dt.timedelta(days=2))

        run()

        assert marker(copy) == [MARKER]
        [kept] = MovedCopy.objects.filter(hub=hub)
        assert kept.moved_at == AT


class TestTheCopiesGoAfterTheirDays:
    def test_a_copy_past_its_days_is_dropped_with_its_row_a_younger_one_stays(self, moves):
        hub = moves.hub(to=moves.cluster())
        run()
        control = tenancy_connections.control_name()
        copy = names.moved_db_name(control, hub.id)

        run(AT + dt.timedelta(days=move.MOVED_COPY_DAYS) - dt.timedelta(minutes=1))
        assert copy in databases() and MovedCopy.objects.filter(hub=hub).exists()

        run(AT + dt.timedelta(days=move.MOVED_COPY_DAYS))
        assert copy not in databases() and not MovedCopy.objects.filter(hub=hub).exists()
        # The hub's own database stays.
        assert marker(fresh(hub).db_name) == [MARKER]

    def test_a_drop_that_fails_is_kept_and_tried_again(self, moves, monkeypatch):
        hub = moves.hub(to=moves.cluster())
        run()

        def unreachable(*args, **kwargs):
            raise move.ops.DatabaseOpsError("the migrator cannot connect")

        monkeypatch.setattr(move, "_drop_copy", unreachable)
        run(AT + dt.timedelta(days=move.MOVED_COPY_DAYS + 1))

        assert MovedCopy.objects.filter(hub=hub).exists()

    def test_only_a_moved_copys_name_is_ever_dropped(self, moves):
        hub = moves.hub(to=None)

        with pytest.raises(names.InvalidDatabaseName):
            move._drop_copy(hub.db_name, None)
        assert marker(hub.db_name) == [MARKER]


@pytest.mark.django_db
def test_the_moves_lease_is_provisionings_and_its_copies_last_a_week():
    # The worker's lease of a moving hub is provisioning's (``base.tenancy.provision.LEASE``), renewed while it copies.
    from base.tenancy import provision

    assert (move.LEASE, move.MOVED_COPY_DAYS) == (provision.LEASE, 7)


def test_the_restore_leaves_out_the_extensions_and_the_public_schema_of_the_copy():
    # On Aurora only the master makes ``vector``: the destination's template has it, and the restore must neither drop
    # nor make it (nor the public schema, which holds its objects). The tests' superuser would not notice.
    listing = """;
; Archive created at 2026-10-31 18:00:00 UTC
3; 2615 2200 SCHEMA - public pg_database_owner
4; 0 0 COMMENT - SCHEMA public pg_database_owner
2; 3079 16385 EXTENSION - vector
5; 0 0 COMMENT - EXTENSION vector
230; 1259 16500 TABLE public base_hub_identity hub_migrator
4012; 0 16500 TABLE DATA public base_hub_identity hub_migrator
"""

    kept = move._kept_entries(listing)

    assert [line for line in kept if not line.startswith(";")] == [
        "230; 1259 16500 TABLE public base_hub_identity hub_migrator",
        "4012; 0 16500 TABLE DATA public base_hub_identity hub_migrator",
    ]



# ── Review of round 2: two workers, an unreachable destination, a missing origin, the schema record ──────────────────


class TestTwoWorkers:
    """A worker whose lease ran out (each deploy starts the new one before the old stops) never acts on a move another
    one took over: before each drop, rename or switch it checks it still holds the lease and that the hub still moves
    to its destination; the switch checks both on the locked row."""

    def test_a_late_switch_never_puts_the_hub_on_no_cluster(self, moves, monkeypatch, caplog):
        target = moves.cluster()
        hub = moves.hub(to=target)
        real = move._ensure_schema
        state = {"inner": False}

        def slow(moving, cluster, heartbeat=None):
            real(moving, cluster, heartbeat)
            if not state["inner"]:
                state["inner"] = True
                move.move_hub(moving.id)  # the worker that took the lease over, all the way to its switch

        monkeypatch.setattr(move, "_ensure_schema", slow)

        run()

        hub = fresh(hub)
        assert (hub.cluster_id, hub.moving_to_id, hub.last_error) == (target.pk, None, "")
        assert marker(hub.db_name) == [MARKER]
        assert "base.tenancy.move.stopped" in caplog.text

    def test_a_stale_worker_never_drops_the_live_destination_nor_touches_control(self, moves, monkeypatch, caplog):
        target = moves.cluster()
        hub = moves.hub(to=target)
        real_dump = move._dump
        state = {"nested": False}

        def dump(source, cluster, path, heartbeat, cancelled=None):
            real_dump(source, cluster, path, heartbeat, cancelled)
            if not state["nested"]:
                state["nested"] = True
                move.move_hub(hub.id)  # the other worker, all the way to its switch
                with hubs._maintenance(fresh(hub).db_name) as conn:
                    conn.execute("INSERT INTO w8a_marker VALUES ('written after the switch')")

        monkeypatch.setattr(move, "_dump", dump)

        run()

        hub = fresh(hub)
        assert (hub.cluster_id, hub.moving_to_id, hub.last_error) == (target.pk, None, "")
        assert marker(hub.db_name) == [MARKER, "written after the switch"]
        assert MovedCopy.objects.get(hub=hub).moved_at is not None
        assert "base.tenancy.move.stopped" in caplog.text

    def test_the_destination_control_says_is_a_hubs_there_is_never_dropped(self, moves):
        target = moves.cluster()
        hub = moves.hub(to=target)
        other = moves.hub(to=None, cluster=target)
        # A row of control that says the name is a hub's database on that cluster (another hub, here: a broken state).
        Hub.objects.filter(pk=other.pk).update(db_name=hub.db_name)

        with pytest.raises(move.MoveStopped):
            move._make_destination(fresh(hub), target, move.ops.environment_roles(tenancy_connections.control_name()))

        assert marker(hub.db_name) == [MARKER]


    def test_a_lease_another_worker_took_just_before_the_switch_is_never_switched(self, moves, monkeypatch, caplog):
        target = moves.cluster()
        hub = moves.hub(to=target)
        real = move._ensure_schema

        def then_taken(moving, cluster, heartbeat=None):
            real(moving, cluster, heartbeat)
            with use_control():
                HubDue.objects.filter(pk=moving.id).update(lease_owner="other:1")

        monkeypatch.setattr(move, "_ensure_schema", then_taken)

        run()

        hub = fresh(hub)
        assert (hub.cluster_id, hub.moving_to_id) == (None, target.pk)
        assert MovedCopy.objects.get(hub=hub).moved_at is None
        assert "base.tenancy.move.stopped" in caplog.text

    def test_a_cancel_that_arrives_meanwhile_stops_it_before_its_switch_and_the_next_pass_undoes_it(
        self, moves, monkeypatch
    ):
        target = moves.cluster()
        hub = moves.hub(to=target)
        real = move._dump

        def cancelled_meanwhile(source, cluster, path, heartbeat, cancelled=None):
            real(source, cluster, path, heartbeat, cancelled)
            with use_control():
                Hub.objects.filter(pk=hub.pk).update(move_undo_asked_at=AT)

        with monkeypatch.context() as patched:
            patched.setattr(move, "_dump", cancelled_meanwhile)
            run()
        assert fresh(hub).moving_to_id == target.pk

        run()

        hub = fresh(hub)
        assert (hub.cluster_id, hub.moving_to_id) == (None, None)
        assert marker(hub.db_name) == [MARKER]

    def test_a_worker_that_read_the_row_before_another_switched_never_touches_the_live_database(
        self, moves, monkeypatch
    ):
        target = moves.cluster()
        hub = moves.hub(to=target)
        stale = move.control_services.moving_row(hub.id)  # read before the other worker's switch
        run()
        assert fresh(hub).cluster_id == target.pk
        monkeypatch.setattr(move.control_services, "moving_row", lambda hub_id: stale)
        with use_control():
            move.services.claim_hub(hub.id, AT, move.LEASE)

        with use_control():
            move.move_hub(hub.id)

        hub = fresh(hub)
        copy = names.moved_db_name(tenancy_connections.control_name(), hub.id)
        assert (hub.cluster_id, hub.moving_to_id) == (target.pk, None)
        assert marker(hub.db_name) == [MARKER] and marker(copy) == [MARKER]

    def test_its_lease_is_renewed_while_its_schema_is_migrated(self, moves, monkeypatch):
        hub = moves.hub(to=moves.cluster())
        leases: list[tuple[dt.datetime, dt.datetime]] = []
        real = move.migrator.ensure_schema

        def ensure(moving, *, heartbeat=None, **kwargs):
            # A migration that takes a while beats the heart: the hub's lease (claimed at AT) moves on to now's.
            before = HubDue.objects.get(pk=hub.pk).lease_until
            heartbeat()
            leases.append((before, HubDue.objects.get(pk=hub.pk).lease_until))
            return real(moving, heartbeat=heartbeat, **kwargs)

        monkeypatch.setattr(move.migrator, "ensure_schema", ensure)

        run()

        [(before, after)] = leases
        assert after > before and fresh(hub).moving_to_id is None


class TestTheOriginFirst:
    """Undoing starts with the origin: the copy renamed back and opened to the app, the hub ready there. The destination
    is cleaned when it answers; when it does not, what may be left there is noted (``LeftoverDatabase``) and dropped on a
    later pass, never a database control says is a hub's, nor one on the hub's own server."""

    def test_an_unreachable_destination_puts_the_hub_back_on_its_origin_at_once(self, moves):
        target = moves.cluster("dead", port=1)
        hub = moves.hub(to=target)
        control = tenancy_connections.control_name()

        run()

        hub = fresh(hub)
        assert (hub.cluster_id, hub.moving_to_id) == (None, None)
        assert hub.last_error.startswith("move_clone_failed")
        assert marker(hub.db_name) == [MARKER] and names.moved_db_name(control, hub.id) not in databases()
        assert not MovedCopy.objects.filter(hub=hub).exists()
        [left] = LeftoverDatabase.objects.filter(hub=hub)
        assert (left.cluster_id, left.db_name) == (target.pk, hub.db_name)

    def test_a_leftover_is_dropped_on_a_later_pass_and_forgotten(self, moves):
        # The hub lives on another server (a row that points elsewhere); its name on this one is only a leftover.
        elsewhere = moves.cluster("elsewhere", port=1)
        target = moves.cluster()
        hub = moves.hub(to=None, cluster=elsewhere)
        with use_control():
            LeftoverDatabase.objects.create(hub=hub, cluster=target, db_name=hub.db_name, noted_at=AT)

        run()

        assert hub.db_name not in databases()
        assert not LeftoverDatabase.objects.filter(hub=hub).exists()

    @pytest.mark.parametrize(
        "where", ["the hubs own server", "the hubs cluster now", "its move there", "another hubs row there"]
    )
    def test_a_leftover_that_is_a_hubs_live_database_is_never_dropped_and_its_note_goes(self, moves, where):
        target = moves.cluster()
        if where == "the hubs own server":
            hub = moves.hub(to=None)  # on the settings' own server: the same one the target's row points at
        elif where == "the hubs cluster now":
            hub = moves.hub(to=None, cluster=target)
        elif where == "its move there":
            hub = moves.hub(to=target)  # its move drops what is left there before it clones
        else:
            # The hub lives on another server; a row of control says that name on the target is a hub's.
            hub = moves.hub(to=None, cluster=moves.cluster("elsewhere", port=1))
            other = moves.hub(to=None, cluster=target)
            Hub.objects.filter(pk=other.pk).update(db_name=hub.db_name)
        with use_control():
            LeftoverDatabase.objects.create(hub=hub, cluster=target, db_name=hub.db_name, noted_at=AT)

        with use_control():
            move.drop_leftovers(AT)

        assert marker(hub.db_name) == [MARKER]
        assert not LeftoverDatabase.objects.filter(hub=hub).exists()

    def test_a_database_missing_on_the_origin_ends_the_move_with_why(self, moves):
        # With the environment's app role on the server (as in AWS): nothing is granted on a database that is not there.
        role = f"w8a_app_{uuid.uuid4().hex[:8]}"
        with hubs._maintenance() as conn:
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD 'app'").format(sql.Identifier(role)))
        try:
            hub = moves.hub(to=moves.cluster())
            control = tenancy_connections.control_name()
            with hubs._maintenance() as conn:
                hubs._drop(conn, hub.db_name, control)

            run(roles=bootstrap.Names(hub_app=role, hub_admin="pg_monitor"))
        finally:
            with hubs._maintenance() as conn:
                conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))

        hub = fresh(hub)
        assert hub.moving_to_id is None and hub.last_error.startswith("move_database_missing")

    def test_a_failed_switch_gives_control_back_the_origins_schema_record(self, moves, monkeypatch):
        hub = moves.hub(to=moves.cluster(), schema_state=Hub.SchemaState.BEHIND, schema_apps={"base": "0001_initial"})

        def broken(*args, **kwargs):
            raise RuntimeError("control blinked")

        monkeypatch.setattr(move, "_switch", broken)

        run()

        hub = fresh(hub)
        assert (hub.moving_to_id, hub.schema_state, hub.schema_apps) == (None, "behind", {"base": "0001_initial"})

    def test_a_move_asked_to_be_cancelled_goes_back_on_the_next_pass(self, moves, monkeypatch):
        target = moves.cluster()
        hub = moves.hub(to=target)

        def stopped(*args, **kwargs):
            raise move.MoveStopped("the worker is stopping")

        with monkeypatch.context() as patched:
            patched.setattr(move, "_restore", stopped)
            run()
        assert fresh(hub).moving_to_id == target.pk
        with use_control():
            Hub.objects.filter(pk=hub.pk).update(move_undo_asked_at=AT)

        run()

        hub = fresh(hub)
        assert (hub.cluster_id, hub.moving_to_id) == (None, None)
        assert hub.last_error.startswith("move_cancelled")
        assert marker(hub.db_name) == [MARKER] and not MovedCopy.objects.filter(hub=hub).exists()



# ── Review of round 3: a cancel never takes an older copy for the hub's data; the minor points ───────────────────────


def an_older_copy(moves, hub, *, note: str = "old copy, two days old") -> str:
    """The copy this hub left on the settings' own server when it moved off it two days ago (kept 7 days)."""
    control = tenancy_connections.control_name()
    copy = names.moved_db_name(control, hub.id)
    with hubs._maintenance() as conn:
        conn.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                names.identifier(copy, control=control), names.identifier(moves.template, control=control)
            )
        )
    with hubs._maintenance(copy) as conn:
        conn.execute("CREATE TABLE w8a_marker (note text)")
        conn.execute("INSERT INTO w8a_marker VALUES (%s)", [note])
    with use_control():
        MovedCopy.objects.create(hub=hub, cluster=None, db_name=copy, moved_at=AT - dt.timedelta(days=2))
    return copy


def cancel(hub) -> None:
    from live.context import system_context

    from base.registry import REGISTRY_SCOPE
    from control.schemas import HubIdIn

    with use_control():
        move.control_services.hub_move_cancel(system_context(REGISTRY_SCOPE), HubIdIn(id=hub.pk))


class TestACancelBeforeTheWorkerStarted:
    def test_an_older_copy_on_the_origin_is_never_taken_for_the_hubs_data(self, moves):
        hub = moves.hub(to=moves.cluster())
        copy = an_older_copy(moves, hub)

        cancel(hub)
        run()

        hub = fresh(hub)
        assert (hub.cluster_id, hub.moving_to_id, hub.move_undo_asked_at) == (None, None, None)
        assert hub.last_error.startswith("move_cancelled")
        assert marker(hub.db_name) == [MARKER]
        # The older copy stays as it was, for its own days.
        assert marker(copy) == ["old copy, two days old"]
        assert MovedCopy.objects.get(hub=hub).moved_at == AT - dt.timedelta(days=2)

    def test_with_its_destination_on_another_server_it_never_stays_moving(self, moves):
        hub = moves.hub(to=moves.cluster("away", port=1))
        an_older_copy(moves, hub)

        cancel(hub)
        run()

        hub = fresh(hub)
        assert (hub.moving_to_id, hub.move_undo_asked_at) == (None, None)
        assert marker(hub.db_name) == [MARKER]

    def test_without_an_older_copy_the_hub_is_back_at_once(self, moves):
        hub = moves.hub(to=moves.cluster())

        cancel(hub)
        run()

        hub = fresh(hub)
        assert (hub.moving_to_id, hub.move_undo_asked_at) == (None, None)
        assert marker(hub.db_name) == [MARKER] and not MovedCopy.objects.filter(hub=hub).exists()


class TestTheUndoRenamesBackOnlyWhatLeft:
    def test_with_its_note_and_copy_a_database_of_the_hubs_name_on_the_origin_is_never_reopened_as_its_own(
        self, moves
    ):
        # Review of round 4: the worker's note and the copy on the origin say the data is in the copy (an older copy is
        # dropped before the note is written). A database with the hub's name there is the destination's (one server)
        # or a leftover, never the hub's: it is not reopened, the copy is not dated; the undo fails and is tried again.
        target = moves.cluster("away", port=1)
        hub = moves.hub(to=target)
        control = tenancy_connections.control_name()
        copy = names.moved_db_name(control, hub.id)
        with hubs._maintenance() as conn:
            conn.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    names.identifier(copy, control=control), names.identifier(moves.template, control=control)
                )
            )
        with use_control():
            MovedCopy.objects.create(hub=hub, cluster=None, db_name=copy, moved_at=None)
            Hub.objects.filter(pk=hub.pk).update(move_undo_asked_at=AT, last_error="move_cancelled: by hand")

        run()

        hub = fresh(hub)
        assert hub.moving_to_id == target.pk and "move_undo_failed" in hub.last_error
        assert copy in databases() and MovedCopy.objects.get(hub=hub).moved_at is None

    def test_on_one_server_a_destination_that_cannot_be_dropped_never_takes_the_place_of_the_real_data(
        self, moves, monkeypatch
    ):
        # The reviewer's probe (round 4): the restore fails, then the undo's drop of the destination does too. The hub
        # stays moving (503) with its data in the copy, never ready on the destination's half-made database.
        target = moves.cluster()  # the origin's own server
        hub = moves.hub(to=target)
        real_drop = move.ops.drop_database
        calls = {"n": 0}

        def drop(name, **kwargs):
            calls["n"] += 1
            if calls["n"] >= 2:  # the undo's drop of the destination (the first is _make_destination's)
                raise move.ops.DatabaseOpsError("statement timeout while dropping")
            return real_drop(name, **kwargs)

        def broken_restore(*args, **kwargs):
            raise move.MoveFailed("move_restore_failed", "broke on purpose")

        monkeypatch.setattr(move.ops, "drop_database", drop)
        monkeypatch.setattr(move, "_restore", broken_restore)

        run()

        hub = fresh(hub)
        copy = names.moved_db_name(tenancy_connections.control_name(), hub.id)
        assert hub.moving_to_id == target.pk and hub.move_undo_asked_at is not None
        assert hub.last_error.startswith("move_restore_failed") and "move_undo_failed" in hub.last_error
        assert marker(copy) == [MARKER] and MovedCopy.objects.get(hub=hub).moved_at is None
        monkeypatch.undo()

        run()

        hub = fresh(hub)
        assert (hub.cluster_id, hub.moving_to_id) == (None, None)
        assert marker(hub.db_name) == [MARKER] and copy not in databases()

    def test_the_destination_control_says_is_a_hubs_is_never_dropped_on_an_undo(self, moves):
        # On another server than the origin's (its row points elsewhere): only control's word stops the drop.
        target = moves.cluster("away", port=1)
        hub = moves.hub(to=target)
        other = moves.hub(to=None, cluster=target)
        Hub.objects.filter(pk=other.pk).update(db_name=hub.db_name)

        with pytest.raises(move.MoveStopped):
            move._drop_destination(fresh(hub), target)

        assert marker(hub.db_name) == [MARKER]


    def test_on_the_origins_own_server_the_destination_is_never_dropped_without_the_copy_there(self, moves):
        # The destination's row points at the origin's server: what has the hub's name there is the live database
        # unless the data is in the copy, which is not there.
        target = moves.cluster()
        hub = moves.hub(to=target)
        copy = names.moved_db_name(tenancy_connections.control_name(), hub.id)

        with pytest.raises(move.MoveStopped):
            move._drop_destination(fresh(hub), target, origin=None, copy_name=copy)

        assert marker(hub.db_name) == [MARKER]


class TestTheMinorPoints:
    def test_the_switch_locks_the_lease_it_checks(self, moves):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        target = moves.cluster()
        hub = moves.hub(to=target)
        with use_control():
            move.services.claim_hub(hub.id, AT, move.LEASE)
            with CaptureQueriesContext(connection) as queries:
                move.control_services.move_finished(
                    hub.id, target.pk, None, f"x_move_{hub.id.hex}", AT, owner=move.services.LEASE_OWNER
                )

        leases = [q["sql"] for q in queries.captured_queries if '"control_hubdue"' in q["sql"]]
        assert leases and all("FOR UPDATE" in sql for sql in leases)

    def test_a_leftover_is_claimed_on_the_clock_and_checked_again_under_the_lease(self, moves, monkeypatch):
        elsewhere = moves.cluster("elsewhere", port=1)
        target = moves.cluster()
        hub = moves.hub(to=None, cluster=elsewhere)
        with use_control():
            LeftoverDatabase.objects.create(hub=hub, cluster=target, db_name=hub.db_name, noted_at=AT)
        claimed: list[dt.datetime] = []
        real = move.services.claim_hub

        def claim(hub_id, now, lease, **kwargs):
            claimed.append(now)
            # Meanwhile the hub moved to that cluster: its database there is live now.
            Hub.objects.filter(pk=hub_id).update(cluster=target)
            return real(hub_id, now, lease, **kwargs)

        monkeypatch.setattr(move.services, "claim_hub", claim)

        run()

        assert marker(hub.db_name) == [MARKER]
        assert not LeftoverDatabase.objects.filter(hub=hub).exists()
        [at] = claimed
        assert at > AT

    def test_the_same_server_is_known_by_its_address_not_by_how_it_is_written(self, moves):
        target = moves.cluster("spelled", host="localhost")
        hub = moves.hub(to=None)  # on the settings' own server, 127.0.0.1
        with use_control():
            LeftoverDatabase.objects.create(hub=hub, cluster=target, db_name=hub.db_name, noted_at=AT)

        with use_control():
            move.drop_leftovers(AT)

        assert marker(hub.db_name) == [MARKER]
        assert move._same_server(None, target)

    def test_a_cancel_is_heard_while_the_copy_is_restored(self, moves, monkeypatch, caplog):
        target = moves.cluster()
        hub = moves.hub(to=target)
        monkeypatch.setattr(move.dumps, "POLL_SECONDS", 0.0)
        real = move._kept_entries

        def asked_meanwhile(listing):
            Hub.objects.filter(pk=hub.pk).update(move_undo_asked_at=AT)
            return real(listing)

        monkeypatch.setattr(move, "_kept_entries", asked_meanwhile)

        run()

        # The restore was stopped (its one transaction undone): the destination never got the hub's tables.
        assert fresh(hub).moving_to_id == target.pk
        assert "w8a_marker" not in hubs.table_names(hub.db_name)
        assert "base.tenancy.move.stopped" in caplog.text
        monkeypatch.undo()

        run()

        hub = fresh(hub)
        assert hub.moving_to_id is None and marker(hub.db_name) == [MARKER]
