"""One hub's move (``base.tenancy.move.moving``): a step that fails puts everything back on the origin, and a move cut
short goes on from where it stopped. The hubs and the passes are ``test_move.py``'s; their databases,
``conftest.py``'s."""

import datetime as dt

import pytest
from psycopg import sql

from base.services import provisioning
from base.tenancy import connections as tenancy_connections
from base.tenancy import move, names
from base.tenancy.context import use_control
from base.tenancy.tests import hubs
from base.tenancy.tests.hubs import control_databases as databases
from base.tenancy.tests.hubs import marker, says_it_is
from base.tenancy.tests.s3 import aws_test_credentials, dumps_bucket, moto_s3
from base.tenancy.tests.test_move import AT, MARKER, fresh, nothing_checked_yet, run
from control.models import HubDue, MovedCopy

#: The moves' own autouse fixture and the bucket the ``moves`` of ``conftest.py`` asks for.
__all__ = ["aws_test_credentials", "dumps_bucket", "moto_s3", "nothing_checked_yet"]


class TestAFailurePutsEverythingBack:
    """Whatever step fails before the switch, the hub stays ready on its origin with every row it had."""

    @pytest.mark.parametrize(
        "step",
        [
            "bucket._dump_to_bucket",
            "bucket._restore_from_bucket",
            "destination._verify_identity",
            "destination._ensure_schema",
            "moving._switch",
        ],
        ids=lambda step: step.rpartition(".")[2],
    )
    def test_the_hub_is_ready_on_its_origin_with_its_data_and_says_why(self, moves, monkeypatch, step):
        target = moves.cluster()
        hub = moves.hub(to=target)

        def broken(*args, **kwargs):
            raise RuntimeError(f"{step} broke on purpose")

        monkeypatch.setattr(f"base.tenancy.move.{step}", broken)

        assert run() == 1

        hub = fresh(hub)
        control = tenancy_connections.control_name()
        assert (hub.cluster_id, hub.moving_to_id, hub.status) == (None, None, "ready")
        assert hub.last_error.startswith("move_") and "broke on purpose" in hub.last_error
        assert marker(hub.db_name) == [MARKER] and says_it_is(hub.db_name) == [hub.id]
        assert names.moved_db_name(control, hub.id) not in databases()
        assert not MovedCopy.objects.filter(hub=hub).exists()
        assert not HubDue.objects.filter(pk=hub.pk).exists()

    def test_a_lease_lost_meanwhile_is_left_to_its_new_holder_untouched(self, moves, monkeypatch):
        target = moves.cluster()
        hub = moves.hub(to=target)

        def stolen(*args, **kwargs):
            raise provisioning.ProvisioningStopped("another worker holds it now")

        monkeypatch.setattr(move.bucket, "_restore_from_bucket", stolen)

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
            patched.setattr(move.destination, "_ensure_schema", broken)
            patched.setattr(move.undo, "_rename_back", broken)
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
