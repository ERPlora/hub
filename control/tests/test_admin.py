"""The Hub admin of control: the database clusters and the hubs with their database (round 2026-10-30b of PLAN-DB,
decision 1 of Ioan; tranche S7, part 1).

Admin › Clusters lists each cluster with its writer, its PgBouncer, whether it is open, its limit, the hubs on it
against that limit, its secret and the total size of its hubs' databases, and its every write is an operation
(``control.cluster.create``/``update``/``close``/``delete``): the form shows what the operation refused on its field
(a secret that does not resolve, a writer under its hubs), «Close to new hubs» closes the chosen ones, and one that
holds hubs is never deleted. Admin › Hubs adds to the registry's columns (``base.admin``) each hub's database, cluster,
schema and size (``control.cluster.sizes``, one measure per cluster and page), with filters by cluster and status.
Only the platform's admins (staff and superuser) change anything; support reads. On the platform host only.
"""

import json
import re

import pytest
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth import get_user_model
from live.models import OutboxEvent

from base import admin as base_admin
from base.tenancy import credentials
from control import admin as control_admin
from control.models import Cluster, Hub

pytestmark = pytest.mark.django_db
PLATFORM = "hubs.localhost:8000"
CLUSTERS = "/admin/control/cluster/"
HUBS = "/admin/control/hub/"
SECRET = "erplora/prod/clusters/cluster-2"
SIZE = re.compile(r"\d[\d.,]*\s(?:bytes|KB|MB|GB)")


@pytest.fixture(autouse=True)
def nothing_kept():
    from django.core.cache import cache

    credentials.forget()
    cache.clear()
    yield
    credentials.forget()
    cache.clear()


@pytest.fixture
def root(client):
    user = get_user_model().objects.create_superuser(username="root", password="pw", email="root@example.com")
    client.force_login(user)
    return user


@pytest.fixture
def support(client):
    from base import services

    user = get_user_model().objects.create_user(username="support", password="pw", is_staff=True)
    user.groups.add(services._support_group())
    client.force_login(user)
    return user


@pytest.fixture
def secrets(monkeypatch):
    found: dict[str, object] = {f"{SECRET}/app": {"app_user": "hub_app", "app_password": "app-secret"}}

    class Secrets:
        def get_secret_value(self, *, SecretId):  # noqa: N803 (boto3's own keyword)
            if SecretId not in found:
                raise LookupError(f"ResourceNotFoundException: {SecretId}")
            return {"SecretString": json.dumps(found[SecretId])}

    monkeypatch.setattr(credentials, "secrets_client", Secrets)
    return found


def local_cluster(**fields) -> Cluster:
    """A cluster on this test's own server (its writer is the default connection's)."""
    default = settings.DATABASES["default"]
    return Cluster.objects.create(**({"name": "local", "host": default["HOST"], "port": default["PORT"]} | fields))


def a_cluster(**fields) -> Cluster:
    return Cluster.objects.create(**({"name": "cluster-1", "host": "writer-1.example"} | fields))


def form(cluster: Cluster | None = None, **changes) -> dict:
    fields = {
        "name": "cluster-2",
        "host": "writer-2.example",
        "port": "5432",
        "pooler_host": "pooler-2.example",
        "pooler_port": "6432",
        "is_open": "on",
        "max_hubs": "100",
        "secret_name": "",
    }
    if cluster is not None:
        fields |= {
            "name": cluster.name,
            "host": cluster.host,
            "port": str(cluster.port),
            "pooler_host": cluster.pooler_host,
            "pooler_port": str(cluster.pooler_port),
            "max_hubs": str(cluster.max_hubs),
            "secret_name": cluster.secret_name,
        }
        if not cluster.is_open:
            del fields["is_open"]
    return {key: value for key, value in (fields | changes).items() if value is not None} | {"_save": "Save"}


def events(name: str) -> list[dict]:
    return [event.payload for event in OutboxEvent.objects.filter(name=name)]


