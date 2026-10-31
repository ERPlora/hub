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
from control.models import Cluster, Hub, HubDue, MovedCopy

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
        hub = moves.hub(to=target)
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

        def dump(source, cluster, path, heartbeat):
            seen.append(self.reaches(app_role, source))
            return real(source, cluster, path, heartbeat)

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

        def restore_and_lie(path, name, cluster, heartbeat):
            real(path, name, cluster, heartbeat)
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
