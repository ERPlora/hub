"""The Hub admin of control: the database clusters and the hubs with their database.

Admin › Clusters lists each cluster with its writer, its PgBouncer, whether it is open, its limit, the hubs on it
against that limit, its secret and the total size of its hubs' databases, and its every write is an operation
(``control.cluster.create``/``update``/``close``/``delete``): the form shows what the operation refused on its field
(a secret that does not resolve, a writer under its hubs), «Close to new hubs» closes the chosen ones, and one that
holds hubs is never deleted. Admin › Hubs adds to the registry's columns (``base.admin``) each hub's database, cluster,
schema and size (``control.cluster.sizes``, one measure per cluster and page), with filters by cluster and status; a
hub on no cluster says it is on the default server, the settings' own, wherever it has a database.
Only the platform's admins (staff and superuser) change anything; support reads. On the platform host only.
"""

import datetime as dt
import json
import re
import uuid

import pytest
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import capfirst
from live.models import OutboxEvent

from base import admin as base_admin
from base.tenancy import credentials
from control import admin as control_admin
from control.models import Cluster, Freeze, Hub, HubDue

pytestmark = pytest.mark.django_db
PLATFORM = "hubs.localhost:8000"
CLUSTERS = "/admin/control/cluster/"
HUBS = "/admin/control/hub/"
COPIES = "/admin/control/restoredcopy/"
RECOVERIES = "/admin/control/copyrecovery/"
FREEZE = "/admin/control/freeze/"
SECRET = "erplora/prod/clusters/cluster-2"
SIZE = re.compile(r"\d[\d.,]*\s(?:bytes|KB|MB|GB)")
DEFAULT_SERVER = "default server"


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


def cluster_cell(row: str) -> str:
    """What a row of the hubs' changelist says in its cluster column."""
    [cell] = re.findall(r'class="field-on_cluster[^"]*">(.*?)</t[dh]>', row, re.S)
    return cell


def read_only_values(html: str, field: str) -> list[str]:
    """What a hub's own page says in the read-only ``field``: none when the page has no such field."""
    return re.findall(rf'field-{field}\b.*?<div class="readonly">(.*?)</div>', html, re.S)


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
        assert 'class="field-limit">100<' in local
        other = row_of(html, ">cluster-1<")
        assert "0 / no limit" in other and "writer-1.example:5432" in other and "icon-no" in other
        assert 'class="field-limit">no limit<' in other and "none: its writer" in other
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

    def test_what_only_the_operation_bounds_is_shown_on_its_field(self, client, root):
        # The model takes a port 0; the operation's schema does not.
        response = client.post(f"{CLUSTERS}add/", form(port="0"), HTTP_HOST=PLATFORM)

        html = response.content.decode()
        assert response.status_code == 200 and "greater than or equal to 1" in html
        assert re.search(r'errorlist[^>]*id="id_port_error"', html)
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
        assert LogEntry.objects.filter(object_id=str(cluster.pk), action_flag=DELETION).count() == 1

    def test_the_bulk_delete_goes_through_its_operation_too(self, client, root):
        first, second = a_cluster(), a_cluster(name="cluster-2", host="writer-2.example")

        client.post(
            CLUSTERS,
            {"action": "delete_selected", "_selected_action": [str(first.pk), str(second.pk)], "post": "yes"},
            HTTP_HOST=PLATFORM,
        )

        assert not Cluster.objects.exists()
        assert len(events("control.cluster.deleted")) == 2

    def test_a_bulk_delete_logs_only_what_its_operation_deleted(self, client, root, monkeypatch):
        from live.errors import Conflict

        first, second = a_cluster(), a_cluster(name="cluster-2", host="writer-2.example")
        real = control_admin.cluster_delete

        def refuses_the_second(ctx, data):
            if data.id == second.pk:
                raise Conflict("A hub was just placed on cluster-2.", code="control.cluster_holds_hubs")
            return real(ctx, data)

        monkeypatch.setattr(control_admin, "cluster_delete", refuses_the_second)

        response = client.post(
            CLUSTERS,
            {"action": "delete_selected", "_selected_action": [str(first.pk), str(second.pk)], "post": "yes"},
            HTTP_HOST=PLATFORM,
            follow=True,
        )

        # The admin capitalises its messages («Cluster-2: …»).
        assert "cluster-2: a hub was just placed on cluster-2." in response.content.decode().lower()
        assert list(Cluster.objects.values_list("name", flat=True)) == ["cluster-2"]
        logged = LogEntry.objects.filter(action_flag=DELETION).values_list("object_id", flat=True)
        assert list(logged) == [str(first.pk)]

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


