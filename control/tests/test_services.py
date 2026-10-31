"""The database clusters, written through their operations (round 2026-10-30b of PLAN-DB, decision 1; tranche S7).

The Hub admin (``hubs.erplora.com/admin``) is where a cluster is registered, edited, closed to new hubs or deleted,
and each of those is a ``control.cluster.*`` command (``control/admin.py`` only calls them): for the platform's admins
(staff and superuser) or the platform itself, never for support (it only reads) nor a customer. A cluster with a
``secret_name`` is saved only once its app's secret (``…/app``, the one the web may read, aws#23) resolves through
``base.tenancy.credentials.credentials_for``; the migrator's is never asked from here. «Close to new hubs» leaves its
hubs where they are; a cluster that holds hubs is never deleted, and its writer never changes under them (that is a
move, ``base.hub.move``). Each write records its event in control's outbox, in the same transaction.
"""

import json
import uuid

import pytest
from django.contrib.auth import get_user_model
from live.context import OperationContext, system_context
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from base.registry import REGISTRY_SCOPE
from base.tenancy import credentials
from control import services
from control.models import Cluster, Hub
from control.schemas import ClusterIdIn, ClusterIn, ClusterUpdateIn

pytestmark = pytest.mark.django_db

SECRET = "erplora/prod/clusters/cluster-2"
APP_VALUES = {"app_user": "hub_app", "app_password": "app-secret"}


class FakeSecrets:
    """Secrets Manager's ``get_secret_value`` over a dict; counts the reads; a missing one is the service's error."""

    def __init__(self, secrets: dict[str, object]):
        self.secrets = secrets
        self.reads: list[str] = []

    def get_secret_value(self, *, SecretId: str) -> dict:  # noqa: N803 (boto3's own keyword)
        self.reads.append(SecretId)
        if SecretId not in self.secrets:
            raise LookupError(f"ResourceNotFoundException: Secrets Manager can't find the specified secret {SecretId}.")
        found = self.secrets[SecretId]
        return {"Name": SecretId, "SecretString": found if isinstance(found, str) else json.dumps(found)}


@pytest.fixture(autouse=True)
def nothing_cached():
    credentials.forget()
    yield
    credentials.forget()


@pytest.fixture
def secrets(monkeypatch):
    fake = FakeSecrets({f"{SECRET}/app": APP_VALUES})
    monkeypatch.setattr(credentials, "secrets_client", lambda: fake)
    return fake


def person(username: str, **flags):
    return get_user_model().objects.create_user(username=username, password="pw", **flags)


def as_actor(actor) -> OperationContext:
    return OperationContext(scope=REGISTRY_SCOPE, actor=actor, permissions=frozenset(), language="en")


@pytest.fixture
def admin_ctx():
    return as_actor(person("root", is_staff=True, is_superuser=True))


def cluster_in(**changes) -> ClusterIn:
    fields = {
        "name": "cluster-2",
        "host": "writer-2.example",
        "port": 5432,
        "pooler_host": "pooler-2.example",
        "pooler_port": 6432,
        "is_open": True,
        "max_hubs": 100,
        "secret_name": "",
    }
    return ClusterIn(**(fields | changes))


def update_in(cluster: Cluster, **changes) -> ClusterUpdateIn:
    fields = {
        "id": cluster.pk,
        "name": cluster.name,
        "host": cluster.host,
        "port": cluster.port,
        "pooler_host": cluster.pooler_host,
        "pooler_port": cluster.pooler_port,
        "is_open": cluster.is_open,
        "max_hubs": cluster.max_hubs,
        "secret_name": cluster.secret_name,
    }
    return ClusterUpdateIn(**(fields | changes))


def a_cluster(**fields) -> Cluster:
    return Cluster.objects.create(**({"name": "cluster-1", "host": "writer-1.example"} | fields))


def events(name: str) -> list[dict]:
    return [event.payload for event in OutboxEvent.objects.filter(name=name).order_by("created_at")]


