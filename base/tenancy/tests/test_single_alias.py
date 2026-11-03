"""Guardrail 3, «alias único» (PLAN-DB §14.2; plan 2026-10-22-fase-2-tenencia §2.3 and §4, step 9).

Two hubs with a database of their own, each with its rows. Whatever runs as A (an operation, a request, a live
re-run in the executor's thread) reaches A's database and never B's, watched on every alias at once; a write in B
records its event in B's database and notifies B's channel, never A's; and B's session on A's host is no session
(401), even for a member of both, and so is B's API key, looked for in A's database only.
"""

import asyncio
import json

import pytest
from django.contrib.auth import get_user_model, login
from django.contrib.sessions.backends.db import SessionStore
from django.db.backends.utils import CursorWrapper
from django.test import RequestFactory
from live.context import OperationContext, Scope
from live.executor import Executor, Stream, Subscription
from live.models import OutboxEvent
from live.operations import get as get_operation

from apps.demo.models import Item
from base import api_keys
from base.models import ApiKey, Membership
from base.tenancy import context
from base.tenancy.tests import hubs
from base.tenancy.tests.legacy import use_legacy

pytestmark = pytest.mark.usefixtures("no_test_fallback")

HUB_DB = pytest.mark.django_db(databases=hubs.HUB_DATABASES)
HUB_DB_COMMITTED = pytest.mark.django_db(databases=hubs.HUB_DATABASES, transaction=True)


@pytest.fixture(autouse=True)
def every_hub_known(settings):
    settings.LIVE = {**settings.LIVE, "context_builder": "base.operations.HubContextBuilder"}


def as_hub(hub) -> OperationContext:
    return OperationContext(scope=Scope("host", hub.slug), actor="system", permissions=frozenset({"*"}))


def create(hub, name: str) -> None:
    op = get_operation("demo.item.create")
    with context.use_hub(hub):
        op(as_hub(hub), op.input.model_validate({"name": name}))


def listed(hub) -> list[str]:
    op = get_operation("demo.item.list")
    with context.use_hub(hub):
        return [row.name for row in op(as_hub(hub), op.input.model_validate({})).rows]


def touches(sent: dict[str, list[str]], alias: str, table: str = "demo_item") -> bool:
    return any(table in sql for sql in sent.get(alias, []))


@HUB_DB
def test_an_operation_as_a_reaches_a_and_never_b(hub_a, hub_b):
    create(hub_a, "Of A")
    create(hub_b, "Of B")

    with hubs.watched() as sent:
        names = listed(hub_a)

    # The watch is scoped: the rest of the test still runs as production (no fallback).
    assert context._test_fallback is None
    assert names == ["Of A"]
    assert touches(sent, hubs.HUB_A_ALIAS)
    assert hubs.HUB_B_ALIAS not in sent
    assert not touches(sent, "default")


@HUB_DB
def test_a_request_as_a_reaches_a_and_never_b(client, hub_a, hub_b):
    create(hub_a, "Of A")
    create(hub_b, "Of B")
    user = get_user_model().objects.create_user(username="ana", password="pw")
    Membership.objects.create(user=user, host=hub_a.slug, role=Membership.Role.ADMIN)
    client.force_login(user)

    with hubs.watched() as sent:
        response = client.get("/api/demo/items", HTTP_HOST=f"{hub_a.slug}.localhost")

    assert [row["name"] for row in response.json()["rows"]] == ["Of A"]
    assert touches(sent, hubs.HUB_A_ALIAS)
    assert hubs.HUB_B_ALIAS not in sent


@HUB_DB_COMMITTED
def test_a_live_rerun_as_a_reaches_a_and_never_b_in_the_executors_thread(hub_a, hub_b):
    create(hub_a, "Of A")
    create(hub_b, "Of B")
    user = get_user_model().objects.create_user(username="ana", password="pw")
    Membership.objects.create(user=user, host=hub_a.slug, role=Membership.Role.ADMIN)
    op = get_operation("demo.item.list")
    stream = Stream(OperationContext(scope=Scope("host", hub_a.slug), actor=user))
    stream.subs["s1"] = Subscription(id="s1", op=op, params=op.input.model_validate({}))
    executor = Executor(max_workers=1, debounce=0)

    async def run_once():
        try:
            await executor.run_all(stream)
        finally:
            executor.reset()
            executor.shutdown()

    with hubs.watched() as sent:
        asyncio.run(run_once())

    frame = stream.queue.get_nowait().decode()
    data = json.loads(frame.split("data: ", 1)[1])
    assert [row["name"] for row in data["data"]["rows"]] == ["Of A"]
    assert touches(sent, hubs.HUB_A_ALIAS)
    assert hubs.HUB_B_ALIAS not in sent


