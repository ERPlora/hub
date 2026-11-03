"""The size of the hubs' databases, as the Hub admin shows it (round 2026-10-30b of PLAN-DB, decision 1; tranche S7).

``control.cluster.sizes`` measures, with ``pg_database_size`` over the catalogue, the own databases of the hubs on one
cluster, never opening any of them: on the settings' own server (no cluster) through control's own connection, on a
cluster through one short direct connection to its maintenance database ``postgres`` on its writer, as its app's role
(``base.tenancy.credentials``: the web has no other). A hub that shares control's database, and a purged one, have
none to measure. What it measured is kept ten minutes in the cache (Valkey in AWS), each database on its own, so a new
hub is measured on the next look without measuring the others again; a cache that does not answer only costs a
measure. A cluster that cannot be reached, or whose secret does not resolve, is a readable failure with its reason.
For the platform's staff (support included: it only reads) and the platform itself.
"""

import json
import uuid

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connections
from live.context import OperationContext, system_context
from live.errors import NotFound, OperationError, PermissionDenied

from base.registry import REGISTRY_SCOPE
from base.tenancy import credentials
from base.tenancy.connections import hub_alias
from control import queries
from control.models import Cluster, Hub
from control.schemas import ClusterSizesIn

pytestmark = pytest.mark.django_db

SECRET = "erplora/test/clusters/local"


@pytest.fixture(autouse=True)
def nothing_kept():
    credentials.forget()
    cache.clear()
    yield
    credentials.forget()
    cache.clear()


def as_actor(actor) -> OperationContext:
    return OperationContext(scope=REGISTRY_SCOPE, actor=actor, permissions=frozenset(), language="en")


@pytest.fixture
def staff_ctx():
    support = get_user_model().objects.create_user(username="support", password="pw", is_staff=True)
    return as_actor(support)


def local_cluster(**fields) -> Cluster:
    """A cluster row on this test's own server: its writer is the default connection's."""
    default = settings.DATABASES["default"]
    return Cluster.objects.create(**({"name": "local", "host": default["HOST"], "port": default["PORT"]} | fields))


def hub_on(db_name: str, *, cluster: Cluster | None = None, slug: str | None = None, **fields) -> Hub:
    row = {"slug": slug or f"h{uuid.uuid4().hex[:10]}", "status": Hub.Status.READY, "db_name": db_name, "cluster": cluster}
    return Hub.objects.create(**(row | fields))


@pytest.fixture
def connects(monkeypatch):
    """Every direct connection the query opens, by its libpq parameters (the password left out)."""
    opened: list[dict] = []
    real = queries.psycopg.connect

    def connect(**conninfo):
        opened.append({key: value for key, value in conninfo.items() if key != "password"})
        return real(**conninfo)

    monkeypatch.setattr(queries.psycopg, "connect", connect)
    return opened


class TestTheSettingsOwnServer:
    def test_measures_its_hubs_own_databases_and_opens_none_of_them(self, staff_ctx, hub_databases, connects):
        a, b = hub_on(hub_databases.a), hub_on(hub_databases.b)
        shared = hub_on("")
        hub_on(f"{hub_databases.control}_demo_{'0' * 32}", slug="demo-0000beef", is_demo=True, status=Hub.Status.PURGED)

        out = queries.cluster_sizes(staff_ctx, ClusterSizesIn(cluster=None))

        assert set(out.databases) == {hub_databases.a, hub_databases.b}
        assert all(isinstance(size, int) and size > 0 for size in out.databases.values())
        # Control's own connection: no direct one, and no hub's alias registered on the way.
        assert connects == []
        assert not {hub_alias(a), hub_alias(b), hub_alias(shared)} & set(connections.settings)

    def test_a_database_that_is_not_on_the_server_has_no_size(self, staff_ctx, hub_databases):
        hub_on(hub_databases.a)
        hub_on(f"{hub_databases.control}_{'f' * 32}")

        out = queries.cluster_sizes(staff_ctx, ClusterSizesIn(cluster=None))

        assert set(out.databases) == {hub_databases.a}

    def test_the_hubs_of_a_cluster_are_not_measured_here(self, staff_ctx, hub_databases):
        hub_on(hub_databases.a, cluster=local_cluster())

        assert queries.cluster_sizes(staff_ctx, ClusterSizesIn(cluster=None)).databases == {}


