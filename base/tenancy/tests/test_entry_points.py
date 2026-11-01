"""Every way into the Hub opens its database context itself (plan 2026-10-22-fase-2-tenencia §3 S1 and §4, step 8).

Without the suite's fallback (``no_test_fallback``), as in production: a request on a hub's host runs in
``use_hub(request.hub)``; on the platform host, in the hub chosen for the admin or, with none, on control (a hub's page
there asks to choose one); a business without its own database (phase 1's, before its cut: S5) answers 503 and runs
nothing; a live re-execution enters its stream's hub in the executor's thread; the registry's operations run on
control and their outbox lands there; ``/internal``'s calls for a business enter it; the worker and the commands open
theirs (``manage.py shell``: ``base/tests/test_shell.py``). A hub with a database of its own (``hub_a``) gets its rows there and nowhere else.
"""

import contextvars
import datetime as dt
import json

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connections
from django.utils import timezone
from live.context import OperationContext, Scope
from live.models import OutboxEvent

from apps.demo.models import Item
from base import worker
from base.models import Membership
from base.operations import HostClosed, HubContextBuilder
from base.tenancy import context, identity
from base.tenancy.tests import hubs
from base.tenancy.tests.legacy import use_legacy

pytestmark = pytest.mark.usefixtures("no_test_fallback")

HUB_DB = pytest.mark.django_db(databases=hubs.HUB_DATABASES)


def member(slug: str, role: str = "hub_admin", username: str = "boss"):
    user = get_user_model().objects.create_user(username=username, password="pw")
    Membership.objects.create(user=user, host=slug, role=role)
    return user


def api_post(client, host, path, data):
    return client.post(f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=host)


def items_in(hub=None) -> list[str]:
    """The demo items of ``hub``'s database (``None``: what phase 1 left in control's tables), read as the code would."""
    entered = use_legacy() if hub is None else context.use_hub(hub)
    with entered:
        return sorted(Item.objects.values_list("name", flat=True))