class TestTheDefaultServer:
    """An empty ``Hub.cluster`` is the settings' own server: the registry says it instead of «-»."""

    def test_a_hub_on_no_cluster_says_it_is_on_the_default_server(self, client, root, hub_databases):
        cluster = local_cluster()
        Hub.objects.create(slug="acme", status=Hub.Status.READY, cluster=cluster, db_name=hub_databases.a)
        Hub.objects.create(slug="corner", status=Hub.Status.READY, db_name=hub_databases.b)

        html = page(client, HUBS)

        assert cluster_cell(row_of(html, ">corner<")) == DEFAULT_SERVER
        assert cluster_cell(row_of(html, ">acme<")) == "local"

    @pytest.mark.parametrize(
        "status", [Hub.Status.READY, Hub.Status.CANCELLED, Hub.Status.EXPIRED, Hub.Status.ARCHIVING]
    )
    def test_a_hub_whose_database_was_made_says_it(self, client, root, status):
        Hub.objects.create(slug="acme", status=status, db_name=f"hub_{uuid.uuid7().hex}", ready_at=timezone.now())

        assert cluster_cell(row_of(page(client, HUBS), ">acme<")) == DEFAULT_SERVER

    @pytest.mark.parametrize(
        "status, was_ready",
        [
            (Hub.Status.REQUESTED, False),  # Not made yet: a cluster may still take it.
            (Hub.Status.SEEDING, False),
            (Hub.Status.FAILED, False),  # No database for certain (no_cluster_available, say), and it is tried again.
            (Hub.Status.CANCELLED, False),  # base.hub.cancel takes a hub that was never ready: it never got a database.
            (Hub.Status.DROPPING, True),
            (Hub.Status.PURGED, True),
        ],
    )
    def test_a_hub_with_no_database_to_point_at_claims_no_server(self, client, root, status, was_ready):
        Hub.objects.create(
            slug="acme",
            status=status,
            db_name=f"hub_{uuid.uuid7().hex}",
            ready_at=timezone.now() if was_ready else None,
        )

        assert cluster_cell(row_of(page(client, HUBS), ">acme<")) == "-"

    def test_a_hub_without_a_database_of_its_own_claims_no_server(self, client, root):
        Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name="")

        assert cluster_cell(row_of(page(client, HUBS), ">acme<")) == "-"

    def test_a_hub_leaving_it_says_where_from_and_where_to(self, client, root, hub_databases):
        target = a_cluster(name="cluster-2", host="writer-2.example")
        Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=hub_databases.a, moving_to=target)

        assert cluster_cell(row_of(page(client, HUBS), ">acme<")) == f"{DEFAULT_SERVER} → cluster-2"

    def test_the_filter_by_cluster_calls_it_by_its_name(self, client, root):
        a_cluster()  # Without any cluster there is only one server, and Django shows no filter.

        choices = re.findall(r'<a href="\?cluster__isnull=True"[^>]*>(.*?)</a>', page(client, HUBS), re.S)

        assert [choice.strip() for choice in choices] == [DEFAULT_SERVER]

    def test_a_hubs_own_page_says_it_too(self, client, root, hub_databases):
        hub = Hub.objects.create(slug="corner", status=Hub.Status.READY, db_name=hub_databases.b)

        html = page(client, f"{HUBS}{hub.pk}/change/")

        assert read_only_values(html, "on_cluster") == [DEFAULT_SERVER]
        assert read_only_values(html, "cluster") == []

    def test_a_hub_on_a_cluster_keeps_its_link_on_its_own_page(self, client, root, hub_databases):
        cluster = local_cluster()
        hub = Hub.objects.create(slug="acme", status=Hub.Status.READY, cluster=cluster, db_name=hub_databases.a)

        html = page(client, f"{HUBS}{hub.pk}/change/")

        [value] = read_only_values(html, "cluster")
        assert f'href="{CLUSTERS}{cluster.pk}/change/"' in value
        assert read_only_values(html, "on_cluster") == []

    def test_it_speaks_spanish(self, client, root, hub_databases):
        Hub.objects.create(slug="corner", status=Hub.Status.READY, db_name=hub_databases.b)

        response = client.get(HUBS, HTTP_HOST=PLATFORM, HTTP_ACCEPT_LANGUAGE="es")

        assert cluster_cell(row_of(response.content.decode(), ">corner<")) == "servidor por defecto"


def test_its_words_are_translated():
    from django.utils import translation

    with translation.override("es"):
        assert str(control_admin.ClusterAdmin.close_to_new_hubs.short_description) == "Cerrar a hubs nuevos"
        assert control_admin.no_limit() == "sin límite"


class TestMoveToCluster:
    """«Move to cluster…»: the platform's admins choose hubs, then an open
    cluster on a confirmation page; each is asked to move through ``control.hub.move`` (the worker moves it, its host
    503 meanwhile). Support never sees it."""

    @pytest.fixture(autouse=True)
    def small(self, monkeypatch):
        from control import queries

        monkeypatch.setattr(queries, "measure", lambda cluster, names: {name: 1024 for name in names})

    @staticmethod
    def a_hub(slug: str, **fields) -> Hub:
        row = {"slug": slug, "status": Hub.Status.READY, "db_name": f"hub_{uuid.uuid7().hex}"}
        return Hub.objects.create(**(row | fields))

    @staticmethod
    def choose(client, *hubs, **more):
        data = {"action": "move_to_cluster", "_selected_action": [str(hub.pk) for hub in hubs]} | more
        return client.post(HUBS, data, HTTP_HOST=PLATFORM, follow=True)

    def test_asks_for_an_open_cluster_first_and_changes_nothing(self, client, root):
        hub = self.a_hub("acme")
        open_one = a_cluster(name="cluster-2", host="writer-2.example")
        a_cluster(name="cluster-closed", host="writer-9.example", is_open=False)

        html = self.choose(client, hub).content.decode()

        assert "Move to cluster" in html and "acme" in html
        assert f'value="{open_one.pk}"' in html and "cluster-closed" not in html
        assert 'name="apply"' in html
        hub.refresh_from_db()
        assert hub.moving_to_id is None

    def test_confirmed_each_hub_is_asked_to_move_and_it_says_so(self, client, root):
        first, second = self.a_hub("acme"), self.a_hub("bistro")
        target = a_cluster(name="cluster-2", host="writer-2.example")

        html = self.choose(client, first, second, apply="yes", cluster=str(target.pk)).content.decode()

        assert "2 hubs will move to cluster-2: each closed for a few minutes" in html
        for hub in (first, second):
            hub.refresh_from_db()
            assert hub.moving_to_id == target.pk
        assert len(events("control.hub.move_requested")) == 2
        on_cluster = row_of(page(client, HUBS), ">acme<")
        assert "cluster-2" in on_cluster

    def test_a_hub_the_operation_refuses_is_named_and_the_others_move(self, client, root):
        ready, preparing = self.a_hub("acme"), self.a_hub("bistro", status=Hub.Status.REQUESTED)
        target = a_cluster(name="cluster-2", host="writer-2.example")

        html = self.choose(client, ready, preparing, apply="yes", cluster=str(target.pk)).content.decode().lower()

        assert "bistro: only a ready hub with a database of its own moves." in html
        assert "1 hub will move to cluster-2" in html
        preparing.refresh_from_db()
        assert preparing.moving_to_id is None

    def test_without_a_cluster_chosen_it_asks_again(self, client, root):
        hub = self.a_hub("acme")
        a_cluster(name="cluster-2", host="writer-2.example")

        html = self.choose(client, hub, apply="yes").content.decode()

        assert 'name="apply"' in html and "errorlist" in html
        hub.refresh_from_db()
        assert hub.moving_to_id is None

    def test_support_neither_sees_it_nor_runs_it(self, client, support):
        hub = self.a_hub("acme")
        target = a_cluster(name="cluster-2", host="writer-2.example")

        assert "move_to_cluster" not in page(client, HUBS)
        self.choose(client, hub, apply="yes", cluster=str(target.pk))

        hub.refresh_from_db()
        assert hub.moving_to_id is None