def page(client, url: str, **params) -> str:
    response = client.get(url, params, HTTP_HOST=PLATFORM)
    assert response.status_code == 200
    return response.content.decode()


def row_of(html: str, text: str) -> str:
    """The changelist's row (``<tr>…</tr>``) that says ``text``."""
    [row] = [row for row in re.findall(r"<tr.*?</tr>", html, re.S) if text in row]
    return row


class TestClusters:
    def test_is_registered(self):
        assert isinstance(admin.site._registry[Cluster], control_admin.ClusterAdmin)

    def test_lists_each_with_its_doors_limit_hubs_secret_and_total_size(self, client, root, hub_databases):
        cluster = local_cluster(pooler_host="pooler-1.example", max_hubs=100)
        Hub.objects.create(slug="acme", status=Hub.Status.READY, cluster=cluster, db_name=hub_databases.a)
        Hub.objects.create(slug="demo-0000beef", is_demo=True, status=Hub.Status.PURGED, cluster=cluster)
        # Its secret is never read for the list: it holds no hub's database to measure.
        a_cluster(is_open=False, secret_name="erplora/x/clusters/one")
        default = settings.DATABASES["default"]

        html = page(client, CLUSTERS)

        local = row_of(html, ">local<")
        assert f"{default['HOST']}:{default['PORT']}" in local and "pooler-1.example:6432" in local
        assert "1 / 100" in local and "icon-yes" in local
        assert SIZE.search(local)
        other = row_of(html, ">cluster-1<")
        assert "0 / no limit" in other and "writer-1.example:5432" in other and "icon-no" in other
        assert "erplora/x/clusters/one" in other and not SIZE.search(other)

    def test_one_that_cannot_be_measured_says_why_and_the_page_still_answers(self, client, root):
        cluster = a_cluster(host="127.0.0.1", port=1)
        Hub.objects.create(slug="acme", status=Hub.Status.READY, cluster=cluster, db_name="hub_" + "a" * 32)

        html = page(client, CLUSTERS)

        assert "The sizes of the databases on cluster-1 could not be read" in html

    def test_a_new_one_is_registered_through_its_operation(self, client, root):
        response = client.post(f"{CLUSTERS}add/", form(), HTTP_HOST=PLATFORM)

        assert response.status_code == 302
        cluster = Cluster.objects.get(name="cluster-2")
        assert (cluster.host, cluster.pooler_host, cluster.max_hubs, cluster.is_open) == (
            "writer-2.example",
            "pooler-2.example",
            100,
            True,
        )
        assert events("control.cluster.created") == [{"id": str(cluster.pk), "name": "cluster-2"}]
        assert LogEntry.objects.filter(object_id=str(cluster.pk), action_flag=ADDITION).exists()

    def test_a_secret_that_does_not_resolve_is_shown_on_its_field_and_nothing_is_saved(self, client, root, secrets):
        response = client.post(f"{CLUSTERS}add/", form(secret_name="erplora/prod/clusters/nope"), HTTP_HOST=PLATFORM)

        html = response.content.decode()
        assert response.status_code == 200
        assert "erplora/prod/clusters/nope/app" in html and "errorlist" in html
        assert not Cluster.objects.exists()

    def test_a_secret_that_resolves_is_kept(self, client, root, secrets):
        client.post(f"{CLUSTERS}add/", form(secret_name=SECRET), HTTP_HOST=PLATFORM)

        assert Cluster.objects.get(name="cluster-2").secret_name == SECRET

    def test_an_edit_goes_through_its_operation(self, client, root):
        cluster = a_cluster(max_hubs=10)

        response = client.post(f"{CLUSTERS}{cluster.pk}/change/", form(cluster, max_hubs="500"), HTTP_HOST=PLATFORM)

        assert response.status_code == 302
        cluster.refresh_from_db()
        assert cluster.max_hubs == 500
        assert events("control.cluster.updated") == [{"id": str(cluster.pk), "name": "cluster-1"}]
        assert LogEntry.objects.filter(object_id=str(cluster.pk), action_flag=CHANGE).exists()

    def test_its_writer_never_changes_under_its_hubs(self, client, root):
        cluster = a_cluster()
        Hub.objects.create(slug="acme", status=Hub.Status.READY, cluster=cluster)

        response = client.post(
            f"{CLUSTERS}{cluster.pk}/change/", form(cluster, host="writer-9.example"), HTTP_HOST=PLATFORM
        )

        assert response.status_code == 200 and "errorlist" in response.content.decode()
        assert "move them" in response.content.decode()
        cluster.refresh_from_db()
        assert cluster.host == "writer-1.example"

    def test_close_to_new_hubs_closes_the_chosen_ones_and_says_so(self, client, root):
        first, second = a_cluster(), a_cluster(name="cluster-2", host="writer-2.example")
        untouched = a_cluster(name="cluster-3", host="writer-3.example")

        response = client.post(
            CLUSTERS,
            {"action": "close_to_new_hubs", "_selected_action": [str(first.pk), str(second.pk)]},
            HTTP_HOST=PLATFORM,
            follow=True,
        )

        assert "2 clusters closed to new hubs" in response.content.decode()
        for cluster in (first, second, untouched):
            cluster.refresh_from_db()
        assert (first.is_open, second.is_open, untouched.is_open) == (False, False, True)
        assert len(events("control.cluster.closed")) == 2

    def test_one_that_holds_hubs_is_not_deleted(self, client, root):
        cluster = a_cluster()
        Hub.objects.create(slug="acme", status=Hub.Status.READY, cluster=cluster)

        response = client.post(f"{CLUSTERS}{cluster.pk}/delete/", {"post": "yes"}, HTTP_HOST=PLATFORM)

        html = response.content.decode()
        # The hubs are what stops it (the foreign key protects it), not a permission to delete them.
        assert response.status_code == 200 and "protected related objects" in html and "acme" in html
        assert "permission to delete" not in html
        assert Cluster.objects.filter(pk=cluster.pk).exists()
        assert events("control.cluster.deleted") == []

    def test_one_without_hubs_is_deleted_through_its_operation(self, client, root):
        cluster = a_cluster()

        response = client.post(f"{CLUSTERS}{cluster.pk}/delete/", {"post": "yes"}, HTTP_HOST=PLATFORM)

        assert response.status_code == 302
        assert not Cluster.objects.exists()
        assert events("control.cluster.deleted") == [{"id": str(cluster.pk), "name": "cluster-1"}]

    def test_the_bulk_delete_goes_through_its_operation_too(self, client, root):
        first, second = a_cluster(), a_cluster(name="cluster-2", host="writer-2.example")

        client.post(
            CLUSTERS,
            {"action": "delete_selected", "_selected_action": [str(first.pk), str(second.pk)], "post": "yes"},
            HTTP_HOST=PLATFORM,
        )

        assert not Cluster.objects.exists()
        assert len(events("control.cluster.deleted")) == 2

    def test_a_refusal_between_the_check_and_the_delete_is_said_and_logs_nothing(self, client, root, monkeypatch):
        from live.errors import Conflict

        cluster = a_cluster()

        def refused(ctx, data):
            raise Conflict("A hub was just placed on cluster-1.", code="control.cluster_holds_hubs")

        monkeypatch.setattr(control_admin, "cluster_delete", refused)

        response = client.post(f"{CLUSTERS}{cluster.pk}/delete/", {"post": "yes"}, HTTP_HOST=PLATFORM, follow=True)

        assert "A hub was just placed on cluster-1." in response.content.decode()
        assert Cluster.objects.filter(pk=cluster.pk).exists()
        assert not LogEntry.objects.filter(object_id=str(cluster.pk)).exists()

    def test_support_reads_and_changes_nothing(self, client, support):
        cluster = a_cluster()

        html = page(client, CLUSTERS)
        assert "cluster-1" in html and "close_to_new_hubs" not in html and f"{CLUSTERS}add/" not in html
        client.post(CLUSTERS, {"action": "close_to_new_hubs", "_selected_action": [str(cluster.pk)]}, HTTP_HOST=PLATFORM)
        client.post(f"{CLUSTERS}{cluster.pk}/change/", form(cluster, max_hubs="5"), HTTP_HOST=PLATFORM)
        assert client.post(f"{CLUSTERS}add/", form(), HTTP_HOST=PLATFORM).status_code == 403
        assert client.post(f"{CLUSTERS}{cluster.pk}/delete/", {"post": "yes"}, HTTP_HOST=PLATFORM).status_code == 403
        cluster.refresh_from_db()
        assert (cluster.is_open, cluster.max_hubs, Cluster.objects.count()) == (True, 0, 1)


