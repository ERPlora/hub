"""Guardrail 3, «alias único» (PLAN-DB §14.2; plan 2026-10-22-fase-2-tenencia §2.3 and §4, step 9).

Two hubs with a database of their own, each with its rows. Whatever runs as A (an operation, a request, a live
re-run in the executor's thread) reaches A's database and never B's, watched on every alias at once; a write in B
records its event in B's database and notifies B's channel, never A's; and B's session on A's host is no session
(401), even for a member of both.
"""

import asyncio
import json
from contextlib import contextmanager

import pytest
from django.contrib.auth import get_user_model, login
from django.contrib.sessions.backends.db import SessionStore
from django.db.backends.utils import CursorWrapper
from django.test import RequestFactory
from live.context import OperationContext, Scope
from live.executor import Executor, Stream, Subscription
from live.models import OutboxEvent
from live.operations import get as get_operation

from base.models import Membership
from base.tenancy import context
from base.tenancy.tests import hubs

pytestmark = pytest.mark.usefixtures("no_test_fallback")

HUB_DB = pytest.mark.django_db(databases=hubs.HUB_DATABASES)
HUB_DB_COMMITTED = pytest.mark.django_db(databases=hubs.HUB_DATABASES, transaction=True)


@pytest.fixture(autouse=True)
def every_hub_known(settings):
    settings.LIVE = {**settings.LIVE, "context_builder": "base.operations.HubContextBuilder"}


@contextmanager
def watched(monkeypatch):
    """Every statement any thread sends, by alias: a wrapper at the cursor, under every connection of every thread."""
    sent: dict[str, list[str]] = {}
    real = CursorWrapper._execute

    def execute(self, sql, params, *ignored):
        sent.setdefault(self.db.alias, []).append(sql)
        return real(self, sql, params, *ignored)

    monkeypatch.setattr(CursorWrapper, "_execute", execute)
    yield sent
    monkeypatch.undo()


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
def test_an_operation_as_a_reaches_a_and_never_b(hub_a, hub_b, monkeypatch):
    create(hub_a, "Of A")
    create(hub_b, "Of B")

    with watched(monkeypatch) as sent:
        names = listed(hub_a)

    assert names == ["Of A"]
    assert touches(sent, hubs.HUB_A_ALIAS)
    assert hubs.HUB_B_ALIAS not in sent
    assert not touches(sent, "default")


@HUB_DB
def test_a_request_as_a_reaches_a_and_never_b(client, hub_a, hub_b, monkeypatch):
    create(hub_a, "Of A")
    create(hub_b, "Of B")
    user = get_user_model().objects.create_user(username="ana", password="pw")
    Membership.objects.create(user=user, host=hub_a.slug, role=Membership.Role.ADMIN)
    client.force_login(user)

    with watched(monkeypatch) as sent:
        response = client.get("/api/demo/items", HTTP_HOST=f"{hub_a.slug}.localhost")

    assert [row["name"] for row in response.json()["rows"]] == ["Of A"]
    assert touches(sent, hubs.HUB_A_ALIAS)
    assert hubs.HUB_B_ALIAS not in sent


@HUB_DB_COMMITTED
def test_a_live_rerun_as_a_reaches_a_and_never_b_in_the_executors_thread(hub_a, hub_b, monkeypatch):
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

    with watched(monkeypatch) as sent:
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