class TestCancelTheMove:
    """«Cancel the move»: the worker puts each chosen hub back on its origin (``control.hub.move_cancel``)."""

    def test_asks_the_worker_to_undo_the_chosen_moves_and_says_which_were_not_moving(self, client, root):
        from control.models import MovedCopy

        target = a_cluster(name="cluster-2", host="writer-2.example")
        moving = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}", moving_to=target)
        still = Hub.objects.create(slug="bistro", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}")

        html = client.post(
            HUBS,
            {"action": "cancel_the_move", "_selected_action": [str(moving.pk), str(still.pk)]},
            HTTP_HOST=PLATFORM,
            follow=True,
        ).content.decode().lower()

        assert "1 move will be undone: the hub goes back to its cluster" in html
        assert "bistro: this hub is not moving." in html
        assert Hub.objects.get(pk=moving.pk).move_undo_asked_at is not None
        assert not MovedCopy.objects.exists()

    def test_support_neither_sees_it_nor_runs_it(self, client, support):
        target = a_cluster(name="cluster-2", host="writer-2.example")
        moving = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}", moving_to=target)

        assert "cancel_the_move" not in page(client, HUBS)
        client.post(HUBS, {"action": "cancel_the_move", "_selected_action": [str(moving.pk)]}, HTTP_HOST=PLATFORM)

        assert Hub.objects.get(pk=moving.pk).move_undo_asked_at is None


#: The moment a temporary cluster's copy is of, written as its point-in-time restore takes it (aws ``restore-hub.sh``).
MOMENT = "2026-11-09T14:30:00Z"
AT_MOMENT = dt.datetime(2026, 11, 9, 14, 30, tzinfo=dt.UTC)


class TestRestoreFromACopy:
    """«Restore from a copy…» (BASE-F114): the platform's admins choose hubs, then the temporary cluster their
    copy is on (one closed to new hubs) and the moment it is of, on a confirmation page; each is asked through
    ``control.hub.restore`` with that moment, and what the operation refuses is said hub by hub. Support never sees it,
    and the operation itself refuses anyone but the platform's admins (403)."""

    @pytest.fixture(autouse=True)
    def small(self, monkeypatch):
        from control import queries

        monkeypatch.setattr(queries, "measure", lambda cluster, names: {name: 1024 for name in names})

    a_hub = staticmethod(TestMoveToCluster.a_hub)

    @staticmethod
    def a_temporary_cluster() -> Cluster:
        return a_cluster(name="restore-1", host="restore-1.example", is_open=False)

    @staticmethod
    def choose(client, *hubs, **more):
        data = {"action": "restore_from_a_copy", "_selected_action": [str(hub.pk) for hub in hubs]} | more
        return client.post(HUBS, data, HTTP_HOST=PLATFORM, follow=True)

    def test_asks_for_a_temporary_cluster_and_the_moment_first_and_changes_nothing(self, client, root):
        hub = self.a_hub("acme")
        temporary = self.a_temporary_cluster()
        a_cluster(name="cluster-open", host="writer-2.example")

        html = self.choose(client, hub).content.decode()

        assert "Restore from a copy" in html and "acme" in html
        assert f'value="{temporary.pk}"' in html and "cluster-open" not in html
        assert 'name="at"' in html and 'name="apply"' in html
        hub.refresh_from_db()
        assert hub.restoring_from_id is None

    def test_confirmed_each_hub_is_asked_through_its_operation_with_the_moment(self, client, root):
        first, second = self.a_hub("acme"), self.a_hub("bistro")
        temporary = self.a_temporary_cluster()

        html = self.choose(client, first, second, apply="yes", cluster=str(temporary.pk), at=MOMENT).content.decode()

        assert "2 hubs will be restored from restore-1 as they were at 2026-11-09 14:30 UTC" in html
        for hub in (first, second):
            hub.refresh_from_db()
            assert (hub.restoring_from_id, hub.restore_point) == (temporary.pk, AT_MOMENT)
        assert [event["at"] for event in events("control.hub.restore_requested")] == [AT_MOMENT.isoformat()] * 2
        assert "← restore-1" in cluster_cell(row_of(page(client, HUBS), ">acme<"))

    def test_a_hub_the_operation_refuses_is_named_with_why_and_the_others_are_asked(self, client, root):
        ready, demo = self.a_hub("acme"), self.a_hub("bistro", is_demo=True)
        temporary = self.a_temporary_cluster()

        html = self.choose(client, ready, demo, apply="yes", cluster=str(temporary.pk), at=MOMENT).content.decode()

        # The admin writes each message with its first letter in capitals.
        assert "Bistro: A demo is not restored: it ends on its own." in html
        assert "1 hub will be restored from restore-1 as it was at 2026-11-09 14:30 UTC" in html
        demo.refresh_from_db()
        assert demo.restoring_from_id is None

    def test_a_moment_still_to_come_is_the_operations_to_refuse(self, client, root):
        hub = self.a_hub("acme")
        temporary = self.a_temporary_cluster()
        later = (timezone.now() + dt.timedelta(days=1)).isoformat()

        html = self.choose(client, hub, apply="yes", cluster=str(temporary.pk), at=later).content.decode()

        assert "Acme: That moment has not come yet." in html
        hub.refresh_from_db()
        assert hub.restoring_from_id is None

    @pytest.mark.parametrize("given", ["cluster", "at"])
    def test_without_the_cluster_or_the_moment_it_asks_again(self, client, root, given):
        hub = self.a_hub("acme")
        both = {"cluster": str(self.a_temporary_cluster().pk), "at": MOMENT}

        html = self.choose(client, hub, apply="yes", **{given: both[given]}).content.decode()

        assert 'name="apply"' in html and "errorlist" in html
        hub.refresh_from_db()
        assert hub.restoring_from_id is None

    def test_support_neither_sees_it_nor_runs_it(self, client, support):
        hub = self.a_hub("acme")
        temporary = self.a_temporary_cluster()

        assert "restore_from_a_copy" not in page(client, HUBS)
        self.choose(client, hub, apply="yes", cluster=str(temporary.pk), at=MOMENT)

        hub.refresh_from_db()
        assert hub.restoring_from_id is None

    def test_anyone_who_is_not_staff_is_answered_403_and_nothing_is_asked(self, client):
        client.force_login(get_user_model().objects.create_user(username="owner", password="pw"))
        hub = self.a_hub("acme")
        temporary = self.a_temporary_cluster()

        response = client.post(
            HUBS,
            {"action": "restore_from_a_copy", "_selected_action": [str(hub.pk)], "apply": "yes",
             "cluster": str(temporary.pk), "at": MOMENT},
            HTTP_HOST=PLATFORM,
        )

        assert response.status_code == 403
        hub.refresh_from_db()
        assert hub.restoring_from_id is None and not events("control.hub.restore_requested")

    def test_past_the_admins_door_its_operation_still_refuses_support_with_403(self, client, support, monkeypatch):
        from live.errors import OperationError

        refused: list[int] = []
        real = control_admin.hub_restore

        def asked(ctx, data):
            try:
                return real(ctx, data)
            except OperationError as error:
                refused.append(error.status)
                raise

        monkeypatch.setattr(control_admin.HubAdmin, "has_restore_permission", lambda self, request: True)
        monkeypatch.setattr(control_admin, "hub_restore", asked)
        hub = self.a_hub("acme")
        temporary = self.a_temporary_cluster()

        html = self.choose(client, hub, apply="yes", cluster=str(temporary.pk), at=MOMENT).content.decode()

        assert refused == [403] and "Acme: Only the platform may do this." in html
        hub.refresh_from_db()
        assert hub.restoring_from_id is None and not events("control.hub.restore_requested")


