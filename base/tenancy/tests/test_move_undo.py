"""A move undone: the origin first, a cancel that never takes an older copy for the hub's data, and the minor points.
The hubs and the passes are ``test_move.py``'s; their databases, ``conftest.py``'s."""

import datetime as dt
import uuid

import pytest
from psycopg import sql

from base.tenancy import bootstrap, move, names
from base.tenancy import connections as tenancy_connections
from base.tenancy.context import use_control
from base.tenancy.tests import hubs
from base.tenancy.tests.hubs import control_databases as databases
from base.tenancy.tests.hubs import marker
from base.tenancy.tests.s3 import aws_test_credentials, dumps_bucket, moto_s3
from base.tenancy.tests.test_move import AT, MARKER, fresh, nothing_checked_yet, run
from control.models import Cluster, Hub, LeftoverDatabase, MovedCopy

#: The moves' own autouse fixture and the bucket the ``moves`` of ``conftest.py`` asks for.
__all__ = ["aws_test_credentials", "dumps_bucket", "moto_s3", "nothing_checked_yet"]


def left_on(target: Cluster, hub: Hub) -> None:
    """``hub``'s database name noted as what an undone move may have left on ``target``."""
    with use_control():
        LeftoverDatabase.objects.create(hub=hub, cluster=target, db_name=hub.db_name, noted_at=AT)


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
        left_on(target, hub)

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
        left_on(target, hub)

        with use_control():
            move.worker_pass.drop_leftovers(AT)

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

        monkeypatch.setattr(move.moving, "_switch", broken)

        run()

        hub = fresh(hub)
        assert (hub.moving_to_id, hub.schema_state, hub.schema_apps) == (None, "behind", {"base": "0001_initial"})

    def test_a_move_asked_to_be_cancelled_goes_back_on_the_next_pass(self, moves, monkeypatch):
        target = moves.cluster()
        hub = moves.hub(to=target)

        def stopped(*args, **kwargs):
            raise move.exceptions.MoveStopped("the worker is stopping")

        with monkeypatch.context() as patched:
            patched.setattr(move.bucket, "_restore_from_bucket", stopped)
            run()
        assert fresh(hub).moving_to_id == target.pk
        with use_control():
            Hub.objects.filter(pk=hub.pk).update(move_undo_asked_at=AT)

        run()

        hub = fresh(hub)
        assert (hub.cluster_id, hub.moving_to_id) == (None, None)
        assert hub.last_error.startswith("move_cancelled")
        assert marker(hub.db_name) == [MARKER] and not MovedCopy.objects.filter(hub=hub).exists()


# ── A cancel never takes an older copy for the hub's data; the minor points ──────────────────────────────────────────


def an_older_copy(moves, hub, *, note: str = "old copy, two days old") -> str:
    """The copy this hub left on the settings' own server when it moved off it two days ago (kept 7 days)."""
    copy = moves.moved_copy(hub)
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
        move.moving.control_services.move.hub_move_cancel(system_context(REGISTRY_SCOPE), HubIdIn(id=hub.pk))


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
        # The worker's note and the copy on the origin say the data is in the copy (an older copy is
        # dropped before the note is written). A database with the hub's name there is the destination's (one server)
        # or a leftover, never the hub's: it is not reopened, the copy is not dated; the undo fails and is tried again.
        target = moves.cluster("away", port=1)
        hub = moves.hub(to=target)
        copy = moves.moved_copy(hub)
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
        # The restore fails, then the undo's drop of the destination does too. The hub
        # stays moving (503) with its data in the copy, never ready on the destination's half-made database.
        target = moves.cluster()  # the origin's own server
        hub = moves.hub(to=target)
        real_drop = move.undo.ops.drop_database
        calls = {"n": 0}

        def drop(name, **kwargs):
            calls["n"] += 1
            if calls["n"] >= 2:  # the undo's drop of the destination (the first is _make_destination's)
                raise move.undo.ops.DatabaseOpsError("statement timeout while dropping")
            return real_drop(name, **kwargs)

        def broken_restore(*args, **kwargs):
            raise move.exceptions.MoveFailed("move_restore_failed", "broke on purpose")

        monkeypatch.setattr(move.undo.ops, "drop_database", drop)
        monkeypatch.setattr(move.bucket, "_restore_from_bucket", broken_restore)

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

        with pytest.raises(move.exceptions.MoveStopped):
            move.undo._drop_destination(fresh(hub), target)

        assert marker(hub.db_name) == [MARKER]


    def test_on_the_origins_own_server_the_destination_is_never_dropped_without_the_copy_there(self, moves):
        # The destination's row points at the origin's server: what has the hub's name there is the live database
        # unless the data is in the copy, which is not there.
        target = moves.cluster()
        hub = moves.hub(to=target)
        copy = names.moved_db_name(tenancy_connections.control_name(), hub.id)

        with pytest.raises(move.exceptions.MoveStopped):
            move.undo._drop_destination(fresh(hub), target, origin=None, copy_name=copy)

        assert marker(hub.db_name) == [MARKER]