class TestCreate:
    def test_a_platform_admin_registers_a_cluster_with_its_limit_and_its_event(self, admin_ctx):
        out = services.cluster_create(admin_ctx, cluster_in())

        row = Cluster.objects.get(pk=out.id)
        assert (row.name, row.host, row.port, row.pooler_host, row.pooler_port, row.is_open, row.max_hubs) == (
            "cluster-2",
            "writer-2.example",
            5432,
            "pooler-2.example",
            6432,
            True,
            100,
        )
        assert (out.name, out.max_hubs, out.hubs) == ("cluster-2", 100, 0)
        assert events("control.cluster.created") == [{"id": str(row.pk), "name": "cluster-2"}]

    def test_the_platform_itself_may_register_one(self):
        out = services.cluster_create(system_context(REGISTRY_SCOPE), cluster_in())

        assert Cluster.objects.filter(pk=out.id).exists()

    @pytest.mark.parametrize("flags", [{"is_staff": True}, {}, {"is_superuser": True}])
    def test_support_a_customer_or_a_superuser_who_is_no_staff_may_not(self, flags):
        with pytest.raises(PermissionDenied):
            services.cluster_create(as_actor(person("someone", **flags)), cluster_in())

        assert not Cluster.objects.exists()

    def test_a_name_taken_is_refused_on_its_field(self, admin_ctx):
        a_cluster(name="cluster-2")

        with pytest.raises(Conflict) as refused:
            services.cluster_create(admin_ctx, cluster_in())

        assert refused.value.code == "control.cluster_name_taken"
        assert set(refused.value.fields) == {"name"}
        assert Cluster.objects.count() == 1

    def test_its_secret_is_read_before_it_is_saved_and_only_the_apps(self, admin_ctx, secrets):
        out = services.cluster_create(admin_ctx, cluster_in(secret_name=SECRET))

        assert Cluster.objects.get(pk=out.id).secret_name == SECRET
        assert secrets.reads == [f"{SECRET}/app"]

    @pytest.mark.parametrize(
        ("stored", "reason"),
        [(None, "could not be read"), ("not json", "no JSON object"), ({"app_user": "hub_app"}, "lacks app_password")],
    )
    def test_a_secret_that_does_not_resolve_is_refused_on_its_field_and_nothing_is_saved(
        self, admin_ctx, monkeypatch, stored, reason
    ):
        fake = FakeSecrets({} if stored is None else {f"{SECRET}/app": stored})
        monkeypatch.setattr(credentials, "secrets_client", lambda: fake)

        with pytest.raises(InvalidPayload) as refused:
            services.cluster_create(admin_ctx, cluster_in(secret_name=SECRET))

        assert refused.value.code == "control.cluster_secret_unavailable"
        assert reason in refused.value.fields["secret_name"]
        assert f"{SECRET}/app" in refused.value.fields["secret_name"]
        assert not Cluster.objects.exists()
        assert events("control.cluster.created") == []

    def test_its_fields_keep_the_models_bounds(self):
        for bad in ({"name": ""}, {"host": " "}, {"port": 0}, {"pooler_port": 70000}, {"max_hubs": -1}):
            with pytest.raises(ValueError):
                cluster_in(**bad)