# ── Requests ──────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("slug", ["a", "b"])
def test_a_request_on_a_business_without_its_own_database_answers_503_and_runs_nothing(client, slug):
    # S5: phase 1's shared database is gone; until its cut, a business still on control's is not served.
    client.force_login(member(slug))

    created = api_post(client, f"{slug}.localhost", "/demo/items", {"name": "Shared"})

    assert created.status_code == 503
    assert created.json()["error"]["code"] == "base.hub_preparing"
    assert items_in() == []


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
def test_a_hub_whose_database_is_not_its_own_serves_nothing(client, hub_a, monkeypatch, caplog):
    """The identity check refuses the database (``test_identity.py``): the request answers 503 and runs nothing."""
    monkeypatch.setattr(identity, "_verified", set())

    def refuse(alias, hub_id):
        raise identity.HubIdentityMismatch(f"{alias} is another hub's")

    real_verify = identity.verify
    monkeypatch.setattr(identity, "verify", refuse)
    client.force_login(member(hub_a.slug))

    response = api_post(client, f"{hub_a.slug}.localhost", "/demo/items", {"name": "Never"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "base.hub_unavailable"
    assert [record for record in caplog.records if record.levelname == "CRITICAL"]
    monkeypatch.setattr(identity, "verify", real_verify)
    assert items_in(hub_a) == []


@HUB_DB
def test_a_hub_whose_database_cannot_be_reached_now_is_503_without_the_mismatch_alarm(client, hub_a, monkeypatch, caplog):
    """A passing failure (PgBouncer restarting, a failover) is no «database not its own»: 503, a warning, no critical."""
    from django.db import OperationalError

    monkeypatch.setattr(identity, "_verified", set())

    def unreachable(alias, hub_id):
        raise OperationalError("connection refused")

    monkeypatch.setattr(identity, "verify", unreachable)
    client.force_login(member(hub_a.slug))

    response = client.get("/api/demo/items", HTTP_HOST=f"{hub_a.slug}.localhost")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "base.hub_unavailable"
    assert "Retry-After" in response
    assert not [record for record in caplog.records if record.levelname == "CRITICAL"]
    assert [record for record in caplog.records if record.levelname == "WARNING" and "base.hub_unreachable" in record.getMessage()]


@pytest.mark.django_db
def test_the_admin_without_a_chosen_hub_works_on_control_and_a_hubs_page_asks_to_choose_one(client):
    with use_legacy():
        Item.objects.create(name="Left on control")
    client.force_login(get_user_model().objects.create_superuser("root", "root@example.com", "pw"))

    page = client.get("/admin/demo/item/", HTTP_HOST="hubs.localhost", follow=True)
    registry = client.get("/admin/base/membership/", HTTP_HOST="hubs.localhost")

    assert page.redirect_chain == [("/admin/", 302)]
    assert "Choose a business first" in page.content.decode()
    assert "Left on control" not in page.content.decode()
    assert registry.status_code == 200


@pytest.mark.django_db
def test_the_admin_on_a_chosen_business_without_its_own_database_answers_503(client):
    client.force_login(get_user_model().objects.create_superuser("root", "root@example.com", "pw"))
    client.get("/admin/hub/a/", HTTP_HOST="hubs.localhost")

    page = client.get("/admin/demo/item/", HTTP_HOST="hubs.localhost")

    assert page.status_code == 503


@HUB_DB
def test_the_admin_with_a_chosen_hub_works_on_its_database(client, hub_a):
    with context.use_hub(hub_a):
        Item.objects.create(name="Of tenant a")
    with use_legacy():
        Item.objects.create(name="Of phase one")
    client.force_login(get_user_model().objects.create_superuser("root", "root@example.com", "pw"))
    client.get(f"/admin/hub/{hub_a.slug}/", HTTP_HOST="hubs.localhost")

    page = client.get("/admin/demo/item/", HTTP_HOST="hubs.localhost").content.decode()

    assert "Of tenant a" in page
    assert "Of phase one" not in page


# ── The live executor and the print socket: a thread of their own ─────────────────────────────────────────────────


@HUB_DB
def test_a_live_rerun_enters_its_streams_hub(hub_a):
    ctx = OperationContext(scope=Scope("host", hub_a.slug), actor="system", permissions=frozenset({"*"}))

    def run():
        with HubContextBuilder().enter(ctx):
            return context.current_hub().slug, context.current_alias()

    assert contextvars.Context().run(run) == (hub_a.slug, hubs.HUB_A_ALIAS)


@pytest.mark.django_db
def test_a_live_rerun_of_a_business_without_its_own_database_closes_the_stream():
    ctx = OperationContext(scope=Scope("host", "a"), actor="system", permissions=frozenset({"*"}))

    with pytest.raises(HostClosed) as closed:
        HubContextBuilder().enter(ctx)
    assert (closed.value.status, closed.value.code) == (503, "base.hub_preparing")


@pytest.mark.django_db
def test_a_live_rerun_of_a_hub_that_ended_closes_the_stream():
    from control.models import Hub

    Hub.objects.filter(slug="a").update(status=Hub.Status.CANCELLED)
    ctx = OperationContext(scope=Scope("host", "a"), actor="system", permissions=frozenset({"*"}))

    with pytest.raises(HostClosed):
        HubContextBuilder().enter(ctx)


@HUB_DB
def test_the_print_socket_runs_its_hubs_code_inside_its_hub(hub_b):
    from base.ws_print import PrintSocket

    socket = PrintSocket({"path": "/ws/print"}, None, None)
    socket.request = type("Admitted", (), {"hub": hub_b})()

    def inside() -> tuple[str, str]:
        return context.current_hub().slug, context.current_alias()

    import asyncio

    assert asyncio.run(socket._sync(inside)) == (hub_b.slug, hubs.HUB_B_ALIAS)


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


@HUB_DB
def test_internal_calls_for_a_business_enter_it(monkeypatch, hub_b):
    from base import internal

    seen = []

    def call(name, body, ctx):
        seen.append((context.current_hub().slug, context.current_alias()))
        return None, internal.refuse(418, "probe", "seen")

    monkeypatch.setattr(internal, "_operation_call", call)
    monkeypatch.setattr(internal.relay, "active_apps", lambda scope: frozenset({internal.WHATSAPP_APP}))
    request = type("Request", (), {"body": json.dumps({"hub": hub_b.slug}).encode()})()

    internal._whatsapp_call(request, "whatsapp_inbox.message.receive")

    assert seen == [(hub_b.slug, hubs.HUB_B_ALIAS)]


@pytest.mark.django_db
def test_internal_calls_for_a_business_without_its_own_database_answer_503_and_enter_nothing(monkeypatch):
    from base import internal

    monkeypatch.setattr(internal, "_operation_call", lambda *args: pytest.fail("it ran"))
    request = type("Request", (), {"body": json.dumps({"hub": "b"}).encode()})()

    answer = internal._whatsapp_call(request, "whatsapp_inbox.message.receive")

    assert (answer.status_code, json.loads(answer.content)["error"]["code"]) == (503, "base.hub_preparing")


@HUB_DB
def test_internal_calls_for_the_platform_hub_run_in_its_own_database(monkeypatch, settings, hub_a):
    from base import internal

    settings.PLATFORM_HUB_SLUG = hub_a.slug
    seen = []

    def call(name, body, ctx):
        seen.append((context.current().kind, context.current_alias()))
        return None, internal.refuse(418, "probe", "seen")

    monkeypatch.setattr(internal, "_operation_call", call)

    internal._platform_call("invoice.invoice.platform_health", {})

    assert seen == [(context.HUB, hubs.HUB_A_ALIAS)]


# ── The worker, the commands and the shell ───────────────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_the_worker_opens_a_context_for_each_pass(caplog):
    now = timezone.now()

    def passes():
        worker._relay(now)
        worker._hubs(now)
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

    # a and b are ready already (the suite's local hubs): it only checks them, in its context.
    contextvars.Context().run(call_command, "seed_local_hubs", "--check", verbosity=0)
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


async def asgi_post(async_client, host: str, path: str, data: dict):
    """A POST through the ASGI handler with ``host`` as its only Host header (``AsyncClient.post`` always adds
    ``testserver``, and two Host headers are one invalid one)."""
    from django.test.client import FakePayload

    body = json.dumps(data).encode()
    return await async_client.request(
        method="POST",
        path=path,
        query_string="",
        headers=[
            (b"host", host.encode()),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        _body_file=FakePayload(body),
    )


@pytest.mark.django_db(databases=hubs.HUB_DATABASES, transaction=True)
@pytest.mark.parametrize("own_database", [False, True], ids=["without", "own"])
async def test_an_asgi_request_runs_in_its_hub_too(async_client, hub_a, own_database):
    """Daphne runs the middleware asynchronously (``HubDatabaseMiddleware.__acall__``): the same context, and the same
    503 for a business without its own database (S5)."""
    from asgiref.sync import sync_to_async

    slug = hub_a.slug if own_database else "a"
    await sync_to_async(member)(slug)
    await async_client.aforce_login(await sync_to_async(get_user_model().objects.get)(username="boss"))

    created = await asgi_post(async_client, f"{slug}.localhost", "/api/demo/items", {"name": "Async"})

    assert created.status_code == (201 if own_database else 503)
    assert await sync_to_async(items_in)(hub_a if own_database else None) == (["Async"] if own_database else [])
    # The connections of the ASGI handler's thread, not the test's: closed before the databases are flushed.
    await sync_to_async(connections.close_all)()
