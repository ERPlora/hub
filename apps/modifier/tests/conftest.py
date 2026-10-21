"""Fixtures of the modifier tests: contexts per role and scope, users with a role on a host, a raw DSN,
the real Inventory and Taxes rows a group is linked to (no doubles), and one tick of the worker's real relay.

The models are imported lazily, so that the tests of apps.py still collect while models.py does not
exist.
"""

import json
import threading

import psycopg
import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone, translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get
from live.outbox import channel_for
from psycopg.conninfo import make_conninfo

from base import catalog, worker
from base.catalog import RegisterResult
from base.models import Membership

A = Scope("host", "a")
B = Scope("host", "b")
#: A tax category of Taxes' Spanish factory catalogue (migration tax.0002): restaurant food, 10 %.
FOOD = "restaurant.food"
#: The general one (21 %): what a bottled soft drink pays.
GENERIC = "product.generic"


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English, the source language: a request in Spanish activates it and
    Django's LocaleMiddleware leaves it active in the thread for the tests that follow."""
    with translation.override("en"):
        yield


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: str = "tester",
    language: str = "en",
) -> OperationContext:
    """The context a user with ``role`` on ``scope`` gets (permissions from the apps' AppConfig)."""
    return OperationContext(
        scope=scope,
        actor=actor,
        permissions=permissions_for_role(all_live_app_configs(), role),
        language=language,
    )


def ctx_with(
    *permissions: str, scope: Scope = A, actor: str = "tester"
) -> OperationContext:
    """A context holding exactly ``permissions`` (a custom role or an API key with a chosen scope)."""
    return OperationContext(
        scope=scope, actor=actor, permissions=frozenset(permissions)
    )


def run(
    name: str,
    data: dict | None = None,
    role: str = "hub_admin",
    ctx: OperationContext | None = None,
):
    """Runs the operation ``name`` with ``data`` validated by its own input, as a route would."""
    op = get(name)
    return op(ctx or ctx_for(role), op.input.model_validate(data or {}))


@pytest.fixture
def make_user(db):
    def make(
        username: str = "ana",
        *,
        host: str | None = "a",
        role: str = Membership.Role.ADMIN,
    ):
        user = get_user_model().objects.create_user(username=username, password="pw")
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        return user

    return make


def make_product(
    name: str = "Burger",
    sku: str = "BUR",
    price: int = 800,
    tax: str | None = FOOD,
    **fields,
):
    """A product of the real Inventory app, made through its own operation."""
    data = {"name": name, "sku": sku, "price": price, **fields}
    if tax:
        data["tax_category_key"] = tax
    return run("inventory.product.create", data)


def make_category(name: str = "Mains"):
    """A category of the real Inventory app, made through its own operation."""
    return run("inventory.category.create", {"name": name})


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


# ── The worker's relay, as production runs it ────────────────────────────────────────────────────

#: What ``register_apps`` says when it has nothing to write: the tick runs without the SaaS.
REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)


def one_tick() -> None:
    """One tick of the worker's real loop (``base.worker.run``): the outbox relay hands each new event to the
    reactions of the apps (``events.py``), as production does."""
    stop = threading.Event()

    def wait(_seconds: float) -> bool:
        stop.set()
        return True

    now = timezone.now()
    assert worker.run(stop, tick_seconds=0, wait=wait, clock=lambda: now) == 0


@pytest.fixture
def tick(db, monkeypatch):
    """``one_tick`` without the SaaS (``register_apps``) and, inside the test's transaction, without releasing
    the connections (that would close the test's own)."""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)
    return one_tick


@pytest.fixture
def listen(transactional_db, db_dsn):
    """``listen(scope)``: a raw session LISTENing on the channel of ``scope`` (it hears only what is committed)."""
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def heard(session, timeout: float = 0.5) -> set[str]:
    """The event names the notices on ``session`` carried."""
    return {name for note in session.notifies(timeout=timeout) for name in json.loads(note.payload)["events"]}