class TestRestoreToASeparateCopy:
    """«Restore to a separate copy…» (BASE-F114): the same confirmation page and form as «Restore from a
    copy…», each hub asked through ``control.hub.restore_aside``; the hubs are not touched, and Separate copies lists
    the copies, read only, for support too. Support never sees the action."""

    small = TestRestoreFromACopy.small
    a_hub = staticmethod(TestMoveToCluster.a_hub)
    a_temporary_cluster = staticmethod(TestRestoreFromACopy.a_temporary_cluster)

    @staticmethod
    def choose(client, *hubs, **more):
        data = {"action": "restore_aside", "_selected_action": [str(hub.pk) for hub in hubs]} | more
        return client.post(HUBS, data, HTTP_HOST=PLATFORM, follow=True)

    @staticmethod
    def a_copy(hub: Hub, **fields):
        """A separate copy of ``hub`` of the moment, as ``control.hub.restore_aside`` asks it."""
        from control.models import RestoredCopy

        values = {"restore_point": AT_MOMENT, "db_name": f"hub_copy_{uuid.uuid7().hex}", "asked_by": "root"}
        return RestoredCopy.objects.create(hub=hub, **(values | fields))

    def test_asks_for_a_temporary_cluster_and_the_moment_first_and_changes_nothing(self, client, root):
        from control.models import RestoredCopy

        hub = self.a_hub("acme")
        temporary = self.a_temporary_cluster()

        html = self.choose(client, hub).content.decode()

        assert "Restore to a separate copy" in html and "acme" in html and 'value="Make the copies"' in html
        assert f'value="{temporary.pk}"' in html and 'name="at"' in html
        assert not RestoredCopy.objects.exists()

    def test_confirmed_each_hub_gets_its_copy_asked_and_stays_as_it_is(self, client, root):
        from control.models import RestoredCopy

        first, second = self.a_hub("acme"), self.a_hub("bistro", is_demo=True)
        temporary = self.a_temporary_cluster()

        html = self.choose(client, first, second, apply="yes", cluster=str(temporary.pk), at=MOMENT).content.decode()

        assert "Bistro: A demo is not restored: it ends on its own." in html
        assert "1 hub will get a separate copy as it was at 2026-11-09 14:30 UTC, made from restore-1" in html
        [copy] = RestoredCopy.objects.all()
        assert (copy.hub_id, copy.source_id, copy.restore_point) == (first.pk, temporary.pk, AT_MOMENT)
        first.refresh_from_db()
        assert first.restoring_from_id is None
        assert "←" not in cluster_cell(row_of(page(client, HUBS), ">acme<"))

    def test_support_neither_sees_it_nor_runs_it_but_reads_the_copies(self, client, support):
        from control.models import RestoredCopy

        hub = self.a_hub("acme")
        temporary = self.a_temporary_cluster()
        self.a_copy(hub, source=temporary)

        assert "restore_aside" not in page(client, HUBS)
        self.choose(client, hub, apply="yes", cluster=str(temporary.pk), at=MOMENT)

        assert RestoredCopy.objects.count() == 1
        listed = page(client, COPIES)
        assert "acme" in listed and "2026-11-09 14:30 UTC" in listed and "Being made" in listed
        assert "addlink" not in listed

    def test_the_copies_are_listed_read_only_with_until_when_they_are_kept(self, client, root):
        from control.models import RestoredCopy

        hub = self.a_hub("acme")
        made = AT_MOMENT + dt.timedelta(hours=1)
        copy = self.a_copy(hub, status=RestoredCopy.Status.MADE, made_at=made)

        listed = page(client, COPIES)
        assert "acme" in listed and "2026-11-09 14:30 UTC" in listed
        assert "Made" in listed and "2026-11-16 15:30 UTC" in listed
        assert copy.db_name in page(client, COPIES, q=copy.db_name)
        its_page = client.get(f"{COPIES}{copy.pk}/change/", HTTP_HOST=PLATFORM).content.decode()
        assert copy.db_name in its_page and "default server" in its_page
        assert 'name="_save"' not in its_page and "deletelink" not in its_page
        assert client.post(f"{COPIES}{copy.pk}/delete/", {"post": "yes"}, HTTP_HOST=PLATFORM).status_code == 403
        assert RestoredCopy.objects.filter(pk=copy.pk).exists()

    def test_each_copy_says_its_business_and_moment_on_two_lines_as_recoveries_do(self, client, root):
        """Five columns in one line each do not fit a phone (375 px), even with the last error broken: its business and
        moment share the first cell, the one Recoveries shows for the same copy, and the last error keeps the room."""
        from control.models import RestoredCopy

        copy = self.a_copy(self.a_hub("acme"), status=RestoredCopy.Status.MADE, made_at=AT_MOMENT)

        listed = page(client, COPIES)

        assert re.findall(r'<th scope="col"[^>]*class="([^"]*)"', listed) == [
            "action-checkbox-column",
            "sortable column-made_from",
            "sortable column-status",
            "column-kept_until",
            "sortable column-last_error",
        ]
        assert TestRecoverIntoTheBusiness.copy_cell(copy) in row_of(listed, ">acme<")

    def test_a_long_last_error_breaks_inside_its_cell_by_the_sheet_copies_load(self, client, root):
        """Why a copy could not be made names its database in one piece: Separate copies load control's admin sheet,
        whose rule on the last error's cells breaks it into lines there instead of pushing the list sideways on a
        phone or a tablet (hub#1345). The browser measures it at 375, 768, 820 and 1280 px
        (tests/e2e/base-copies-aside-long-error.spec.ts); this keeps the sheet loaded and its rule on the cells the list
        draws."""
        from pathlib import Path

        from django.contrib.staticfiles import finders
        from django.templatetags.static import static

        from control.models import RestoredCopy

        copy = self.a_copy(self.a_hub("acme"), status=RestoredCopy.Status.FAILED)
        copy.last_error = f"restore_aside_restore_failed: pg_restore into {copy.db_name} failed (exit 1)"
        copy.save(update_fields=["last_error"])

        listed = page(client, COPIES)

        assert f'href="{static("control/admin.css")}"' in listed
        assert 'class="field-last_error"' in row_of(listed, ">acme<")
        sheet = Path(finders.find("control/admin.css")).read_text()
        rule = re.search(r"([^{}]*)\{[^}]*overflow-wrap:\s*anywhere", sheet)
        assert rule and "#result_list td.field-last_error" in rule.group(1)


