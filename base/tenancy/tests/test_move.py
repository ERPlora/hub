"""A hub's database moved to another cluster.

``control.hub.move`` asks; the worker moves (``base.tenancy.move.run_due``), under the hub's lease, one hub at a time:

1. the origin is closed to the app (``CONNECT`` taken from the environment's ``hub_app`` and ``hub_admin``, their
   sessions ended), so nothing writes in it from here on; its host answers 503 «maintenance» already;
2. it is renamed ``<control>_move_<hex>`` (an older copy of the same hub on that server goes first);
3. it is copied with ``pg_dump`` to the dumps bucket as it is made and, on the destination, its database is made from
   that cluster's template, emptied and filled with ``pg_restore`` reading the copy from the bucket (the template's
   extensions stay): never through a file of the worker, so no size stops it;
4. the destination's identity is checked and its schema brought to the code's leaf (``ensure_schema``);
5. control switches the hub to the destination in one transaction and keeps the copy's row (``MovedCopy``).

Any failure before the switch puts everything back on the origin, nothing lost: the destination's database dropped,
the copy renamed back and opened to the app again, the hub ready there with the reason in ``last_error``. A lease that
went to another worker is left to it. The copies are dropped after ``MOVED_COPY_DAYS``.

Real databases on the session's server: the destination cluster's row points at the same server (CI has one), which
the move handles as any other, since the origin is renamed before the destination is made. The bucket is a real S3
server (moto's, ``s3.py``).

The copy through the bucket, two workers on one move and the undo have their own ``test_move_*.py``; the databases
of every one are ``conftest.py``'s.
"""

import datetime as dt
import uuid
from zoneinfo import ZoneInfo

import psycopg
import pytest
from django.db import connections as django_connections
from django.utils import timezone
from psycopg import sql

from base.services import provisioning
from base.tenancy import identity, move, names
from base.tenancy import connections as tenancy_connections
from base.tenancy.context import use_control
from base.tenancy.tests import hubs
from base.tenancy.tests.s3 import aws_test_credentials, dumps_bucket, moto_s3  # noqa: F401
from control.models import Cluster, Hub, HubDue, MovedCopy

AT = dt.datetime(2026, 10, 31, 12, 0, tzinfo=dt.UTC)
MARKER = "kept across the move"


@pytest.fixture(autouse=True)
def nothing_checked_yet(monkeypatch):
    monkeypatch.setattr(identity, "_verified", set())


databases, marker, says_it_is = hubs.control_databases, hubs.marker, hubs.says_it_is


class Moves(hubs.CopiedHubs):
    """The rows and databases of one test, dropped and deleted after it."""

    def cluster(self, name: str = "next", **fields) -> Cluster:
        return super().cluster(name, **fields)

    def hub(self, *, to: Cluster | None, cluster: Cluster | None = None, **fields) -> Hub:
        """A ready hub on the settings' own server whose database is a clone of the template with its identity and a
        table of its own, asked to move ``to``."""
        hub_id = uuid.uuid7()
        name = self.database(hub_id, MARKER)
        return self.ready_hub(hub_id, name, **({"cluster": cluster, "moving_to": to} | fields))

    def moved_copy(self, hub: Hub) -> str:
        """The name ``hub``'s moved copy has on the settings' own server, made there as a clone of the template."""
        control = tenancy_connections.control_name()
        copy = names.moved_db_name(control, hub.id)
        with hubs._maintenance() as conn:
            conn.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    names.identifier(copy, control=control), names.identifier(self.template, control=control)
                )
            )
        return copy


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
        # The pass runs at the clock's own ``now``: the lease is held whether the pass claims with its ``now`` or with
        # the clock, and by one minute only, so a claim that takes a lease about to run out is seen.
        now = timezone.now()
        with use_control():
            HubDue.objects.create(hub=hub, due_at=now, lease_until=now + dt.timedelta(minutes=1), lease_owner="other:1")

        assert run(now) == 0

        assert fresh(hub).moving_to_id == target.pk
        assert marker(hub.db_name) == [MARKER]

    def test_nothing_asked_nothing_done(self, moves):
        moves.hub(to=None)

        assert run() == 0


def zone_at(now: dt.datetime, hour: int) -> str:
    """A fixed-offset zone (``Etc/GMT±N``, whose sign is the other way round) whose clock says ``hour`` o'clock at
    ``now``: the pass runs on the real clock, the one a lease is taken by."""
    offset = (hour - now.hour) % 24
    if offset > 14:
        offset -= 24
    return f"Etc/GMT{-offset:+d}"