class TestUpdate:
    def test_changes_its_limit_its_door_and_its_secret_with_its_event(self, admin_ctx, secrets):
        cluster = a_cluster(max_hubs=10)

        out = services.cluster_update(
            admin_ctx, update_in(cluster, max_hubs=500, pooler_host="pooler-1b.example", secret_name=SECRET)
        )

        cluster.refresh_from_db()
        assert (cluster.max_hubs, cluster.pooler_host, cluster.secret_name) == (500, "pooler-1b.example", SECRET)
        assert (out.id, out.max_hubs) == (cluster.pk, 500)
        assert events("control.cluster.updated") == [{"id": str(cluster.pk), "name": "cluster-1"}]

    def test_a_new_secret_that_does_not_resolve_is_refused(self, admin_ctx, monkeypatch):
        cluster = a_cluster()
        fake = FakeSecrets({})
        monkeypatch.setattr(credentials, "secrets_client", lambda: fake)

        with pytest.raises(InvalidPayload) as refused:
            services.cluster_update(admin_ctx, update_in(cluster, secret_name=SECRET, max_hubs=7))

        assert refused.value.code == "control.cluster_secret_unavailable"
        cluster.refresh_from_db()
        assert (cluster.secret_name, cluster.max_hubs) == ("", 0)

    def test_a_secret_it_already_had_is_not_read_again_for_another_change(self, admin_ctx, monkeypatch):
        cluster = a_cluster(secret_name=SECRET)
        fake = FakeSecrets({})
        monkeypatch.setattr(credentials, "secrets_client", lambda: fake)

        services.cluster_update(admin_ctx, update_in(cluster, max_hubs=7))

        assert fake.reads == []
        cluster.refresh_from_db()
        assert cluster.max_hubs == 7

    def test_a_name_another_cluster_has_is_refused(self, admin_ctx):
        a_cluster(name="cluster-2", host="writer-2.example")
        cluster = a_cluster()

        with pytest.raises(Conflict) as refused:
            services.cluster_update(admin_ctx, update_in(cluster, name="cluster-2"))

        assert (refused.value.code, set(refused.value.fields)) == ("control.cluster_name_taken", {"name"})

    @pytest.mark.parametrize("change", [{"host": "writer-9.example"}, {"port": 5433}])
    def test_the_writer_of_a_cluster_that_holds_hubs_never_changes_under_them(self, admin_ctx, change):
        cluster = a_cluster()
        Hub.objects.create(slug="acme", status=Hub.Status.READY, cluster=cluster)

        with pytest.raises(Conflict) as refused:
            services.cluster_update(admin_ctx, update_in(cluster, **change))

        assert refused.value.code == "control.cluster_holds_hubs"
        assert set(refused.value.fields) == set(change)
        cluster.refresh_from_db()
        assert (cluster.host, cluster.port) == ("writer-1.example", 5432)

    @pytest.mark.parametrize("held_by", ["a hub on its way", "a moved copy", "a leftover of an undone move"])
    def test_its_writer_never_changes_under_what_is_coming_or_kept_there(self, admin_ctx, held_by):
        from control.models import LeftoverDatabase, MovedCopy

        cluster = a_cluster()
        hub = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}")
        if held_by == "a hub on its way":
            Hub.objects.filter(pk=hub.pk).update(moving_to=cluster)
        elif held_by == "a moved copy":
            MovedCopy.objects.create(hub=hub, cluster=cluster, db_name=f"hub_move_{hub.id.hex}", moved_at="2026-10-31T10:00Z")
        else:
            LeftoverDatabase.objects.create(hub=hub, cluster=cluster, db_name=hub.db_name, noted_at="2026-10-31T10:00Z")

        with pytest.raises(Conflict) as refused:
            services.cluster_update(admin_ctx, update_in(cluster, host="writer-9.example"))

        assert refused.value.code == "control.cluster_holds_hubs"

    def test_its_writer_changes_while_it_holds_none_but_purged_demos(self, admin_ctx):
        cluster = a_cluster()
        Hub.objects.create(slug="demo-0000beef", is_demo=True, status=Hub.Status.PURGED, cluster=cluster)

        services.cluster_update(admin_ctx, update_in(cluster, host="writer-9.example", port=5433))

        cluster.refresh_from_db()
        assert (cluster.host, cluster.port) == ("writer-9.example", 5433)

    def test_nothing_changed_writes_nothing_and_reads_no_secret(self, admin_ctx, monkeypatch):
        cluster = a_cluster(secret_name=SECRET)
        fake = FakeSecrets({})
        monkeypatch.setattr(credentials, "secrets_client", lambda: fake)

        out = services.cluster_update(admin_ctx, update_in(cluster))

        assert (out.id, out.secret_name, fake.reads) == (cluster.pk, SECRET, [])
        assert events("control.cluster.updated") == []

    def test_an_unknown_cluster_is_not_found(self, admin_ctx):
        ghost = Cluster(id=uuid.uuid7(), name="ghost", host="nowhere.example")

        with pytest.raises(NotFound):
            services.cluster_update(admin_ctx, update_in(ghost))

    def test_support_may_not(self):
        cluster = a_cluster()

        with pytest.raises(PermissionDenied):
            services.cluster_update(as_actor(person("support", is_staff=True)), update_in(cluster, max_hubs=1))