class TestTheMinorPoints:
    def test_the_switch_locks_the_lease_it_checks(self, moves):
        from django.db import connections
        from django.test.utils import CaptureQueriesContext

        target = moves.cluster()
        hub = moves.hub(to=target)
        with use_control():
            move.moving.services.provisioning.claim_hub(hub.id, AT, move.moving.LEASE)
            with CaptureQueriesContext(connections["default"]) as queries:
                move.moving.control_services.worker_move.move_finished(
                    hub.id,
                    target.pk,
                    None,
                    f"x_move_{hub.id.hex}",
                    AT,
                    owner=move.moving.services.provisioning.LEASE_OWNER,
                )

        leases = [q["sql"] for q in queries.captured_queries if '"control_hubdue"' in q["sql"]]
        assert leases and all("FOR UPDATE" in sql for sql in leases)

    def test_a_leftover_is_claimed_on_the_clock_and_checked_again_under_the_lease(self, moves, monkeypatch):
        elsewhere = moves.cluster("elsewhere", port=1)
        target = moves.cluster()
        hub = moves.hub(to=None, cluster=elsewhere)
        left_on(target, hub)
        claimed: list[dt.datetime] = []
        real = move.moving.services.provisioning.claim_hub

        def claim(hub_id, now, lease, **kwargs):
            claimed.append(now)
            # Meanwhile the hub moved to that cluster: its database there is live now.
            Hub.objects.filter(pk=hub_id).update(cluster=target)
            return real(hub_id, now, lease, **kwargs)

        monkeypatch.setattr(move.moving.services.provisioning, "claim_hub", claim)

        run()

        assert marker(hub.db_name) == [MARKER]
        assert not LeftoverDatabase.objects.filter(hub=hub).exists()
        [at] = claimed
        assert at > AT

    def test_the_same_server_is_known_by_its_address_not_by_how_it_is_written(self, moves):
        target = moves.cluster("spelled", host="localhost")
        hub = moves.hub(to=None)  # on the settings' own server, 127.0.0.1
        left_on(target, hub)

        with use_control():
            move.worker_pass.drop_leftovers(AT)

        assert marker(hub.db_name) == [MARKER]
        assert move.databases._same_server(None, target)

    def test_a_cancel_is_heard_while_the_copy_is_restored(self, moves, monkeypatch, caplog):
        target = moves.cluster()
        hub = moves.hub(to=target)
        monkeypatch.setattr(move.bucket.dumps, "POLL_SECONDS", 0.0)
        real = move.bucket._kept_entries

        def asked_meanwhile(listing):
            Hub.objects.filter(pk=hub.pk).update(move_undo_asked_at=AT)
            return real(listing)

        monkeypatch.setattr(move.bucket, "_kept_entries", asked_meanwhile)

        run()

        # The restore was stopped (its one transaction undone): the destination never got the hub's tables.
        assert fresh(hub).moving_to_id == target.pk
        assert "w8a_marker" not in hubs.table_names(hub.db_name)
        assert "base.tenancy.move.stopped" in caplog.text
        monkeypatch.undo()

        run()

        hub = fresh(hub)
        assert hub.moving_to_id is None and marker(hub.db_name) == [MARKER]