class TestRecoverIntoTheBusiness:
    """«Recover into the business…» on Separate copies (BASE-F114): a confirmation page with what the apps
    give back from a copy (Customers today), ticked; confirmed, each chosen copy is asked through
    ``control.copy.recover`` and Recoveries lists how each goes, read only, for support too. Support never sees it."""

    a_hub = staticmethod(TestMoveToCluster.a_hub)

    def made(self, slug: str = "acme", **fields):
        from control.models import RestoredCopy

        made_at = AT_MOMENT + dt.timedelta(hours=1)
        values = {"status": RestoredCopy.Status.MADE, "made_at": made_at} | fields
        return TestRestoreToASeparateCopy.a_copy(self.a_hub(slug), **values)

    @staticmethod
    def choose(client, *copies, **more):
        data = {"action": "recover_into_the_business", "_selected_action": [str(copy.pk) for copy in copies]} | more
        return client.post(COPIES, data, HTTP_HOST=PLATFORM, follow=True)

    @staticmethod
    def copy_cell(copy) -> str:
        """What Recoveries says of a copy: its business and its moment on two lines, the results' column room on a
        phone (375 px)."""
        return f">{copy.hub.slug}<br>2026-11-09 14:30 UTC</a>"

    @staticmethod
    def a_recovery(copy, **fields):
        from control.models import CopyRecovery

        return CopyRecovery.objects.create(copy=copy, **({"apps": ["customer"], "asked_by": "root"} | fields))

    def test_asks_what_to_bring_back_first_and_changes_nothing(self, client, root):
        from control.models import CopyRecovery

        copy = self.made()

        html = self.choose(client, copy).content.decode()

        assert "Recover into the business" in html and 'value="Recover"' in html
        assert re.search(r'<input[^>]*name="apps"[^>]*value="customer"[^>]*checked', html)
        assert "Customers" in html
        # And the appointments, after the customers they are booked for.
        assert re.search(r'<input[^>]*name="apps"[^>]*value="appointment"[^>]*checked', html)
        assert html.index('value="customer"') < html.index('value="appointment"')
        assert str(copy) in html and f'<div class="readonly">{copy.db_name}</div>' in html
        assert "admin/css/forms.css" in html
        # Before confirming, what will not happen: what comes back greets nobody.
        assert "What comes back is nothing new to the business: it starts none of its automations" in html
        assert not CopyRecovery.objects.exists()

    def test_confirmed_each_copy_is_asked_and_recoveries_says_how_it_goes(self, client, root):
        from control.models import CopyRecovery

        copy = self.made("acme")
        not_made = TestRestoreToASeparateCopy.a_copy(self.a_hub("bistro"))

        html = self.choose(client, copy, not_made, apply="yes", apps="customer").content.decode()

        # The admin says each message with its first letter in capitals, as «Bistro: A demo is not restored…».
        assert f"{capfirst(str(not_made))}: Only a separate copy that is made gives anything back." in html
        assert "1 separate copy will give back Customers into its business within a few minutes" in html
        [asked] = CopyRecovery.objects.all()
        assert (asked.copy_id, asked.apps, asked.asked_by, asked.language) == (copy.pk, ["customer"], "root", "en")
        # Its row, never the admin's menu (which names Customers too): asked, and what it brings back.
        row = row_of(page(client, RECOVERIES), self.copy_cell(copy))
        assert "Asked" in row and "Customers" in row

    def test_with_nothing_ticked_it_asks_again(self, client, root):
        from control.models import CopyRecovery

        copy = self.made()

        html = self.choose(client, copy, apply="yes").content.decode()

        assert 'value="Recover"' in html and "This field is required." in html
        assert not CopyRecovery.objects.exists()

    def test_a_recovery_done_says_what_came_back_and_why_some_did_not(self, client, root):
        copy = self.made()
        why = {"id": str(uuid.uuid7()), "reason": "customer.phone_invalid: This phone is not valid."}
        done = self.a_recovery(
            copy,
            status="done",
            done_at=AT_MOMENT + dt.timedelta(days=1),
            results=[{"app": "customer", "created": 2, "not_created": 1, "reasons": [why], "refused": ""}],
        )

        listed = page(client, RECOVERIES)
        assert "Done" in listed and "Customers: 2 created, 1 not created" in listed
        # Three columns, what a phone shows at a glance (375 px): when it was asked and done is on its page.
        assert re.findall(r'<th scope="col"[^>]*class="([^"]*)"', listed) == [
            "sortable column-made_from",
            "sortable column-status",
            "column-outcome",
        ]
        its_page = client.get(f"{RECOVERIES}{done.pk}/change/", HTTP_HOST=PLATFORM).content.decode()
        assert why["id"] in its_page and "customer.phone_invalid: This phone is not valid." in its_page
        assert "2026-11-10 14:30 UTC" in its_page and "Customers" in read_only_values(its_page, "what")
        assert 'name="_save"' not in its_page and "deletelink" not in its_page
        assert client.post(f"{RECOVERIES}{done.pk}/delete/", {"post": "yes"}, HTTP_HOST=PLATFORM).status_code == 403
        assert f'href="{RECOVERIES}add/"' not in listed

    def test_a_recovery_says_how_many_came_back_the_same_apart_from_those_created(self, client, root):
        # A card the business deleted and still held comes back the same card (CUSTOMER-F33).
        self.a_recovery(
            self.made("acme"),
            status="done",
            results=[
                {"app": "customer", "restored": 1, "created": 2, "not_created": 1, "reasons": [], "refused": ""}
            ],
        )
        self.a_recovery(
            self.made("bistro"),
            status="done",
            results=[
                {"app": "customer", "restored": 2, "created": 0, "not_created": 0, "reasons": [], "refused": ""}
            ],
        )

        listed = page(client, RECOVERIES)
        assert "Customers: 1 restored, 2 created, 1 not created" in row_of(listed, ">acme<br>")
        # Only what came back is said: no «0 created» beside what was restored.
        assert "Customers: 2 restored<" in row_of(listed, ">bistro<br>")

    def test_an_app_that_gave_nothing_back_says_why_and_a_failed_one_its_error(self, client, root):
        refused = self.a_recovery(
            self.made("acme"),
            status="done",
            results=[
                {
                    "app": "customer",
                    "created": 0,
                    "not_created": 0,
                    "reasons": [],
                    "refused": "app_inactive: Customers is turned off in this business.",
                }
            ],
        )
        failed = self.a_recovery(
            self.made("bistro"), status="failed", last_error="recover_copy_unreadable: it is gone"
        )

        listed = page(client, RECOVERIES)
        assert "Customers: nothing (app_inactive: Customers is turned off in this business.)" in row_of(
            listed, ">acme<br>"
        )
        assert "recover_copy_unreadable: it is gone" in row_of(listed, ">bistro<br>")

    def test_an_app_stopped_halfway_says_what_came_back_and_why_it_stopped(self, client, root):
        self.a_recovery(
            self.made("acme"),
            status="done",
            results=[
                {
                    "app": "customer",
                    "created": 2,
                    "not_created": 0,
                    "reasons": [],
                    "refused": "base.hub_busy: The business is busy.",
                }
            ],
        )

        # What was restored before it stopped is said too, never «nothing».
        self.a_recovery(
            self.made("bistro"),
            status="done",
            results=[
                {
                    "app": "customer",
                    "restored": 1,
                    "created": 0,
                    "not_created": 0,
                    "reasons": [],
                    "refused": "base.hub_busy: The business is busy.",
                }
            ],
        )

        listed = page(client, RECOVERIES)
        assert "Customers: 2 created, then stopped (base.hub_busy: The business is busy.)" in row_of(
            listed, ">acme<br>"
        )
        assert "Customers: 1 restored, then stopped (base.hub_busy: The business is busy.)" in row_of(
            listed, ">bistro<br>"
        )

    def test_support_neither_sees_it_nor_runs_it_but_reads_the_recoveries(self, client, support):
        from control.models import CopyRecovery

        copy = self.made()

        assert "recover_into_the_business" not in page(client, COPIES)
        self.choose(client, copy, apply="yes", apps="customer")

        assert not CopyRecovery.objects.exists()
        self.a_recovery(copy)
        assert self.copy_cell(copy) in page(client, RECOVERIES)

    def test_a_long_result_breaks_inside_its_cell_by_the_sheet_recoveries_load(self, client, root):
        """A result can be long and in one piece (why a recovery failed names its copy's database): Recoveries load
        control's admin sheet, whose rule on the results' cells breaks it into lines there instead of pushing the list
        sideways on a phone. The browser measures it at 375, 768 and 1280 px
        (tests/e2e/base-recoveries-long-result.spec.ts); this keeps the sheet loaded and its rule on the cells the list
        draws."""
        from pathlib import Path

        from django.contrib.staticfiles import finders
        from django.templatetags.static import static

        copy = self.made()
        self.a_recovery(copy, status="failed", last_error=f"recover_copy_unreadable: {copy.db_name!r} is gone")

        listed = page(client, RECOVERIES)

        assert f'href="{static("control/admin.css")}"' in listed
        assert 'class="field-outcome"' in row_of(listed, self.copy_cell(copy))
        sheet = Path(finders.find("control/admin.css")).read_text()
        assert re.search(r"#result_list td\.field-outcome\s*\{[^}]*overflow-wrap:\s*anywhere", sheet)