class TestAMoveAskedForTheNight:
    """A move asked for the business's night (``control.hub.move`` with ``when="at_night"``) is started by the worker's
    pass once it is due and it is night on the business's own clock, under the hub's lease (``claim_hub``, as a move),
    with the checks of a move asked then; the same pass moves it. By day it waits for the next night."""

    def scheduled(self, moves, target: Cluster, now: dt.datetime, *, hour: int, due: dt.timedelta) -> Hub:
        return moves.hub(
            to=None, move_scheduled_to=target, move_scheduled_for=now - due, timezone=zone_at(now, hour)
        )

    def test_it_starts_in_the_business_s_night_and_the_same_pass_moves_it(self, moves):
        target = moves.cluster()
        now = timezone.now()
        hub = self.scheduled(moves, target, now, hour=3, due=dt.timedelta(minutes=1))

        assert run(now) == 1

        moved = fresh(hub)
        assert (moved.cluster_id, moved.moving_to_id) == (target.pk, None)
        assert (moved.move_scheduled_to_id, moved.move_scheduled_for, moved.last_error) == (None, None, "")
        assert marker(moved.db_name) == [MARKER]

    def test_by_the_business_s_day_it_waits_for_its_next_night_and_closes_nothing(self, moves):
        target = moves.cluster()
        now = timezone.now()
        hub = self.scheduled(moves, target, now, hour=15, due=dt.timedelta(hours=12))

        assert run(now) == 0

        waiting = fresh(hub)
        assert (waiting.cluster_id, waiting.moving_to_id, waiting.move_scheduled_to_id) == (None, None, target.pk)
        assert waiting.move_scheduled_for == move.control_services.move.night_start(now, ZoneInfo(waiting.timezone))
        assert waiting.move_scheduled_for > now

    def test_one_not_due_yet_waits_even_at_night(self, moves):
        target = moves.cluster()
        now = timezone.now()
        hub = self.scheduled(moves, target, now, hour=3, due=-dt.timedelta(minutes=30))

        assert run(now) == 0
        with use_control():
            assert hub.id not in move.control_services.worker_move.moves_scheduled_due(now)
            # Even listed (a pass that read it before it was put off), its locked row says it is not due.
            assert provisioning.claim_hub(hub.id, now, move.LEASE, owner="a:1") is not None
            assert move.control_services.worker_move.start_scheduled_move(hub.id, now, owner="a:1") is False

        assert (fresh(hub).moving_to_id, fresh(hub).move_scheduled_to_id) == (None, target.pk)

    def test_the_lease_says_which_worker_starts_it(self, moves):
        target = moves.cluster()
        now = timezone.now()
        hub = self.scheduled(moves, target, now, hour=3, due=dt.timedelta(minutes=1))
        with use_control():
            HubDue.objects.create(hub=hub, due_at=now, lease_until=now + dt.timedelta(minutes=1), lease_owner="other:1")

        assert run(now) == 0
        assert (fresh(hub).moving_to_id, fresh(hub).move_scheduled_to_id) == (None, target.pk)

        with use_control():
            HubDue.objects.filter(pk=hub.pk).update(lease_until=None, lease_owner="")
        assert run(now) == 1
        assert fresh(hub).cluster_id == target.pk

    def test_two_workers_never_start_it_twice(self, moves):
        target = moves.cluster()
        now = timezone.now()
        hub = self.scheduled(moves, target, now, hour=3, due=dt.timedelta(minutes=1))
        start = move.control_services.worker_move.start_scheduled_move

        with use_control():
            assert provisioning.claim_hub(hub.id, now, move.LEASE, owner="a:1") is not None
            with pytest.raises(move.control_services.worker_move.MoveTaken):
                start(hub.id, now, owner="b:2")
            assert (fresh(hub).moving_to_id, fresh(hub).move_scheduled_to_id) == (None, target.pk)

            assert start(hub.id, now, owner="a:1") is True
            assert start(hub.id, now, owner="a:1") is False
        started = fresh(hub)
        assert (started.moving_to_id, started.move_scheduled_to_id) == (target.pk, None)
        assert started.move_scheduled_for is None

    def test_the_place_it_was_keeping_on_a_cluster_with_one_left_is_its_own(self, moves):
        target = moves.cluster(max_hubs=1)
        now = timezone.now()
        hub = self.scheduled(moves, target, now, hour=3, due=dt.timedelta(minutes=1))

        assert run(now) == 1

        assert (fresh(hub).cluster_id, fresh(hub).last_error) == (target.pk, "")

    def test_a_size_that_cannot_be_read_leaves_it_asked_and_the_next_pass_starts_it(self, moves, monkeypatch):
        from control import queries

        target = moves.cluster()
        now = timezone.now()
        hub = self.scheduled(moves, target, now, hour=3, due=dt.timedelta(minutes=1))
        measure = queries.measure
        reads = []

        def unreachable_once(cluster, names):
            reads.append(names)
            if len(reads) == 1:
                raise queries._unreachable(cluster, "the server is restarting")
            return measure(cluster, names)

        monkeypatch.setattr(queries, "measure", unreachable_once)

        assert run(now) == 0

        waiting = fresh(hub)
        assert (waiting.moving_to_id, waiting.move_scheduled_to_id, waiting.last_error) == (None, target.pk, "")
        assert waiting.move_scheduled_for == now - dt.timedelta(minutes=1)
        with use_control():
            assert not HubDue.objects.filter(pk=hub.pk).exists()

        assert run(now) == 1
        assert fresh(hub).cluster_id == target.pk

    def test_one_refused_when_its_night_comes_says_why_and_closes_nothing(self, moves):
        target = moves.cluster(is_open=False)
        now = timezone.now()
        hub = self.scheduled(moves, target, now, hour=3, due=dt.timedelta(minutes=1))

        assert run(now) == 0

        refused = fresh(hub)
        assert (refused.cluster_id, refused.moving_to_id, refused.move_scheduled_to_id) == (None, None, None)
        assert refused.last_error.startswith("move_not_started: control.cluster_closed")
        assert marker(refused.db_name) == [MARKER]


