"""Every way into the Hub opens its database context itself (plan 2026-10-22-fase-2-tenencia §3 S1 and §4, step 8).

Without the suite's fallback (``no_test_fallback``), as in production: a request on a hub's host runs in
``use_hub(request.hub)``; on the platform host, in the hub chosen for the admin or, with none, phase 1's shared
database; a live re-execution enters its stream's hub in the executor's thread; the registry's operations run on
control and their outbox lands there; ``/internal``'s calls for a business enter it; the worker and the commands open
theirs (``manage.py shell``: ``base/tests/test_shell.py``). A hub with a database of its own (``hub_a``) gets its rows there and nowhere else.
"""

import contextvars
import datetime as dt
import json

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from live.context import OperationContext, Scope
from live.models import OutboxEvent

from apps.demo.models import Item
from base import worker
from base.models import Membership
from base.operations import HostClosed, HubContextBuilder
from base.tenancy import context, identity
from base.tenancy.tests import hubs

pytestmark = pytest.mark.usefixtures("no_test_fallback")

HUB_DB = pytest.mark.django_db(databases=hubs.HUB_DATABASES)


def member(slug: str, role: str = "hub_admin", username: str = "boss"):
    user = get_user_model().objects.create_user(username=username, password="pw")
    Membership.objects.create(user=user, host=slug, role=role)
    return user


def api_post(client, host, path, data):
    return client.post(f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=host)


def items_in(hub=None) -> list[str]:
    """The demo items of ``hub``'s database (``None``: phase 1's shared one), read as the code would."""
    entered = context.use_shared_database() if hub is None else context.use_hub(hub)
    with entered:
        return sorted(Item.objects.values_list("name", flat=True))


# ── Requests ──────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("slug", ["a", "b"])
def test_a_request_on_a_hub_of_the_shared_database_works_as_in_phase_one(client, slug):
    client.force_login(member(slug))

    created = api_post(client, f"{slug}.localhost", "/demo/items", {"name": "Shared"})

    assert created.status_code == 201
    assert items_in() == ["Shared"]


@HUB_DB
def test_a_request_on_a_hub_with_its_database_writes_there_and_nowhere_else(client, hub_a):
    client.force_login(member(hub_a.slug))

    created = api_post(client, f"{hub_a.slug}.localhost", "/demo/items", {"name": "Own"})
    listed = client.get("/api/demo/items", HTTP_HOST=f"{hub_a.slug}.localhost")

    assert created.status_code == 201
    assert [row["name"] for row in listed.json()["rows"]] == ["Own"]
    assert items_in(hub_a) == ["Own"]
    assert items_in() == []