def test_the_recovery_speaks_spanish(client, root):
    from django.utils import translation
    from django.utils.translation import ngettext

    copy = TestRecoverIntoTheBusiness().made()
    with translation.override("es"):
        assert (
            str(control_admin.RestoredCopyAdmin.recover_into_the_business.short_description)
            == "Recuperar en el negocio…"
        )
        assert ngettext(
            "%(count)d separate copy will give back %(what)s into its business within a few minutes: Recoveries says "
            "how it went.",
            "%(count)d separate copies will give back %(what)s into their businesses within a few minutes: Recoveries "
            "says how each went.",
            1,
        ) % {"count": 1, "what": "Clientes"} == (
            "1 copia aparte devolverá Clientes a su negocio en unos minutos: Recuperaciones dice cómo fue."
        )
    html = client.post(
        COPIES,
        {"action": "recover_into_the_business", "_selected_action": [str(copy.pk)]},
        HTTP_HOST=PLATFORM,
        HTTP_ACCEPT_LANGUAGE="es",
    ).content.decode()
    assert 'value="Recuperar"' in html and "Clientes" in html and "nunca se copia" in html
    # What the business deleted and still holds comes back the same, with its history.
    assert "vuelve tal como era, con su historial" in html
    # And it starts none of the business's automations.
    assert "Lo que vuelve no es nada nuevo para el negocio: no arranca ninguna de sus automatizaciones" in html
    with translation.override("es"):
        said = control_admin.CopyRecoveryAdmin.result_said(
            {"app": "customer", "restored": 2, "created": 1, "not_created": 1, "reasons": [], "refused": ""}
        )
    assert said == "Clientes: se restauraron 2, se creó 1, 1 sin crear"
    listed = client.get(RECOVERIES, HTTP_HOST=PLATFORM, HTTP_ACCEPT_LANGUAGE="es").content.decode()
    assert "Recuperaciones" in listed or "recuperaciones" in listed


