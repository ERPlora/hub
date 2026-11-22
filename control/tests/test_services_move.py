"""A hub's move to another cluster."""

import uuid

import pytest
from live.errors import Conflict, NotFound, PermissionDenied

from control import services
from control.models import Cluster, Hub
from control.schemas import ClusterIdIn
from control.tests.conftest import a_cluster, a_ready_hub, as_actor, events, person

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("nothing_cached")]


class TestMove:
    """``control.hub.move`` asks the worker to move a ready hub's own database to another cluster (``base.tenancy.move``):
    its host answers 503 «maintenance» from now until the worker is done. Only an open cluster with room takes it, the
    way a new hub is placed. Its size stops nothing: the copy goes through the dumps bucket, never the worker's disk."""

    a_hub = staticmethod(a_ready_hub)

    def test_asks_the_move_and_says_so(self, admin_ctx, small):
        from control.schemas import HubMoveIn

        old, new = a_cluster(), a_cluster(name="cluster-2", host="writer-2.example")
        hub = self.a_hub(cluster=old, last_error="schema_failed: an old one")

        out = services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=new.pk))

        hub.refresh_from_db()
        assert (hub.moving_to_id, hub.cluster_id, hub.last_error) == (new.pk, old.pk, "")
        assert (out.id, out.cluster, out.moving_to) == (hub.pk, old.pk, new.pk)
        assert small == [(old, [hub.db_name])]
        assert events("control.hub.move_requested") == [
            {"id": str(hub.pk), "slug": "acme", "from": str(old.pk), "to": str(new.pk)}
        ]

    def test_a_hub_on_the_settings_own_server_moves_too(self, admin_ctx, small):
        from control.schemas import HubMoveIn

        new = a_cluster()
        hub = self.a_hub()

        out = services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=new.pk))

        assert (out.cluster, out.moving_to) == (None, new.pk)
        assert small == [(None, [hub.db_name])]
        assert events("control.hub.move_requested")[0]["from"] == ""

    @pytest.mark.parametrize(
        "fields",
        [{"status": Hub.Status.REQUESTED}, {"status": Hub.Status.CANCELLED}, {"db_name": ""}],
    )
    def test_only_a_ready_hub_with_its_own_database_moves(self, admin_ctx, small, fields):
        from control.schemas import HubMoveIn

        new = a_cluster()
        hub = self.a_hub(**fields)

        with pytest.raises(Conflict) as refused:
            services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=new.pk))

        assert refused.value.code == "control.hub_not_movable"
        hub.refresh_from_db()
        assert hub.moving_to_id is None

    def test_a_hub_already_moving_or_already_there_is_refused(self, admin_ctx, small):
        from control.schemas import HubMoveIn

        old, new = a_cluster(), a_cluster(name="cluster-2", host="writer-2.example")
        moving = self.a_hub(cluster=old, moving_to=new)
        there = self.a_hub(slug="bistro", cluster=new)

        for hub, code in ((moving, "control.hub_moving"), (there, "control.hub_already_there")):
            with pytest.raises(Conflict) as refused:
                services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=new.pk))
            assert refused.value.code == code

    def test_only_an_open_cluster_with_room_takes_it_counting_the_hubs_on_their_way(self, admin_ctx, small):
        from control.schemas import HubMoveIn

        closed = a_cluster(is_open=False)
        full = a_cluster(name="full", host="writer-full.example", max_hubs=2)
        self.a_hub(slug="living", cluster=full)
        self.a_hub(slug="arriving", moving_to=full)
        # A purged demo has no database there any more: not counted.
        self.a_hub(slug="demo-0000beef", is_demo=True, status=Hub.Status.PURGED, cluster=full)
        hub = self.a_hub()

        for cluster, code in ((closed, "control.cluster_closed"), (full, "control.cluster_full")):
            with pytest.raises(Conflict) as refused:
                services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=cluster.pk))
            assert refused.value.code == code
        full.max_hubs = 3
        full.save(update_fields=["max_hubs"])
        assert services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=full.pk)).moving_to == full.pk

    def test_a_demo_never_moves(self, admin_ctx, small):
        from control.schemas import HubMoveIn

        new = a_cluster()
        demo = self.a_hub(slug="demo-0000beef", is_demo=True)

        with pytest.raises(Conflict) as refused:
            services.hub_move(admin_ctx, HubMoveIn(hub=demo.pk, cluster=new.pk))

        assert refused.value.code == "control.hub_is_demo"

    @pytest.mark.parametrize("when", ["now", "at_night"])
    def test_a_database_of_any_size_is_asked_to_move(self, admin_ctx, monkeypatch, when):
        from control import queries
        from control.schemas import HubMoveIn

        new = a_cluster()
        hub = self.a_hub()
        monkeypatch.setattr(queries, "measure", lambda cluster, names: {names[0]: 40 * 1024**3})

        out = services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=new.pk, when=when))

        hub.refresh_from_db()
        assert new.pk in (out.moving_to, out.scheduled_to)
        assert new.pk in (hub.moving_to_id, hub.move_scheduled_to_id)

    def test_a_database_that_is_not_on_its_server_or_cannot_be_measured_does_not_move(self, admin_ctx, monkeypatch):
        from live.errors import OperationError

        from control import queries
        from control.schemas import HubMoveIn

        new = a_cluster()
        hub = self.a_hub()
        monkeypatch.setattr(queries, "measure", lambda cluster, names: {})
        with pytest.raises(Conflict) as refused:
            services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=new.pk))
        assert refused.value.code == "control.hub_database_missing"

        def unreachable(cluster, names):
            raise OperationError("The sizes … could not be read: refused", code="control.cluster_unreachable", status=503)

        monkeypatch.setattr(queries, "measure", unreachable)
        with pytest.raises(OperationError) as failed:
            services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=new.pk))
        assert failed.value.code == "control.cluster_unreachable"
        hub.refresh_from_db()
        assert hub.moving_to_id is None

    def test_measures_on_the_real_server(self, admin_ctx, hub_databases):
        from control.schemas import HubMoveIn

        new = a_cluster()
        hub = self.a_hub(db_name=hub_databases.a)

        assert services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=new.pk)).moving_to == new.pk

    def test_support_may_not_and_unknown_ones_are_not_found(self, admin_ctx, small):
        from control.schemas import HubMoveIn

        new = a_cluster()
        hub = self.a_hub()
        with pytest.raises(PermissionDenied):
            services.hub_move(as_actor(person("support", is_staff=True)), HubMoveIn(hub=hub.pk, cluster=new.pk))
        for move in (HubMoveIn(hub=uuid.uuid7(), cluster=new.pk), HubMoveIn(hub=hub.pk, cluster=uuid.uuid7())):
            with pytest.raises(NotFound):
                services.hub_move(admin_ctx, move)
        hub.refresh_from_db()
        assert hub.moving_to_id is None