class TestClose:
    def test_closes_it_to_new_hubs_and_leaves_its_hubs_where_they_are(self, admin_ctx):
        cluster = a_cluster()
        hub = Hub.objects.create(slug="acme", status=Hub.Status.READY, cluster=cluster)
        # A purged demo has no database left there: not counted among its hubs.
        Hub.objects.create(slug="demo-0000beef", is_demo=True, status=Hub.Status.PURGED, cluster=cluster)

        out = services.cluster_close(admin_ctx, ClusterIdIn(id=cluster.pk))

        cluster.refresh_from_db()
        hub.refresh_from_db()
        assert (cluster.is_open, out.is_open, out.hubs, hub.cluster_id) == (False, False, 1, cluster.pk)
        assert events("control.cluster.closed") == [{"id": str(cluster.pk), "name": "cluster-1"}]

    def test_a_closed_one_stays_closed_and_says_nothing_new(self, admin_ctx):
        cluster = a_cluster(is_open=False)

        services.cluster_close(admin_ctx, ClusterIdIn(id=cluster.pk))

        assert events("control.cluster.closed") == []

    def test_support_may_not_and_an_unknown_one_is_not_found(self, admin_ctx):
        cluster = a_cluster()
        with pytest.raises(PermissionDenied):
            services.cluster_close(as_actor(person("support", is_staff=True)), ClusterIdIn(id=cluster.pk))
        with pytest.raises(NotFound):
            services.cluster_close(admin_ctx, ClusterIdIn(id=uuid.uuid7()))
        cluster.refresh_from_db()
        assert cluster.is_open


class TestDelete:
    def test_deletes_one_without_hubs_with_its_event(self, admin_ctx):
        cluster = a_cluster()

        out = services.cluster_delete(admin_ctx, ClusterIdIn(id=cluster.pk))

        assert out.id == cluster.pk
        assert not Cluster.objects.exists()
        assert events("control.cluster.deleted") == [{"id": str(cluster.pk), "name": "cluster-1"}]

    def test_one_that_holds_hubs_is_never_deleted_even_purged_ones(self, admin_ctx):
        cluster = a_cluster()
        Hub.objects.create(slug="acme", status=Hub.Status.CANCELLED, cluster=cluster)
        Hub.objects.create(slug="demo-0000beef", is_demo=True, status=Hub.Status.PURGED, cluster=cluster)

        with pytest.raises(Conflict) as refused:
            services.cluster_delete(admin_ctx, ClusterIdIn(id=cluster.pk))

        assert refused.value.code == "control.cluster_holds_hubs"
        assert "2" in refused.value.message
        assert Cluster.objects.filter(pk=cluster.pk).exists()
        assert events("control.cluster.deleted") == []

    def test_support_may_not_and_an_unknown_one_is_not_found(self, admin_ctx):
        cluster = a_cluster()
        with pytest.raises(PermissionDenied):
            services.cluster_delete(as_actor(person("support", is_staff=True)), ClusterIdIn(id=cluster.pk))
        with pytest.raises(NotFound):
            services.cluster_delete(admin_ctx, ClusterIdIn(id=uuid.uuid7()))
        assert Cluster.objects.filter(pk=cluster.pk).exists()


def test_every_write_is_an_internal_command_of_control():
    from live.operations import INTERNAL
    from live.operations import get as get_operation

    for name in ("control.cluster.create", "control.cluster.update", "control.cluster.close", "control.cluster.delete"):
        op = get_operation(name)
        assert (op.kind, op.app_label, op.ai_spec(), op.fn.__module__) == ("command", "control", INTERNAL, "control.services")


# ── A hub's move to another cluster (round 2026-10-30b of PLAN-DB, decision 3; tranche S7) ──────────────────────────


