"""Fixtures of the WhatsApp inbox tests: contexts per role, a fixed clock, people of the hub and helpers
that run the app's (and Customers') real operations."""

import datetime as dt
import json

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import translation
from live.context import OperationContext, Scope, system_context
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get
from psycopg.conninfo import make_conninfo

from base.models import Membership

A = Scope("host", "a")
B = Scope("host", "b")

#: The fixed «now» of every test: Thursday 15 October 2026, 10:00 UTC (12:00 in Madrid).
NOW = dt.datetime(2026, 10, 15, 10, 0, tzinfo=dt.UTC)


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


def connect(version: int = 1, templates: list | None = None, **fields):
    """erplora.com says the number is connected (and, when given, which templates Meta has)."""
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
    return system("whatsapp_inbox.channel.sync", body)


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
def make_user(db):
    def make(
        username: str = "luis",
        *,
        host: str | None = "a",
        role: str = Membership.Role.EMPLOYEE,
        **fields,
    ):
        user = get_user_model().objects.create_user(
            username=username, password="pw", **fields
        )
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
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