class TestTheOriginIsClosedToTheApp:
    """While it moves, the environment's app roles cannot reach the origin; after it, the moved database is theirs and
    the copy is not; after a failure, the origin is theirs again. A role of this test's own plays ``hub_app``."""

    @pytest.fixture
    def app_role(self, moves):
        with hubs.an_app_role() as role:
            yield role

    def test_while_it_moves_the_app_is_out_and_after_it_reaches_the_moved_database_only(
        self, moves, app_role, monkeypatch
    ):
        hub = moves.hub(to=moves.cluster())
        hubs.grant_connect(app_role, hub.db_name)
        # A session of the app open on the origin before the move: ended by it.
        default = django_connections.settings["default"]
        open_session = psycopg.connect(
            dbname=hub.db_name, user=app_role, password="app", host=default["HOST"], port=default["PORT"]
        )
        seen: list[bool] = []
        real = move._dump_to_bucket

        def dump(key, source, cluster, heartbeat, cancelled=None):
            seen.append(hubs.reaches(app_role, source))
            real(key, source, cluster, heartbeat, cancelled)

        monkeypatch.setattr(move, "_dump_to_bucket", dump)

        run(roles=hubs.app_roles(app_role))

        assert seen == [False]
        assert open_session.closed or open_session.broken or self._dead(open_session)
        copy = names.moved_db_name(tenancy_connections.control_name(), hub.id)
        assert (hubs.reaches(app_role, hub.db_name), hubs.reaches(app_role, copy)) == (True, False)

    @staticmethod
    def _dead(session) -> bool:
        try:
            session.execute("SELECT 1")
        except psycopg.OperationalError:
            return True
        return False

    def test_after_a_failure_the_app_reaches_the_origin_again(self, moves, app_role, monkeypatch):
        hub = moves.hub(to=moves.cluster())
        hubs.grant_connect(app_role, hub.db_name)
        monkeypatch.setattr(move, "_restore_from_bucket", self.fails("restore"))

        run(roles=hubs.app_roles(app_role))

        assert fresh(hub).moving_to_id is None
        assert hubs.reaches(app_role, hub.db_name)

    @staticmethod
    def fails(step: str):
        def failing(*args, **kwargs):
            raise move.MoveFailed(f"move_{step}_failed", f"the {step} broke on purpose")

        return failing


class TestAFailurePutsEverythingBack:
    """Whatever step fails before the switch, the hub stays ready on its origin with every row it had."""

    @pytest.mark.parametrize(
        "step", ["_dump_to_bucket", "_restore_from_bucket", "_verify_identity", "_ensure_schema", "_switch"]
    )
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
        real = move._restore_from_bucket

        def restore_and_lie(key, name, cluster, heartbeat, cancelled=None):
            real(key, name, cluster, heartbeat, cancelled)
            with hubs._maintenance(name) as conn:
                conn.execute("UPDATE base_hub_identity SET hub_id = %s", [uuid.uuid7()])

        monkeypatch.setattr(move, "_restore_from_bucket", restore_and_lie)

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
            raise provisioning.ProvisioningStopped("another worker holds it now")

        monkeypatch.setattr(move, "_restore_from_bucket", stolen)

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
        # A move that could not be undone is not taken forward on the next pass; it goes back to its
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
        copy = moves.moved_copy(hub)
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