class TestACluster:
    def test_measures_on_its_writers_postgres_as_its_apps_role(self, staff_ctx, hub_databases, connects):
        cluster = local_cluster(pooler_host="pooler.invalid")
        hub_on(hub_databases.a, cluster=cluster)
        hub_on(hub_databases.b)

        out = queries.cluster_sizes(staff_ctx, ClusterSizesIn(cluster=cluster.pk))

        assert set(out.databases) == {hub_databases.a}
        assert out.databases[hub_databases.a] > 0
        default = settings.DATABASES["default"]
        assert [(c["dbname"], c["host"], c["port"], c["user"]) for c in connects] == [
            ("postgres", cluster.host, cluster.port, default["USER"])
        ]

    def test_with_a_secret_its_app_role_is_the_secrets_and_the_migrators_is_never_asked(
        self, staff_ctx, hub_databases, connects, monkeypatch
    ):
        default = settings.DATABASES["default"]
        reads: list[str] = []

        class Secrets:
            def get_secret_value(self, *, SecretId):  # noqa: N803 (boto3's own keyword)
                reads.append(SecretId)
                values = {"app_user": default["USER"], "app_password": default["PASSWORD"]}
                return {"SecretString": json.dumps(values)}

        monkeypatch.setattr(credentials, "secrets_client", Secrets)
        cluster = local_cluster(secret_name=SECRET)
        hub_on(hub_databases.a, cluster=cluster)

        out = queries.cluster_sizes(staff_ctx, ClusterSizesIn(cluster=cluster.pk))

        assert set(out.databases) == {hub_databases.a}
        assert reads == [f"{SECRET}/app"]
        assert [c["user"] for c in connects] == [default["USER"]]

    def test_one_without_hubs_of_its_own_database_is_not_even_reached(self, staff_ctx, connects):
        cluster = local_cluster(host="writer.invalid")
        hub_on("", cluster=cluster)
        hub_on(f"hub_demo_{'0' * 32}", cluster=cluster, slug="demo-0000beef", is_demo=True, status=Hub.Status.PURGED)

        assert queries.cluster_sizes(staff_ctx, ClusterSizesIn(cluster=cluster.pk)).databases == {}
        assert connects == []

    def test_one_that_cannot_be_reached_is_a_readable_failure(self, staff_ctx):
        cluster = local_cluster(host="127.0.0.1", port=1)
        hub_on(f"{connections.settings['default']['NAME']}_{'a' * 32}", cluster=cluster)

        with pytest.raises(OperationError) as failed:
            queries.cluster_sizes(staff_ctx, ClusterSizesIn(cluster=cluster.pk))

        assert (failed.value.code, failed.value.status) == ("control.cluster_unreachable", 503)
        assert "local" in failed.value.message

    def test_one_whose_secret_does_not_resolve_is_a_readable_failure(self, staff_ctx, monkeypatch):
        class Secrets:
            def get_secret_value(self, *, SecretId):  # noqa: N803 (boto3's own keyword)
                raise LookupError("ResourceNotFoundException")

        monkeypatch.setattr(credentials, "secrets_client", Secrets)
        cluster = local_cluster(secret_name=SECRET)
        hub_on(f"{connections.settings['default']['NAME']}_{'a' * 32}", cluster=cluster)

        with pytest.raises(OperationError) as failed:
            queries.cluster_sizes(staff_ctx, ClusterSizesIn(cluster=cluster.pk))

        assert failed.value.code == "control.cluster_unreachable"
        assert f"{SECRET}/app" in failed.value.message

    def test_an_unknown_cluster_is_not_found(self, staff_ctx):
        with pytest.raises(NotFound):
            queries.cluster_sizes(staff_ctx, ClusterSizesIn(cluster=uuid.uuid7()))


class TestKeptTenMinutes:
    def test_a_second_look_measures_nothing_again_and_a_new_hub_alone(self, staff_ctx, hub_databases, monkeypatch):
        measured: list[list[str]] = []
        real = queries.measure

        def measure(cluster, names):
            measured.append(sorted(names))
            return real(cluster, names)

        monkeypatch.setattr(queries, "measure", measure)
        kept: list[int] = []
        real_set_many = cache.set_many
        monkeypatch.setattr(cache, "set_many", lambda values, timeout: (kept.append(timeout), real_set_many(values, timeout)))
        hub_on(hub_databases.a)

        first = queries.cluster_sizes(staff_ctx, ClusterSizesIn(cluster=None))
        again = queries.cluster_sizes(staff_ctx, ClusterSizesIn(cluster=None))
        hub_on(hub_databases.b)
        later = queries.cluster_sizes(staff_ctx, ClusterSizesIn(cluster=None))

        assert first.databases == again.databases
        assert set(later.databases) == {hub_databases.a, hub_databases.b}
        assert measured == [[hub_databases.a], [hub_databases.b]]
        assert kept == [queries.SIZE_TTL_SECONDS, queries.SIZE_TTL_SECONDS] and queries.SIZE_TTL_SECONDS == 600

    def test_the_same_name_on_two_servers_is_kept_apart(self, staff_ctx, hub_databases, monkeypatch):
        measured: list[object] = []
        real = queries.measure

        def measure(cluster, names):
            measured.append(cluster.pk if cluster is not None else None)
            return real(cluster, names)

        monkeypatch.setattr(queries, "measure", measure)
        cluster = local_cluster()
        # While a hub moves (base.hub.move) its database's name is on both servers.
        hub_on(hub_databases.a)
        hub_on(hub_databases.a, cluster=cluster)

        queries.cluster_sizes(staff_ctx, ClusterSizesIn(cluster=None))
        queries.cluster_sizes(staff_ctx, ClusterSizesIn(cluster=cluster.pk))

        assert measured == [None, cluster.pk]

    def test_a_cache_that_does_not_answer_only_costs_a_measure(self, staff_ctx, hub_databases, monkeypatch):
        def away(*args, **kwargs):
            raise ConnectionError("Valkey is away")

        monkeypatch.setattr(cache, "get_many", away)
        monkeypatch.setattr(cache, "set_many", away)
        hub_on(hub_databases.a)

        assert set(queries.cluster_sizes(staff_ctx, ClusterSizesIn(cluster=None)).databases) == {hub_databases.a}


class TestWhoMayLook:
    def test_the_platform_may(self, hub_databases):
        hub_on(hub_databases.a)

        out = queries.cluster_sizes(system_context(REGISTRY_SCOPE), ClusterSizesIn(cluster=None))

        assert set(out.databases) == {hub_databases.a}

    def test_a_customer_may_not(self):
        customer = get_user_model().objects.create_user(username="ana", password="pw")

        with pytest.raises(PermissionDenied):
            queries.cluster_sizes(as_actor(customer), ClusterSizesIn(cluster=None))


def test_it_is_an_internal_query_of_control():
    from live.operations import INTERNAL
    from live.operations import get as get_operation

    op = get_operation("control.cluster.sizes")
    assert (op.kind, op.app_label, op.ai_spec(), op.fn.__module__) == ("query", "control", INTERNAL, "control.queries")