class TestMove:
    """``control.hub.move`` asks the worker to move a ready hub's own database to another cluster (``base.tenancy.move``):
    its host answers 503 «maintenance» from now until the worker is done. Only an open cluster with room takes it, the
    way a new hub is placed; a database too large for a copy (``MOVE_MAX_BYTES``) waits for logical replication."""

    @pytest.fixture
    def small(self, monkeypatch):
        """The hub's database measures 5 MB on its server (``control.queries._measure``)."""
        from control import queries

        measured: list[tuple[object, list[str]]] = []

        def measure(cluster, names):
            measured.append((cluster, names))
            return {name: 5 * 1024 * 1024 for name in names}

        monkeypatch.setattr(queries, "_measure", measure)
        return measured

    @staticmethod
    def a_hub(**fields) -> Hub:
        row = {"slug": "acme", "status": Hub.Status.READY, "db_name": f"hub_{uuid.uuid7().hex}"}
        return Hub.objects.create(**(row | fields))

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

    def test_a_database_too_large_for_a_copy_waits_for_logical_replication(self, admin_ctx, monkeypatch):
        from control import queries
        from control.schemas import HubMoveIn

        new = a_cluster()
        hub = self.a_hub()
        monkeypatch.setattr(queries, "_measure", lambda cluster, names: {names[0]: services.MOVE_MAX_BYTES + 1})

        with pytest.raises(Conflict) as refused:
            services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=new.pk))

        assert refused.value.code == "control.hub_too_large"
        hub.refresh_from_db()
        assert hub.moving_to_id is None

    def test_a_database_that_is_not_on_its_server_or_cannot_be_measured_does_not_move(self, admin_ctx, monkeypatch):
        from live.errors import OperationError

        from control import queries
        from control.schemas import HubMoveIn

        new = a_cluster()
        hub = self.a_hub()
        monkeypatch.setattr(queries, "_measure", lambda cluster, names: {})
        with pytest.raises(Conflict) as refused:
            services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=new.pk))
        assert refused.value.code == "control.hub_database_missing"

        def unreachable(cluster, names):
            raise OperationError("The sizes … could not be read: refused", code="control.cluster_unreachable", status=503)

        monkeypatch.setattr(queries, "_measure", unreachable)
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
    """``control.hub.move_cancel`` asks the worker to undo a move, started or not (review of W8, round 2): its note is
    marked to be undone, made if the move had not started, with the origin's schema record; the worker puts the hub back
    on its origin on its next pass (``base.tenancy.move``), the only one that may reopen it."""

    def test_a_move_not_started_yet_is_marked_to_be_undone_with_the_origins_record(self, admin_ctx):
        from control.models import MovedCopy
        from control.schemas import HubIdIn

        old, new = a_cluster(), a_cluster(name="cluster-2", host="writer-2.example")
        hub = Hub.objects.create(
            slug="acme",
            status=Hub.Status.READY,
            db_name=f"hub_{uuid.uuid7().hex}",
            cluster=old,
            moving_to=new,
            schema_state="behind",
            schema_apps={"base": "0001_initial"},
        )

        out = services.hub_move_cancel(admin_ctx, HubIdIn(id=hub.pk))

        [note] = MovedCopy.objects.filter(hub=hub)
        assert (note.cluster_id, note.moved_at, note.undoing) == (old.pk, None, True)
        assert (note.schema_state, note.schema_apps) == ("behind", {"base": "0001_initial"})
        assert note.db_name.endswith(f"_move_{hub.id.hex}")
        hub.refresh_from_db()
        assert hub.moving_to_id == new.pk and hub.last_error.startswith("move_cancelled")
        assert (out.id, out.moving_to) == (hub.pk, new.pk)
        assert events("control.hub.move_cancel_requested") == [{"id": str(hub.pk), "slug": "acme"}]

    def test_a_move_in_course_keeps_its_note_marked_to_be_undone(self, admin_ctx):
        from control.models import MovedCopy
        from control.schemas import HubIdIn

        new = a_cluster()
        hub = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}", moving_to=new)
        MovedCopy.objects.create(hub=hub, db_name=f"hub_move_{hub.id.hex}", schema_state="current", schema_apps={})

        services.hub_move_cancel(admin_ctx, HubIdIn(id=hub.pk))

        [note] = MovedCopy.objects.filter(hub=hub)
        assert (note.undoing, note.schema_state, note.db_name) == (True, "current", f"hub_move_{hub.id.hex}")

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