def test_what_came_back_is_said_in_spanish_in_words_that_fit_customers_and_appointments_alike():
    """The counts follow the name of an app whose records are feminine in Spanish («Citas») as well as one
    whose records are masculine («Clientes»): never «Citas: 2 creados»."""
    from django.utils import translation

    said = control_admin.CopyRecoveryAdmin.result_said
    with translation.override("es"):
        assert said({"app": "appointment", "created": 2, "not_created": 1, "reasons": [], "refused": ""}) == (
            "Citas: se crearon 2, 1 sin crear"
        )
        assert said({"app": "customer", "created": 1, "not_created": 0, "reasons": [], "refused": ""}) == (
            "Clientes: se creó 1"
        )
        # And what comes back the same, whatever app restores it next.
        assert said({"app": "appointment", "restored": 1, "created": 0, "not_created": 0, "reasons": [], "refused": ""}) == (
            "Citas: se restauró 1"
        )


def test_the_separate_copy_speaks_spanish(client, root):
    from django.utils import translation
    from django.utils.translation import ngettext

    with translation.override("es"):
        assert str(control_admin.HubAdmin.restore_aside.short_description) == "Restaurar en una copia aparte…"
        assert ngettext(
            "%(count)d hub will get a separate copy as it was at %(moment)s, made from %(cluster)s: the business stays "
            "open as it is. Separate copies lists it, and says if it could not be made.",
            "%(count)d hubs will get a separate copy each as they were at %(moment)s, made from %(cluster)s: the "
            "businesses stay open as they are. Separate copies lists them, and says if one could not be made.",
            1,
        ).startswith("%(count)d hub tendrá una copia aparte")
    listed = client.get(COPIES, HTTP_HOST=PLATFORM, HTTP_ACCEPT_LANGUAGE="es").content.decode()
    assert "Copias aparte" in listed or "copias aparte" in listed


def test_the_restore_speaks_spanish():
    from django.utils import translation
    from django.utils.translation import ngettext

    with translation.override("es"):
        assert str(control_admin.HubAdmin.restore_from_a_copy.short_description) == "Restaurar desde una copia…"
        assert ngettext(
            "%(count)d hub will be restored from %(cluster)s as it was at %(moment)s: closed for a few minutes while "
            "it is restored. If it is refused, its page says why under «last error».",
            "%(count)d hubs will be restored from %(cluster)s as they were at %(moment)s: each closed for a few "
            "minutes while it is restored. If one is refused, its page says why under «last error».",
            2,
        ) % {"count": 2, "cluster": "r1", "moment": "2026-11-09 14:30 UTC"} == (
            "2 hubs se restaurarán desde r1 tal como estaban el 2026-11-09 14:30 UTC: cada uno cerrado unos minutos "
            "mientras se restaura. Si se rechaza alguno, su ficha dice por qué en «último error»."
        )


@pytest.mark.parametrize(
    "action, said, button",
    [
        ("restore_from_a_copy", "Cada hub elegido vuelve a como estaba en el momento", "Restaurarlos"),
        ("restore_aside", "nada de ella se envía a Hacienda", "Hacer las copias"),
    ],
)
def test_its_restore_page_speaks_spanish(client, root, action, said, button):
    hub = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}")
    a_cluster(name="restore-1", host="restore-1.example", is_open=False)

    html = client.post(
        HUBS,
        {"action": action, "_selected_action": [str(hub.pk)]},
        HTTP_HOST=PLATFORM,
        HTTP_ACCEPT_LANGUAGE="es",
    ).content.decode()

    assert said in html and f'value="{button}"' in html
    assert "Clúster temporal" in html and "Momento" in html


@pytest.mark.parametrize("action", ["move_to_cluster", "restore_from_a_copy", "restore_aside"])
def test_a_confirmation_page_wraps_a_long_database_name_as_a_hubs_own_page_does(client, root, action):
    """The chosen hubs are read-only rows of an aligned fieldset: the admin's forms sheet is what wraps a database name
    wider than a phone (375 px) instead of pushing the page sideways."""
    hub = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}")

    html = client.post(HUBS, {"action": action, "_selected_action": [str(hub.pk)]}, HTTP_HOST=PLATFORM).content.decode()

    assert 'class="module aligned"' in html and f'<div class="readonly">{hub.db_name}</div>' in html
    assert "admin/css/forms.css" in html


def test_the_move_speaks_spanish():
    from django.utils import translation
    from django.utils.translation import gettext, ngettext

    with translation.override("es"):
        assert str(control_admin.HubAdmin.move_to_cluster.short_description) == "Mover a otro clúster…"
        assert str(control_admin.HubAdmin.cancel_the_move.short_description) == "Cancelar el traslado"
        assert gettext("Only a ready hub with a database of its own moves.") == (
            "Solo se mueve un hub listo con base de datos propia."
        )
        assert ngettext(
            "%(count)d hub will move to %(cluster)s: closed for a few minutes while it moves.",
            "%(count)d hubs will move to %(cluster)s: each closed for a few minutes while it moves.",
            2,
        ) % {"count": 2, "cluster": "c2"} == "2 hubs se moverán a c2: cada uno cerrado unos minutos mientras se mueve."


