"""The moves' pass (``base.tenancy.move.worker_pass``): a move asked for the business's night starts in it, and the
copies a move leaves behind go after their days. The hubs and the passes are ``test_move.py``'s; their databases,
``conftest.py``'s."""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from base.services import provisioning
from base.tenancy import connections as tenancy_connections
from base.tenancy import move, names
from base.tenancy.context import use_control
from base.tenancy.tests.hubs import control_databases as databases
from base.tenancy.tests.hubs import marker
from base.tenancy.tests.s3 import aws_test_credentials, dumps_bucket, moto_s3
from base.tenancy.tests.test_move import AT, MARKER, fresh, nothing_checked_yet, run
from control.models import Cluster, Hub, HubDue, MovedCopy

#: The moves' own autouse fixture and the bucket the ``moves`` of ``conftest.py`` asks for.
__all__ = ["aws_test_credentials", "dumps_bucket", "moto_s3", "nothing_checked_yet"]


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
        assert waiting.move_scheduled_for == move.worker_pass.control_services.move.night_start(
            now, ZoneInfo(waiting.timezone)
        )
        assert waiting.move_scheduled_for > now

    def test_one_not_due_yet_waits_even_at_night(self, moves):
        target = moves.cluster()
        now = timezone.now()
        hub = self.scheduled(moves, target, now, hour=3, due=-dt.timedelta(minutes=30))

        assert run(now) == 0
        with use_control():
            assert hub.id not in move.worker_pass.control_services.worker_move.moves_scheduled_due(now)
            # Even listed (a pass that read it before it was put off), its locked row says it is not due.
            assert provisioning.claim_hub(hub.id, now, move.moving.LEASE, owner="a:1") is not None
            assert move.worker_pass.control_services.worker_move.start_scheduled_move(hub.id, now, owner="a:1") is False

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
        start = move.worker_pass.control_services.worker_move.start_scheduled_move

        with use_control():
            assert provisioning.claim_hub(hub.id, now, move.moving.LEASE, owner="a:1") is not None
            with pytest.raises(move.worker_pass.control_services.worker_move.MoveTaken):
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


class TestTheCopiesGoAfterTheirDays:
    def test_a_copy_past_its_days_is_dropped_with_its_row_a_younger_one_stays(self, moves):
        hub = moves.hub(to=moves.cluster())
        run()
        control = tenancy_connections.control_name()
        copy = names.moved_db_name(control, hub.id)

        run(AT + dt.timedelta(days=move.worker_pass.MOVED_COPY_DAYS) - dt.timedelta(minutes=1))
        assert copy in databases() and MovedCopy.objects.filter(hub=hub).exists()

        run(AT + dt.timedelta(days=move.worker_pass.MOVED_COPY_DAYS))
        assert copy not in databases() and not MovedCopy.objects.filter(hub=hub).exists()
        # The hub's own database stays.
        assert marker(fresh(hub).db_name) == [MARKER]

    def test_a_drop_that_fails_is_kept_and_tried_again(self, moves, monkeypatch):
        hub = moves.hub(to=moves.cluster())
        run()

        def unreachable(*args, **kwargs):
            raise move.worker_pass.ops.DatabaseOpsError("the migrator cannot connect")

        monkeypatch.setattr(move.databases, "_drop_copy", unreachable)
        run(AT + dt.timedelta(days=move.worker_pass.MOVED_COPY_DAYS + 1))

        assert MovedCopy.objects.filter(hub=hub).exists()
