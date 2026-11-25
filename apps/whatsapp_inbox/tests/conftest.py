"""Fixtures of the WhatsApp inbox tests: contexts per role, a fixed clock, people of the hub and helpers
that run the app's (and Customers') real operations.

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``). Business B (``hub_b``) has its own database beside it; a test of B asks for ``hub_b`` and enters it.
"""

import datetime as dt
import json
import threading

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import timezone, translation
from live.context import OperationContext, Scope, system_context
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get
from psycopg.conninfo import make_conninfo

from apps.invoice.tests.conftest import catalog_of
from base import catalog, hub_visits, worker
from base.catalog.register_apps import RegisterResult
from base.models import Membership
from base.services.sessions import ensure_hub_user
from base.tenancy.context import use_hub
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, in_business_a
from base.tenancy.tests.concurrency import hub_staff, plan_with_room

#: The marks, scopes and fixtures of the businesses' own databases, and the assistant's catalogue of a person of
#: business A, that these tests take from here.
__all__ = ["B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "catalog_of", "hub_staff", "in_business_a", "plan_with_room"]

#: The fixed «now» of every test: Thursday 15 October 2026, 10:00 UTC (12:00 in Madrid).
NOW = dt.datetime(2026, 10, 15, 10, 0, tzinfo=dt.UTC)
#: What the worker's start would register in erplora.com's catalogue: nothing, in these tests.
REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor="tester",
    language: str = "en",
) -> OperationContext:
    """The context a user with ``role`` on ``scope`` gets (permissions from the apps' AppConfig)."""
    return OperationContext(
        scope=scope,
        actor=actor,
        permissions=permissions_for_role(all_live_app_configs(), role),
        language=language,
    )


def run(name: str, payload: dict | None = None, ctx: OperationContext | None = None):
    """Run the operation ``name`` with ``payload`` (validated by its input) as ``ctx`` (an admin of A)."""
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(payload or {}))


def system(name: str, payload: dict | None = None, scope: Scope = A):
    """Run ``name`` as the platform (the doors erplora.com calls, the reactions)."""
    return run(name, payload, system_context(scope))


def resume_each(hubs, on_commit) -> list:
    """The worker's resume pass of each of ``hubs`` in its own database, as its business (``base.worker``), with what
    it leaves for after the COMMIT (the calls to erplora.com) run; ``on_commit`` is pytest-django's
    ``django_capture_on_commit_callbacks``. One result per hub, in order."""
    results = []
    for hub in hubs:
        with use_hub(hub) as active, on_commit(execute=True, using=active.alias):
            results.append(system("whatsapp_inbox.delivery.resume", {}, Scope("host", hub.slug)))
    return results


def inbound(wa_id: str = "wamid.1", phone: str = "34600111222", **fields) -> dict:
    """The body erplora.com sends to /internal/whatsapp/inbound for a customer's text."""
    body = {
        "wa_message_id": wa_id,
        "from": phone,
        "contact_name": "Ana",
        "direction": "inbound",
        "source": "live",
        "type": "text",
        "text": "Hola, ¿tenéis hora mañana?",
        "sent_at": NOW.isoformat(),
    }
    body.update(fields)
    return body


def receive(
    wa_id: str = "wamid.1", phone: str = "34600111222", scope: Scope = A, **fields
):
    return system(
        "whatsapp_inbox.message.receive", inbound(wa_id, phone, **fields), scope
    )


def connect(version: int = 1, templates: list | None = None, scope: Scope = A, **fields):
    """erplora.com says ``scope``'s number is connected (and, when given, which templates Meta has)."""
    body = {
        "version": version,
        "status": "connected",
        "phone_number": "+34910000000",
        "display_name": "Peluquería Ana",
        "monthly_limit": 150,
        "monthly_usage": 10,
        "usage_month": "2026-10",
        "templates": templates,
    }
    body.update(fields)
    return system("whatsapp_inbox.channel.sync", body, scope)


def template(name: str = "recordatorio", **fields) -> dict:
    body = {
        "name": name,
        "language": "es",
        "category": "UTILITY",
        "status": "APPROVED",
        "header": "",
        "body": "Hola {{1}}, te esperamos el {{2}}.",
        "footer": "",
        "variables": 2,
        "rejected_reason": "",
        "meta_id": f"meta-{name}",
    }
    body.update(fields)
    return body


def card(name: str = "Ana López", phone: str = "600111222", **fields):
    """A customer card made by Customers' own operation (a real dependency, never a mock)."""
    return run("customer.customer.create", {"name": name, "phone": phone, **fields})


@pytest.fixture(autouse=True)
def english():
    """Each test starts in English: an earlier request (LocaleMiddleware) may have left another one."""
    with translation.override("en"):
        yield


@pytest.fixture(autouse=True)
def saas_settings(settings):
    """A SaaS to send through (``respx`` answers for it where a test sends) and the shared secret."""
    settings.SAAS_INTERNAL_URL = "http://saas.test"
    settings.SAAS_URL = "https://erplora.com"
    settings.INTERNAL_SHARED_SECRET = "s3cret"


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    """No test reads the real time: «now» is ``NOW`` unless the test moves it."""
    from apps.whatsapp_inbox import clock

    monkeypatch.setattr(clock, "now", lambda: NOW)
    return clock


@pytest.fixture
def tick(monkeypatch):
    """``tick(later)``: one turn of the worker's real loop over every business in its own database, its clock ``later``
    than now (a second by default), without erplora.com's catalogue, as a fresh process (no business served yet, A
    first) whose pass serves every business however slow the machine. The worker closes each business's connection
    after serving it, so a test that ticks is committed (``HUB_DB_COMMITTED``)."""
    monkeypatch.setattr(catalog.register_apps, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(hub_visits, "HUB_PASS_SECONDS", 3600)

    def run_once(later: dt.timedelta = dt.timedelta(seconds=1)) -> None:
        stop = threading.Event()
        at = timezone.now() + later
        assert worker.run(stop, tick_seconds=0, wait=lambda _seconds: stop.set() or True, clock=lambda: at) == 0

    return run_once


@pytest.fixture
def make_user(db):
    def make(
        username: str = "luis",
        *,
        host: str | None = A.key,
        role: str = Membership.Role.EMPLOYEE,
        **fields,
    ):
        user = get_user_model().objects.create_user(
            username=username, password="pw", **fields
        )
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        # Who they are in the business's database, as their entry makes it: who a conversation is with.
        user.person = ensure_hub_user(user)
        return user

    return make


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of the test database, for raw psycopg sessions (LISTEN)."""
    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )


def dumps(value) -> str:
    return json.dumps(value, default=str)