class TestHubs:
    def test_is_controls_and_keeps_the_registrys_columns_and_actions(self):
        registered = admin.site._registry[Hub]
        assert isinstance(registered, control_admin.HubAdmin) and isinstance(registered, base_admin.HubAdmin)
        assert "expire_now" in registered.actions

    def test_lists_each_with_its_database_cluster_schema_and_size(self, client, root, hub_databases):
        cluster = local_cluster()
        Hub.objects.create(
            slug="acme", status=Hub.Status.READY, cluster=cluster, db_name=hub_databases.a, schema_state="behind"
        )
        Hub.objects.create(slug="corner", status=Hub.Status.READY, db_name=hub_databases.b)

        html = page(client, HUBS)

        acme = row_of(html, ">acme<")
        assert hub_databases.a in acme and ">local<" in acme and "Behind" in acme and SIZE.search(acme)
        corner = row_of(html, ">corner<")
        assert hub_databases.b in corner and SIZE.search(corner)
        shared = row_of(html, ">a<")
        assert "shared with control" in shared and not SIZE.search(shared)

    def test_measures_once_per_cluster_on_the_page(self, client, root, hub_databases, monkeypatch):
        calls: list[object] = []
        real = control_admin.cluster_sizes

        def counted(ctx, data):
            calls.append(data.cluster)
            return real(ctx, data)

        monkeypatch.setattr(control_admin, "cluster_sizes", counted)
        cluster = local_cluster()
        for slug, db_name in (("acme", hub_databases.a), ("bistro", hub_databases.b)):
            Hub.objects.create(slug=slug, status=Hub.Status.READY, cluster=cluster, db_name=db_name)

        page(client, HUBS)

        assert sorted(calls, key=str) == sorted([cluster.pk], key=str)

    def test_a_cluster_that_cannot_be_measured_says_why_and_the_page_still_answers(self, client, root):
        cluster = a_cluster(host="127.0.0.1", port=1)
        Hub.objects.create(slug="acme", status=Hub.Status.READY, cluster=cluster, db_name="hub_" + "a" * 32)

        html = page(client, HUBS)

        assert "The sizes of the databases on cluster-1 could not be read" in html
        assert not SIZE.search(row_of(html, ">acme<"))

    def test_filters_by_cluster_and_status(self, client, root):
        cluster = a_cluster()
        Hub.objects.create(slug="acme", status=Hub.Status.READY, cluster=cluster)
        Hub.objects.create(slug="bistro", status=Hub.Status.CANCELLED, cluster=cluster)

        on_it = page(client, HUBS, cluster__id__exact=str(cluster.pk))
        assert ">acme<" in on_it and ">bistro<" in on_it and ">a<" not in on_it
        on_none = page(client, HUBS, cluster__isnull="True")
        assert ">a<" in on_none and ">acme<" not in on_none
        ready_on_it = page(client, HUBS, cluster__id__exact=str(cluster.pk), status__exact="ready")
        assert ">acme<" in ready_on_it and ">bistro<" not in ready_on_it


def test_its_words_are_translated():
    from django.utils import translation

    with translation.override("es"):
        assert str(control_admin.ClusterAdmin.close_to_new_hubs.short_description) == "Cerrar a hubs nuevos"
        assert control_admin.no_limit() == "sin límite"
