"""A hub's database moved to another cluster.

``control.hub.move`` asks; the worker moves (``base.tenancy.move.worker_pass.run_due``), under the hub's lease, one
hub at a time:

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

Each module of the move has its own ``test_move_<module>.py``, and two workers on one move ``test_move_two_workers.py``;
the databases of every one are ``conftest.py``'s.
"""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from psycopg import sql

from base.tenancy import identity, move, names
from base.tenancy import connections as tenancy_connections
from base.tenancy.context import use_control
from base.tenancy.tests import hubs
from base.tenancy.tests.s3 import aws_test_credentials, dumps_bucket, moto_s3  # noqa: F401
from control.models.copies import MovedCopy
from control.models.hubs import Cluster, Hub, HubDue

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
        return move.worker_pass.run_due(now, **kwargs)


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


@pytest.mark.django_db
def test_the_moves_lease_is_provisionings_and_its_copies_last_a_week():
    # The worker's lease of a moving hub is provisioning's (``base.tenancy.provision.LEASE``), renewed while it copies.
    from base.tenancy import provision

    assert (move.moving.LEASE, move.worker_pass.MOVED_COPY_DAYS) == (provision.LEASE, 7)