def test_a_cluster_a_hub_is_moving_to_or_that_keeps_a_moved_copy_or_a_leftover_is_never_deleted(admin_ctx):
    from control.models import LeftoverDatabase, MovedCopy

    target, old = a_cluster(), a_cluster(name="old", host="writer-old.example")
    dead = a_cluster(name="dead", host="writer-dead.example")
    hub = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}", moving_to=target)
    MovedCopy.objects.create(hub=hub, cluster=old, db_name=f"hub_move_{hub.id.hex}", moved_at="2026-10-31T10:00Z")
    LeftoverDatabase.objects.create(hub=hub, cluster=dead, db_name=hub.db_name, noted_at="2026-10-31T10:00Z")

    for cluster in (target, old, dead):
        with pytest.raises(Conflict) as refused:
            services.cluster_delete(admin_ctx, ClusterIdIn(id=cluster.pk))
        assert refused.value.code == "control.cluster_holds_hubs"
    assert Cluster.objects.count() == 3


def test_the_move_is_an_internal_command_of_control():
    from live.operations import INTERNAL
    from live.operations import get as get_operation

    op = get_operation("control.hub.move")
    assert (op.kind, op.app_label, op.ai_spec(), op.fn.__module__) == ("command", "control", INTERNAL, "control.services")


class TestCancelAMove:
    """``control.hub.move_cancel`` asks the worker to undo a move, started or not: the hub
    is marked (``move_undo_asked_at``); no note of a copy is made nor taken, so an older copy of the same hub is never
    taken for its data. The worker puts the hub back on its origin on its next pass (``base.tenancy.move``)."""

    def test_a_move_is_marked_to_be_undone_and_no_copy_is_touched(self, admin_ctx):
        from control.models import MovedCopy
        from control.schemas import HubIdIn

        old, new = a_cluster(), a_cluster(name="cluster-2", host="writer-2.example")
        hub = Hub.objects.create(
            slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}", cluster=old, moving_to=new
        )
        # An older copy of this hub on its cluster, from a move off it two days ago.
        MovedCopy.objects.create(hub=hub, cluster=old, db_name=f"hub_move_{hub.id.hex}", moved_at="2026-10-29T10:00Z")

        out = services.hub_move_cancel(admin_ctx, HubIdIn(id=hub.pk))

        hub.refresh_from_db()
        assert hub.move_undo_asked_at is not None and hub.moving_to_id == new.pk
        assert hub.last_error.startswith("move_cancelled")
        [kept] = MovedCopy.objects.filter(hub=hub)
        assert kept.moved_at is not None
        assert (out.id, out.moving_to) == (hub.pk, new.pk)
        assert events("control.hub.move_cancel_requested") == [{"id": str(hub.pk), "slug": "acme"}]

    def test_a_hub_that_is_not_moving_is_refused_and_support_may_not(self, admin_ctx):
        from control.schemas import HubIdIn

        hub = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}")

        with pytest.raises(Conflict) as refused:
            services.hub_move_cancel(admin_ctx, HubIdIn(id=hub.pk))
        assert refused.value.code == "control.hub_not_moving"
        with pytest.raises(PermissionDenied):
            services.hub_move_cancel(as_actor(person("support", is_staff=True)), HubIdIn(id=hub.pk))
        with pytest.raises(NotFound):
            services.hub_move_cancel(admin_ctx, HubIdIn(id=uuid.uuid7()))
