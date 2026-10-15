"""Fixtures of the printing tests: contexts per role and scope, users with a role on a host, and the
helpers that run printing's operations by name, the way the other apps and the routes call them."""

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get

from psycopg.conninfo import make_conninfo

from base.models import Membership

A = Scope("host", "a")
B = Scope("host", "b")


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: str = "tester",
    language: str = "en",
) -> OperationContext:
    """The context a user with ``role`` on ``scope`` gets (owner and admin: every declared permission)."""
    configs = all_live_app_configs()
    if role in ("hub_owner", "hub_admin"):
        permissions = frozenset(p for config in configs for p in config.permissions)
    else:
        permissions = permissions_for_role(configs, role)
    return OperationContext(scope=scope, actor=actor, permissions=permissions, language=language)


def run(name: str, data: dict | None = None, ctx: OperationContext | None = None):
    """Runs the operation ``name`` with ``data`` as its input (validated as a route would)."""
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data or {}))


def printer(name: str = "Till", **more):
    """Adds a printer through ``printing.printer.create`` (a network one at 192.168.1.50 by default)."""
    data = {"name": name, "kind": "network", "address": "192.168.1.50", "usage": "receipt", **more}
    return run("printing.printer.create", data)


RECEIPT = {
    "business_name": "Salón Ana",
    "receipt_id": "T-000123",
    "items": [{"name": "Haircut", "quantity": 1, "total": 18.0}],
    "subtotal": 14.88,
    "tax_amount": 3.12,
    "total": 18.0,
    "payment_method": "Cash",
}


def enqueue(document_type: str = "receipt", document: dict | None = None, **more):
    """Queues a document through ``printing.job.create`` (a receipt by default)."""
    data = {"document_type": document_type, "document": document if document is not None else RECEIPT, **more}
    return run("printing.job.create", data)


@pytest.fixture(autouse=True)
def english():
    """Each test starts in English: a request of an earlier test may have left another language."""
    with translation.override("en"):
        yield


@pytest.fixture
def make_user(db):
    def make(username: str = "ana", *, host: str | None = "a", role: str = Membership.Role.ADMIN):
        user = get_user_model().objects.create_user(username=username, password="pw")
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        return user

    return make


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of the test database, for raw psycopg sessions (LISTEN, or reading only what is committed)."""
    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )
