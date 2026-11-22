"""A hub's database put back as it was at a moment, from a copy on a temporary cluster."""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied

from base.tenancy.tests.hubs import HUB_DATABASES
from control import services
from control.models import Cluster, Hub
from control.schemas import ClusterIdIn
from control.tests.conftest import a_cluster, a_ready_hub, as_actor, events, person

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("nothing_cached")]


class AskedFromATemporaryCluster:
    """What a restore in place (``control.hub.restore``) and a separate copy (``control.hub.restore_aside``) both
    refuse, nothing asked (``control.services._restorable``): a hub that is not ready or has no database of its own, a
    demo, one moving or being restored, a copy from a cluster open to new hubs, with hubs on it or the hub's own, a
    moment still to come, a copy missing; support, and unknown hubs or clusters (a copy of any size is asked:
    ``test_services_restore_any_size.py``)."""

    MOMENT = dt.datetime(2026, 11, 9, 14, 30, tzinfo=dt.UTC)

    a_hub = staticmethod(a_ready_hub)

    @staticmethod
    def temporary(**fields) -> Cluster:
        return a_cluster(**({"name": "restore-1", "host": "writer-restore.example", "is_open": False} | fields))

    # Each class names its ``operation`` and says what it would have written (``nothing_asked(hub)``).

    def ask(self, ctx, hub: Hub, cluster: Cluster, at: dt.datetime | None = None):
        from control.schemas import HubRestoreIn

        return self.operation(ctx, HubRestoreIn(hub=hub.pk, cluster=cluster.pk, at=at or self.MOMENT))

    @pytest.mark.parametrize(
        "fields",
        [{"status": Hub.Status.REQUESTED}, {"status": Hub.Status.CANCELLED}, {"db_name": ""}],
    )
    def test_only_a_ready_hub_with_its_own_database_is_restored(self, admin_ctx, small, fields):
        hub = self.a_hub(**fields)

        with pytest.raises(Conflict) as refused:
            self.ask(admin_ctx, hub, self.temporary())

        assert refused.value.code == "control.hub_not_restorable"
        assert self.nothing_asked(hub)

    def test_a_demo_moving_or_already_restored_hub_is_refused(self, admin_ctx, small):
        source, other = self.temporary(), a_cluster(name="cluster-2", host="writer-2.example")
        demo = self.a_hub(slug="demo-0000beef", is_demo=True)
        moving = self.a_hub(slug="moving", moving_to=other)
        restoring = self.a_hub(slug="restoring", restoring_from=source, restore_point=self.MOMENT)

        for hub, code in (
            (demo, "control.hub_is_demo"),
            (moving, "control.hub_moving"),
            (restoring, "control.hub_restoring"),
        ):
            with pytest.raises(Conflict) as refused:
                self.ask(admin_ctx, hub, source)
            assert refused.value.code == code
        assert small == [] and self.nothing_asked(demo) and self.nothing_asked(moving)

    def test_the_copy_comes_only_from_a_closed_temporary_cluster_never_its_own(self, admin_ctx, small):
        own = self.temporary(name="own", host="writer-own.example")
        open_one = a_cluster(name="open", host="writer-open.example")
        lived_on = self.temporary(name="lived-on", host="writer-lived.example")
        self.a_hub(slug="living", cluster=lived_on)
        hub = self.a_hub(cluster=own)

        for cluster, code in (
            (own, "control.restore_from_own_cluster"),
            (open_one, "control.cluster_open"),
            (lived_on, "control.cluster_holds_hubs"),
        ):
            with pytest.raises(Conflict) as refused:
                self.ask(admin_ctx, hub, cluster)
            assert refused.value.code == code
        assert self.nothing_asked(hub)

    def test_a_moment_still_to_come_is_refused(self, admin_ctx, small):
        hub = self.a_hub()

        with pytest.raises(InvalidPayload) as refused:
            self.ask(admin_ctx, hub, self.temporary(), at=timezone.now() + dt.timedelta(minutes=5))

        assert refused.value.code == "control.restore_point_ahead"
        assert set(refused.value.fields) == {"at"}

    def test_a_copy_missing_is_refused(self, admin_ctx, monkeypatch):
        from control import queries

        hub = self.a_hub()
        monkeypatch.setattr(queries, "measure", lambda cluster, names: {})

        with pytest.raises(Conflict) as refused:
            self.ask(admin_ctx, hub, self.temporary())

        assert refused.value.code == "control.restore_copy_missing"
        assert self.nothing_asked(hub)

    def test_support_may_not_and_unknown_ones_are_not_found(self, admin_ctx, small):
        from control.schemas import HubRestoreIn

        source, hub = self.temporary(), self.a_hub()
        with pytest.raises(PermissionDenied):
            self.ask(as_actor(person("support", is_staff=True)), hub, source)
        for asked in (
            HubRestoreIn(hub=uuid.uuid7(), cluster=source.pk, at=self.MOMENT),
            HubRestoreIn(hub=hub.pk, cluster=uuid.uuid7(), at=self.MOMENT),
        ):
            with pytest.raises(NotFound):
                self.operation(admin_ctx, asked)
        assert self.nothing_asked(hub)


class TestRestore(AskedFromATemporaryCluster):
    """``control.hub.restore`` asks the worker to put a ready hub's database back as it was at a moment, from the copy
    of it on a temporary cluster (``base.tenancy.restore``): its host answers 503 «maintenance» from now until the
    worker is done. The copy comes only from a cluster closed to new hubs with none on it, and never while the hub's
    database has a production VeriFactu record the copy lacks or has otherwise: the worker refuses that one, nothing
    changed (``base/tenancy/tests/test_restore.py``), for it reads both databases with the migrator."""

    operation = staticmethod(services.hub_restore)

    def nothing_asked(self, hub: Hub) -> bool:
        hub.refresh_from_db()
        return hub.restoring_from_id is None

    def test_asks_the_restore_and_says_so(self, admin_ctx, small):
        own, source = a_cluster(), self.temporary()
        hub = self.a_hub(cluster=own, last_error="move_cancelled: an old one")

        out = self.ask(admin_ctx, hub, source)

        hub.refresh_from_db()
        assert (hub.restoring_from_id, hub.restore_point, hub.cluster_id, hub.last_error) == (
            source.pk,
            self.MOMENT,
            own.pk,
            "",
        )
        assert (out.id, out.slug, out.cluster, out.restoring_from, out.restore_point) == (
            hub.pk,
            "acme",
            own.pk,
            source.pk,
            self.MOMENT,
        )
        # The copy is measured where it is, under the hub's own name.
        assert small == [(source, [hub.db_name])]
        assert events("control.hub.restore_requested") == [
            {"id": str(hub.pk), "slug": "acme", "from": str(source.pk), "at": self.MOMENT.isoformat()}
        ]

    def test_a_purged_demo_on_the_temporary_cluster_does_not_count_as_living_there(self, admin_ctx, small):
        source = self.temporary()
        self.a_hub(slug="demo-0000beef", is_demo=True, status=Hub.Status.PURGED, cluster=source)

        assert self.ask(admin_ctx, self.a_hub(), source).restoring_from == source.pk

    def test_a_move_is_refused_while_the_hub_is_restored(self, admin_ctx, small):
        from control.schemas import HubMoveIn

        hub = self.a_hub(restoring_from=self.temporary(), restore_point=self.MOMENT)

        with pytest.raises(Conflict) as refused:
            services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=a_cluster().pk))

        assert refused.value.code == "control.hub_restoring"

    @pytest.mark.django_db(databases=HUB_DATABASES)
    def test_measures_the_copy_and_reads_the_records_on_the_real_servers(self, admin_ctx, hub_a):
        from django.db import connections

        # The temporary cluster's row points at the session's server, where the hub's database stands for its copy.
        default = connections.settings["default"]
        source = self.temporary(host=default["HOST"], port=default["PORT"])

        assert self.ask(admin_ctx, hub_a, source).restoring_from == source.pk


    def test_a_cluster_a_hub_is_restored_from_is_never_deleted(self, admin_ctx):
        source = self.temporary()
        self.a_hub(restoring_from=source, restore_point=self.MOMENT)

        with pytest.raises(Conflict) as refused:
            services.cluster_delete(admin_ctx, ClusterIdIn(id=source.pk))

        assert refused.value.code == "control.cluster_holds_hubs"
        assert Cluster.objects.filter(pk=source.pk).exists()

    def test_the_restore_is_an_internal_command_of_control(self):
        from live.operations import INTERNAL
        from live.operations import get as get_operation

        op = get_operation("control.hub.restore")
        assert (op.kind, op.app_label, op.ai_spec(), op.fn.__module__) == (
            "command",
            "control",
            INTERNAL,
            "control.services",
        )