@HUB_DB_COMMITTED
def test_a_write_in_b_lands_in_b_and_notifies_b_only(hub_a, hub_b, monkeypatch):
    notified: list[tuple[str, str]] = []
    real = CursorWrapper._execute

    def execute(self, sql, params, *ignored):
        if "pg_notify" in sql:
            notified.append((self.db.alias, params[0]))
        return real(self, sql, params, *ignored)

    monkeypatch.setattr(CursorWrapper, "_execute", execute)

    create(hub_b, "Of B")

    assert notified == [("default", Scope("host", hub_b.slug).channel)]
    with context.use_hub(hub_b):
        assert OutboxEvent.objects.filter(name="demo.item.created").count() == 1
    with context.use_hub(hub_a):
        assert not OutboxEvent.objects.exists()
    with context.use_control():
        assert not OutboxEvent.objects.filter(name="demo.item.created").exists()


@HUB_DB
def test_bs_session_on_as_host_is_no_session(client, hub_a, hub_b):
    user = get_user_model().objects.create_user(username="ana", password="pw")
    for hub in (hub_a, hub_b):
        Membership.objects.create(user=user, host=hub.slug, role=Membership.Role.ADMIN)
    request = RequestFactory().get("/auth/callback")
    request.session, request.hub = SessionStore(), hub_b
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.save()
    client.cookies["sessionid"] = request.session.session_key

    assert client.get("/api/demo/items", HTTP_HOST=f"{hub_a.slug}.localhost").status_code == 401
    assert client.get("/api/demo/items", HTTP_HOST=f"{hub_b.slug}.localhost").status_code == 200


def new_key(hub) -> str:
    """A key of ``hub``, made in its own database as its Employees › API keys screen makes one: its token."""
    op = get_operation("base.api_key.create")
    with context.use_hub(hub):
        return op(as_hub(hub), op.input.model_validate({"name": "Till", "mode": "full"})).token


@HUB_DB
def test_bs_api_key_on_as_host_is_no_caller_and_never_reaches_b(client, hub_a, hub_b):
    token = new_key(hub_b)
    key = {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    with hubs.assert_only_alias(hubs.HUB_A_ALIAS) as sent:
        refused = client.get("/api/demo/items", HTTP_HOST=f"{hub_a.slug}.localhost", **key)

    assert refused.status_code == 401
    # A looked for it in its own database, where no key of B exists, and never in phase 1's shared tables.
    assert touches(sent, hubs.HUB_A_ALIAS, "base_apikey")
    assert not touches(sent, "default", "base_apikey")
    # The key is good on its own host: only A refuses it.
    assert client.get("/api/demo/items", HTTP_HOST=f"{hub_b.slug}.localhost", **key).status_code == 200


@HUB_DB
def test_the_watch_fails_a_block_that_reaches_any_other_hub(hub_a, hub_b):
    with hubs.assert_only_alias(hubs.HUB_A_ALIAS):
        listed(hub_a)

    with pytest.raises(AssertionError, match=hubs.HUB_B_ALIAS):
        with hubs.assert_only_alias(hubs.HUB_A_ALIAS):
            listed(hub_b)

    # What phase 1 left in control's tables is no hub's own either: a hub's table read there fails it.
    with pytest.raises(AssertionError, match="demo_item"):
        with hubs.assert_only_alias(hubs.HUB_A_ALIAS), use_legacy():
            list(Item.objects.all())


@HUB_DB
def test_a_key_planted_in_the_shared_tables_never_opens_a_hub_with_its_own_database(client, hub_a):
    # A key row left in control's tables by phase 1 (by hand, or by a business before its cut) is nobody's: A looks
    # for its keys in its own database only.
    token = api_keys.new_token()
    with use_legacy():
        ApiKey.objects.create(
            name="Planted", prefix=token[: api_keys.PREFIX_LENGTH], token_digest=api_keys.digest(token), mode="full"
        )

    with hubs.assert_only_alias(hubs.HUB_A_ALIAS) as sent:
        refused = client.get("/api/demo/items", HTTP_HOST=f"{hub_a.slug}.localhost", HTTP_AUTHORIZATION=f"Bearer {token}")

    assert refused.status_code == 401
    assert touches(sent, hubs.HUB_A_ALIAS, "base_apikey")
    assert not touches(sent, "default", "base_apikey")