def test_its_confirmation_page_speaks_spanish(client, root):
    hub = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}")
    a_cluster(name="cluster-2", host="writer-2.example")

    html = client.post(
        HUBS,
        {"action": "move_to_cluster", "_selected_action": [str(hub.pk)]},
        HTTP_HOST=PLATFORM,
        HTTP_ACCEPT_LANGUAGE="es",
    ).content.decode()

    assert "Cada hub elegido se cierra unos minutos" in html and 'value="Moverlos"' in html


# ── The freeze switch ────────────────────────────────────────────────────────────────────────────────────────────────


def the_switch() -> Freeze:
    """The switch's row, control's migration's (a test that flushed the tables before may have taken it away)."""
    row, _ = Freeze.objects.get_or_create()
    return row


def freeze_form(**fields) -> dict:
    values = {"frozen": "on", "reason": "Aurora upgrade"} | fields
    return {key: value for key, value in values.items() if value is not None} | {"_save": "Save"}


def held_by_the_worker(slug: str) -> None:
    """A hub the worker is working on now: its ``hub_due`` lease held."""
    now = timezone.now()
    hub = Hub.objects.create(slug=slug, status=Hub.Status.CREATING)
    HubDue.objects.create(hub=hub, due_at=now, lease_until=now + dt.timedelta(seconds=60), lease_owner="w1")


class TestFreeze:
    """Admin › Freeze: one row, its every write ``control.freeze.set``; the page says how many hubs the worker is still
    working on while frozen, the number the staff waits to see at 0 before the upgrade."""

    def test_is_registered(self):
        assert isinstance(admin.site._registry[Freeze], control_admin.FreezeAdmin)

    def test_lists_the_one_switch_not_frozen_and_offers_no_second(self, client, root):
        switch = the_switch()

        html = page(client, FREEZE)

        row = row_of(html, "field-frozen")
        assert "icon-no" in row and f'{switch.pk}/change/">not frozen</a>' in row
        assert f"{FREEZE}add/" not in html
        assert "the worker" not in html

    def test_a_platform_admin_freezes_it_through_its_operation(self, client, root):
        switch = the_switch()

        response = client.post(f"{FREEZE}{switch.pk}/change/", freeze_form(), HTTP_HOST=PLATFORM)

        assert response.status_code == 302
        row = Freeze.objects.get()
        assert (row.frozen, row.reason, row.by) == (True, "Aurora upgrade", "root")
        assert events("control.freeze.started") == [{"reason": "Aurora upgrade"}]
        assert LogEntry.objects.filter(object_id=str(row.pk), action_flag=CHANGE).exists()

    def test_frozen_its_page_says_how_many_hubs_the_worker_is_still_working_on(self, client, root):
        switch = the_switch()
        client.post(f"{FREEZE}{switch.pk}/change/", freeze_form(), HTTP_HOST=PLATFORM)
        held_by_the_worker("acme")
        held_by_the_worker("other")

        html = page(client, FREEZE)

        assert "icon-yes" in row_of(html, "Aurora upgrade")
        assert "the worker is still working on 2 hubs" in html

    def test_frozen_with_nothing_running_its_page_says_the_upgrade_may_start(self, client, root):
        switch = the_switch()
        client.post(f"{FREEZE}{switch.pk}/change/", freeze_form(), HTTP_HOST=PLATFORM)

        html = page(client, f"{FREEZE}{switch.pk}/change/")

        assert "the worker is working on no hub: the database may be upgraded" in html

    def test_unticking_it_lifts_the_freeze(self, client, root):
        switch = the_switch()
        client.post(f"{FREEZE}{switch.pk}/change/", freeze_form(), HTTP_HOST=PLATFORM)

        response = client.post(f"{FREEZE}{switch.pk}/change/", freeze_form(frozen=None, reason=""), HTTP_HOST=PLATFORM)

        assert response.status_code == 302
        assert Freeze.objects.get().frozen is False
        assert len(events("control.freeze.lifted")) == 1

    def test_what_its_operation_refuses_is_shown_on_its_field(self, client, root):
        switch = the_switch()

        response = client.post(f"{FREEZE}{switch.pk}/change/", freeze_form(reason="x" * 501), HTTP_HOST=PLATFORM)

        assert response.status_code == 200 and "errorlist" in response.content.decode()
        assert Freeze.objects.get().frozen is False

    def test_without_its_row_a_platform_admin_adds_it_through_the_operation(self, client, root):
        Freeze.objects.all().delete()
        assert f"{FREEZE}add/" in page(client, FREEZE)

        response = client.post(f"{FREEZE}add/", freeze_form(), HTTP_HOST=PLATFORM)

        assert response.status_code == 302
        assert Freeze.objects.get().frozen is True
        assert events("control.freeze.started") == [{"reason": "Aurora upgrade"}]

    def test_it_is_never_deleted(self, client, root):
        switch = the_switch()

        assert client.post(f"{FREEZE}{switch.pk}/delete/", {"post": "yes"}, HTTP_HOST=PLATFORM).status_code == 403
        assert Freeze.objects.filter(pk=switch.pk).exists()

    def test_support_reads_it_and_changes_nothing(self, client, support):
        switch = the_switch()

        assert "icon-no" in row_of(page(client, FREEZE), "field-frozen")
        assert client.post(f"{FREEZE}{switch.pk}/change/", freeze_form(), HTTP_HOST=PLATFORM).status_code == 403
        assert Freeze.objects.get().frozen is False


def test_the_freeze_speaks_spanish():
    from django.utils import translation
    from django.utils.translation import gettext, ngettext

    with translation.override("es"):
        assert str(Freeze._meta.verbose_name) == "congelación"
        assert str(Freeze._meta.get_field("frozen").verbose_name) == "congelado"
        assert str(Freeze(frozen=False)) == "sin congelar"
        assert str(control_admin.FreezeAdmin.state.short_description) == "estado"
        assert ngettext(
            "Frozen: the worker is still working on %(count)d hub; wait until it is 0 before the upgrade.",
            "Frozen: the worker is still working on %(count)d hubs; wait until it is 0 before the upgrade.",
            2,
        ) % {"count": 2} == "Congelado: el worker aún trabaja en 2 hubs; espera a que sea 0 antes de la subida."
        assert gettext("Frozen: the worker is working on no hub: the database may be upgraded.") == (
            "Congelado: el worker no trabaja en ningún hub: ya se puede subir la base de datos."
        )