class TestRestoreAside(AskedFromATemporaryCluster):
    """``control.hub.restore_aside`` asks the worker to make, on the hub's own cluster, a separate copy of its database
    as it was at a moment, from its copy on a temporary cluster (``base.tenancy.restore``): the
    business is never closed nor changed, so a hub with production VeriFactu records made after the moment gets its
    data back this way. The copy is a ``RestoredCopy`` row named ``<control>_copy_<its hex>``; it is asked under the
    same conditions as a restore in place (``control.hub.restore``)."""

    operation = staticmethod(services.hub_restore_aside)

    def nothing_asked(self, hub: Hub) -> bool:
        from control.models import RestoredCopy

        return not RestoredCopy.objects.filter(hub=hub).exists()

    def test_asks_a_copy_aside_and_the_business_stays_open_as_it_was(self, admin_ctx, small):
        from base import registry
        from base.tenancy import names
        from base.tenancy.connections import control_name
        from control.models import RestoredCopy

        own, source = a_cluster(), self.temporary()
        hub = self.a_hub(cluster=own, last_error="move_cancelled: an old one")

        out = self.ask(admin_ctx, hub, source)

        [copy] = RestoredCopy.objects.all()
        assert (copy.hub_id, copy.cluster_id, copy.source_id, copy.restore_point, copy.status, copy.made_at) == (
            hub.pk,
            own.pk,
            source.pk,
            self.MOMENT,
            RestoredCopy.Status.COPYING,
            None,
        )
        assert copy.db_name == f"{control_name()}_copy_{copy.pk.hex}"
        assert names.is_copy_aside(copy.db_name, control=control_name())
        assert copy.asked_by == "root"
        # The business is not touched: no 503, nothing restored in place, its last error as it was.
        hub.refresh_from_db()
        assert (hub.restoring_from_id, hub.restore_point, hub.moving_to_id, hub.status) == (None, None, None, "ready")
        assert hub.last_error == "move_cancelled: an old one"
        assert not registry.is_copying(hub)
        assert (out.id, out.hub, out.slug, out.db_name, out.cluster, out.source, out.restore_point, out.status) == (
            copy.pk,
            hub.pk,
            "acme",
            copy.db_name,
            own.pk,
            source.pk,
            self.MOMENT,
            "copying",
        )
        assert small == [(source, [hub.db_name])]
        assert events("control.hub.restore_aside_requested") == [
            {
                "id": str(copy.pk),
                "hub": str(hub.pk),
                "slug": "acme",
                "from": str(source.pk),
                "at": self.MOMENT.isoformat(),
                "database": copy.db_name,
            }
        ]

    def test_two_copies_of_one_hub_have_two_names(self, admin_ctx, small):
        from control.models import RestoredCopy

        hub, source = self.a_hub(), self.temporary()

        self.ask(admin_ctx, hub, source)
        self.ask(admin_ctx, hub, source, at=self.MOMENT - dt.timedelta(hours=1))

        assert len(set(RestoredCopy.objects.values_list("db_name", flat=True))) == 2

    def test_the_temporary_cluster_is_kept_while_its_copy_is_made_and_the_hubs_while_the_copy_is_on_it(
        self, admin_ctx, small
    ):
        from control.models import RestoredCopy

        own, source = a_cluster(), self.temporary()
        hub = self.a_hub(cluster=own)
        self.ask(admin_ctx, hub, source)
        # The hub went elsewhere since: on its old cluster only the copy is left.
        Hub.objects.filter(pk=hub.pk).update(cluster=a_cluster(name="cluster-2", host="writer-2.example"))
        for cluster in (source, own):
            with pytest.raises(Conflict) as refused:
                services.cluster_delete(admin_ctx, ClusterIdIn(id=cluster.pk))
            assert refused.value.code == "control.cluster_holds_hubs"
        # Made, the copy no longer needs the temporary cluster: it may go; the hub's old one still holds the copy.
        RestoredCopy.objects.update(status=RestoredCopy.Status.MADE, made_at=timezone.now(), source=None)
        services.cluster_delete(admin_ctx, ClusterIdIn(id=source.pk))
        assert not Cluster.objects.filter(pk=source.pk).exists()
        with pytest.raises(Conflict) as refused:
            services.cluster_delete(admin_ctx, ClusterIdIn(id=own.pk))
        assert refused.value.code == "control.cluster_holds_hubs"

    def test_the_copy_aside_is_an_internal_command_of_control(self):
        from live.operations import INTERNAL
        from live.operations import get as get_operation

        op = get_operation("control.hub.restore_aside")
        assert (op.kind, op.app_label, op.ai_spec(), op.fn.__module__) == (
            "command",
            "control",
            INTERNAL,
            "control.services",
        )
