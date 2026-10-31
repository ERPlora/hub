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

    def test_its_writer_changes_while_it_holds_none_but_purged_demos(self, admin_ctx):
        cluster = a_cluster()
        Hub.objects.create(slug="demo-0000beef", is_demo=True, status=Hub.Status.PURGED, cluster=cluster)

        services.cluster_update(admin_ctx, update_in(cluster, host="writer-9.example", port=5433))

        cluster.refresh_from_db()
        assert (cluster.host, cluster.port) == ("writer-9.example", 5433)

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