@HUB_DB
def test_a_hub_whose_database_is_not_its_own_serves_nothing(client, hub_a, monkeypatch):
    """The identity check refuses the database (``test_identity.py``): the request answers 503 and runs nothing."""
    monkeypatch.setattr(identity, "_verified", set())

    def refuse(alias, hub_id):
        raise identity.HubIdentityMismatch(f"{alias} is another hub's")

    monkeypatch.setattr(identity, "verify", refuse)
    client.force_login(member(hub_a.slug))

    response = api_post(client, f"{hub_a.slug}.localhost", "/demo/items", {"name": "Never"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "base.hub_unavailable"
    monkeypatch.undo()
    assert items_in(hub_a) == []


@pytest.mark.django_db
def test_the_admin_without_a_chosen_hub_works_on_the_shared_database(client):
    with context.use_shared_database():
        Item.objects.create(name="Visible")
    client.force_login(get_user_model().objects.create_superuser("root", "root@example.com", "pw"))

    page = client.get("/admin/demo/item/", HTTP_HOST="hubs.localhost")

    assert page.status_code == 200
    assert "Visible" in page.content.decode()


@HUB_DB
def test_the_admin_with_a_chosen_hub_works_on_its_database(client, hub_a):
    with context.use_hub(hub_a):
        Item.objects.create(name="Of tenant a")
    with context.use_shared_database():
        Item.objects.create(name="Of phase one")
    client.force_login(get_user_model().objects.create_superuser("root", "root@example.com", "pw"))
    client.get(f"/admin/hub/{hub_a.slug}/", HTTP_HOST="hubs.localhost")

    page = client.get("/admin/demo/item/", HTTP_HOST="hubs.localhost").content.decode()

    assert "Of tenant a" in page
    assert "Of phase one" not in page


# ── The live executor and the print socket: a thread of their own ─────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_live_rerun_enters_its_streams_hub():
    ctx = OperationContext(scope=Scope("host", "a"), actor="system", permissions=frozenset({"*"}))

    def run():
        with HubContextBuilder().enter(ctx):
            return context.current_hub().slug

    assert contextvars.Context().run(run) == "a"


@pytest.mark.django_db
def test_a_live_rerun_of_a_hub_that_ended_closes_the_stream():
    from control.models import Hub

    Hub.objects.filter(slug="a").update(status=Hub.Status.CANCELLED)
    ctx = OperationContext(scope=Scope("host", "a"), actor="system", permissions=frozenset({"*"}))

    with pytest.raises(HostClosed):
        HubContextBuilder().enter(ctx)


@pytest.mark.django_db
def test_the_print_socket_runs_its_hubs_code_inside_its_hub():
    from base.ws_print import PrintSocket
    from control.models import Hub

    socket = PrintSocket({"path": "/ws/print"}, None, None)
    socket.request = type("Admitted", (), {"hub": Hub.objects.get(slug="b")})()

    def inside() -> str:
        return context.current_hub().slug

    import asyncio

    assert asyncio.run(socket._sync(inside)) == "b"


# ── /internal, the registry and the demos ────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_the_registrys_operations_run_on_control_and_their_events_land_there(client, settings):
    from base.registry import REGISTRY_SCOPE
    from base.schemas import HubSeedLocalIn
    from base.services import hub_seed_local
    from live.context import system_context

    answer = hub_seed_local(system_context(REGISTRY_SCOPE), HubSeedLocalIn(slugs=["c"]))

    assert [hub.slug for hub in answer.hubs] == ["c"]
    with context.use_control():
        assert OutboxEvent.objects.filter(scope_kind="platform").exists()


@HUB_DB
def test_a_hubs_operation_never_runs_inside_another_hub(hub_a, hub_b):
    from base.tenancy.context import HubContextMismatch
    from live.operations import get as get_operation

    op = get_operation("demo.item.create")
    as_b = OperationContext(scope=Scope("host", hub_b.slug), actor="system", permissions=frozenset({"*"}))

    with context.use_hub(hub_a), pytest.raises(HubContextMismatch):
        op(as_b, op.input.model_validate({"name": "Smuggled"}))
    assert items_in(hub_a) == items_in(hub_b) == []


@pytest.mark.django_db
def test_internal_calls_for_a_business_enter_it(monkeypatch):
    from base import internal

    seen = []

    def call(name, body, ctx):
        seen.append(context.current_hub().slug)
        return None, internal.refuse(418, "probe", "seen")

    monkeypatch.setattr(internal, "_operation_call", call)
    monkeypatch.setattr(internal.relay, "active_apps", lambda scope: frozenset({internal.WHATSAPP_APP}))
    request = type("Request", (), {"body": json.dumps({"hub": "b"}).encode()})()

    internal._whatsapp_call(request, "whatsapp_inbox.message.receive")

    assert seen == ["b"]


@pytest.mark.django_db
def test_internal_calls_for_the_platform_hub_run_on_the_shared_database(monkeypatch):
    from base import internal

    seen = []

    def call(name, body, ctx):
        seen.append(context.current().kind)
        return None, internal.refuse(418, "probe", "seen")

    monkeypatch.setattr(internal, "_operation_call", call)

    internal._platform_call("invoice.invoice.platform_health", {})

    assert seen == [context.SHARED]


# ── The worker, the commands and the shell ───────────────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_the_worker_opens_a_context_for_each_pass(caplog):
    now = timezone.now()

    def passes():
        worker._tick(now)
        worker._relay(now)
        worker._reap(now)

    contextvars.Context().run(passes)

    assert "HubContextMissing" not in caplog.text
    assert not [record for record in caplog.records if record.levelname == "ERROR"]


@pytest.mark.django_db(transaction=True)
def test_the_demo_reaper_purges_on_control(caplog):
    from control.models import Hub

    Hub.objects.create(
        slug="demo-0000beef", is_demo=True, status=Hub.Status.READY, expires_at=timezone.now() - dt.timedelta(minutes=1)
    )

    contextvars.Context().run(worker._reap, timezone.now())

    assert Hub.objects.get(slug="demo-0000beef").status == Hub.Status.PURGED


@pytest.mark.django_db
def test_seed_local_hubs_and_demo_expire_open_their_context(settings):
    from control.models import Hub

    settings.DEBUG = True
    Hub.objects.create(slug="demo-0000cafe", is_demo=True, status=Hub.Status.READY, expires_at=timezone.now())

    contextvars.Context().run(call_command, "seed_local_hubs", verbosity=0)
    contextvars.Context().run(call_command, "demo_expire", "demo-0000cafe", verbosity=0)

    assert Hub.objects.get(slug="demo-0000cafe").status == Hub.Status.PURGED


@pytest.mark.django_db
def test_create_platform_hub_works_on_the_shared_database(settings, capsys):
    settings.PLATFORM_ISSUER_LEGAL_NAME = "ERPlora S.L."
    settings.PLATFORM_ISSUER_TAX_ID = "B00000000"
    settings.PLATFORM_ISSUER_ADDRESS = "Calle Mayor 1"

    contextvars.Context().run(call_command, "create_platform_hub")

    assert "dry run" in capsys.readouterr().out.lower()


def test_nothing_of_a_hub_runs_without_a_context():
    def touch():
        return Item.objects.count()

    with pytest.raises(context.HubContextMissing):
        contextvars.Context().run(touch)
