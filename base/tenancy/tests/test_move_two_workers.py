"""Two workers on the same move: the one whose lease ran out never acts on a move the other took over. The hubs and
the passes are ``test_move.py``'s; their databases, ``conftest.py``'s."""

import datetime as dt

import pytest

from base.tenancy import connections as tenancy_connections
from base.tenancy import move, names
from base.tenancy.context import use_control
from base.tenancy.tests import hubs
from base.tenancy.tests.hubs import marker
from base.tenancy.tests.s3 import aws_test_credentials, dumps_bucket, moto_s3
from base.tenancy.tests.test_move import AT, MARKER, fresh, nothing_checked_yet, run
from control.models import Hub, HubDue, MovedCopy

#: The moves' own autouse fixture and the bucket the ``moves`` of ``conftest.py`` asks for.
__all__ = ["aws_test_credentials", "dumps_bucket", "moto_s3", "nothing_checked_yet"]


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
        real_dump = move._dump_to_bucket
        state = {"nested": False}

        def dump(key, source, cluster, heartbeat, cancelled=None):
            real_dump(key, source, cluster, heartbeat, cancelled)
            if not state["nested"]:
                state["nested"] = True
                move.move_hub(hub.id)  # the other worker, all the way to its switch
                with hubs._maintenance(fresh(hub).db_name) as conn:
                    conn.execute("INSERT INTO w8a_marker VALUES ('written after the switch')")

        monkeypatch.setattr(move, "_dump_to_bucket", dump)

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
        real = move._dump_to_bucket

        def cancelled_meanwhile(key, source, cluster, heartbeat, cancelled=None):
            real(key, source, cluster, heartbeat, cancelled)
            with use_control():
                Hub.objects.filter(pk=hub.pk).update(move_undo_asked_at=AT)

        with monkeypatch.context() as patched:
            patched.setattr(move, "_dump_to_bucket", cancelled_meanwhile)
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
            move.services.provisioning.claim_hub(hub.id, AT, move.LEASE)

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
