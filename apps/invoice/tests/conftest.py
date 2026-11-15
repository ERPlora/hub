"""Fixtures of the invoice tests: contexts per role and scope, users with a role on a host, and the real
apps invoice works with (tax's factory catalogue, inventory's products, customer's cards, sale's charges,
refunds and voids) — made through their own operations, never by hand: no mocks.

Every test with the database runs as production does: inside business A's own database (``hub_a`` of the root
conftest, entered with ``use_hub``), nothing falling back on control's. Business B (``hub_b``) has its own database
beside it; a test of B asks for ``hub_b`` and enters it.

``deliver(name)`` hands the newest ``name`` event of the outbox to Invoicing's real reaction
(``apps.invoice.events.react``), as the worker's outbox relay does.
"""

import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from importlib import import_module

import pytest
from django.apps import apps as registry
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import Client
from django.utils import timezone, translation
from live.context import OperationContext, Scope, system_context
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get
from psycopg.conninfo import make_conninfo

from pytest_django.fixtures import validate_django_db

from base import assistant
from base.models import Membership
from base.permissions import permissions_for
from base.tenancy import context, limits
from base.tenancy.connections import close_this_threads_connections
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

#: The django_db mark of a test of Invoicing: control's database and both businesses' own, each in its transaction.
IN_HUBS = pytest.mark.django_db(databases=hubs.HUB_DATABASES)
IN_HUBS_COMMITTED = pytest.mark.django_db(databases=hubs.HUB_DATABASES, transaction=True)


def in_hubs(test):
    """A test made by one of ``base.tests.test_assistant_asks``' factories, run in the businesses' own databases: its
    ``django_db`` mark becomes :data:`IN_HUBS`."""
    test.pytestmark = [IN_HUBS.mark if mark.name == "django_db" else mark for mark in test.pytestmark]
    return test


#: The businesses ``hub_a`` and ``hub_b`` of the root conftest, by their slugs.
A = Scope("host", "tenant-a")
B = Scope("host", "tenant-b")
#: Where the platform's staff open the Hub admin.
PLATFORM_HOST = "hubs.localhost"
#: A plan of erplora.com under which several sessions of a business work at the same time: Free's lets one transaction
#: at once, so a second session would wait for its turn, never for a row the first one holds.
WITH_ROOM = {"slug": "standard", "max_db_connections": 6, "statement_timeout_seconds": 15}
#: The migrations that plant the factory data a document needs: Taxes' catalogue and Sales' payment methods.
FACTORY_DATA = (
    "apps.tax.migrations.0002_factory_catalogue",
    "apps.tax.migrations.0005_retail_alcohol",
    "apps.sale.migrations.0002_factory_payment_methods",
)
ISSUER = {
    "legal_name": "Peluquería Ana SL",
    "tax_id": "B12345674",
    "address": "Calle Mayor 1",
    "postal_code": "28001",
    "city": "Madrid",
    "province": "Madrid",
}


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
    return OperationContext(
        scope=scope, actor=actor, permissions=permissions, language=language
    )


def run(name: str, data: dict | None = None, ctx: OperationContext | None = None):
    """Runs the operation ``name`` with ``data`` as its input (validated as a route would)."""
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data or {}))


def deliver(name: str, scope: Scope = A):
    """Hands the newest ``name`` event of the outbox to Invoicing, as the relay will."""
    from live.models import OutboxEvent

    from apps.invoice import events

    event = OutboxEvent.objects.filter(name=name).order_by("-created_at", "-id").first()
    assert event is not None, f"no {name} in the outbox"
    return events.react(scope, event.name, event.payload)


@pytest.fixture(autouse=True)
def english():
    """Each test starts in English: a request of an earlier test may have left another language."""
    with translation.override("en"):
        yield


def _uses_the_database(request) -> bool:
    return request.node.get_closest_marker("django_db") is not None or bool(
        {"db", "transactional_db"} & set(request.fixturenames)
    )


@pytest.fixture(autouse=True)
def in_business_a(request, no_test_fallback):
    """A test with the database runs inside business A's own database, as a request of A runs in production."""
    if not _uses_the_database(request):
        yield
        return
    marker = request.node.get_closest_marker("django_db")
    databases = validate_django_db(marker)[2] if marker else None
    if not databases or hubs.HUB_A_ALIAS not in databases:
        pytest.fail("A test of Invoicing with the database is marked IN_HUBS: both businesses' own databases.")
    with use_hub(request.getfixturevalue("hub_a")):
        yield


@pytest.fixture
def today():
    """The business day the test runs on, taken when it runs as the operations take it: a date taken at import
    is the day of the collection, and a run that crosses midnight would compare it with the next one
    (``tests/test_guardrails.py``, ``clock_at_import``)."""
    return timezone.localdate()


@pytest.fixture
def make_user(db):
    def make(
        username: str = "ana",
        *,
        host: str | None = A.key,
        role: str = Membership.Role.ADMIN,
    ):
        user = get_user_model().objects.create_user(username=username, password="pw")
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        return user

    return make


@pytest.fixture
def catalog_of(make_user):
    """``catalog_of(role, language)``: the real catalogue of the assistant of a person of business A with ``role``, who
    asks in ``language`` (one person per role)."""
    users = {}

    def of(role: str, language: str):
        if role not in users:
            users[role] = make_user(f"asker-{role}", role=role)
        user = users[role]
        ctx = OperationContext(scope=A, actor=user, permissions=permissions_for(user, A), language=language)
        return assistant.catalog(ctx)

    return of


@pytest.fixture
def issuer(db):
    """The business's tax identity, set up as the owner would (Invoicing → Issuer)."""
    return run("invoice.issuer.update", ISSUER)


@pytest.fixture
def product(db):
    """``product(name, sku, price, tax_category_key, **more)``: an inventory product, made by inventory."""

    def make(
        name="Shampoo",
        sku="SHA",
        price=1210,
        tax_category_key="product.generic",
        **more,
    ):
        data = {
            "name": name,
            "sku": sku,
            "price": price,
            "tax_category_key": tax_category_key,
            **more,
        }
        return run("inventory.product.create", data, system_context(A))

    return make


@pytest.fixture
def customer(db):
    """``customer(name, **more)``: a customer card, made by customer."""

    def make(name="Ana López", **more):
        return run(
            "customer.customer.create", {"name": name, **more}, system_context(A)
        )

    return make


@pytest.fixture
def charge(db):
    """``charge(key, lines, **more)``: a sale charged by card through the till's own operation."""

    def make(key="inv-sale-0001", lines=None, **more):
        data = {
            "idempotency_key": key,
            "lines": lines if lines is not None else [{"product": "SHA"}],
            "payments": [{"method": "card"}],
            **more,
        }
        return run("sale.sale.complete", data)

    return make


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of control's test database, where a live stream listens for a business's notices."""
    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )


@pytest.fixture
def factory_data(hub_a):
    """A committed test finds business A's database as the test before it left it, emptied: the factory data is
    planted again, as its migrations plant it (idempotent)."""
    with connections[hubs.HUB_A_ALIAS].schema_editor() as editor:
        for module in FACTORY_DATA:
            import_module(module).plant(registry, editor)


# ── Two sessions at once ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def plan_with_room(hub_a, monkeypatch):
    """Business A on a plan with room for several sessions at once (:data:`WITH_ROOM`), read by limiters of this test
    alone: the next test finds its hub's limits as they were."""
    monkeypatch.setattr(limits, "_limiters", {})
    hub_a.state, hub_a.state_version = {"plan": WITH_ROOM}, hub_a.state_version + 1
    hub_a.save(update_fields=["state", "state_version"])
    limits.configure(hubs.HUB_A_ALIAS, hub_a)


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, in the business at work, released together; their results
    or errors (reported by the test)."""
    active = context.current()
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            with context.use_again(active):
                results[index] = call()
        except Exception as error:
            results[index] = error
        finally:
            close_this_threads_connections()

    threads = [threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


#: How long a write lets the staff's deletion run until it waits for what the write holds (or ends).
DELETION_WAIT = 10


def _waited_for() -> bool:
    """Whether another session waits for a lock business A's session of this thread holds."""
    with connections[hubs.HUB_A_ALIAS].cursor() as cursor:
        cursor.execute("SELECT pg_stat_clear_snapshot()")
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE pg_backend_pid() = ANY (pg_blocking_pids(pid)))"
        )
        return cursor.fetchone()[0]


def _card_deletion(card, how: str):
    """The platform staff's «Delete» of the customer ``card`` in the Hub admin, with business A chosen, from its
    delete page (``page``) or with the list's «Delete selected» (``list``); calling it returns their answer."""
    staff = get_user_model().objects.create_superuser(
        username="card-deleter", password="pw", email="card-deleter@example.com"
    )
    client = Client()
    client.force_login(staff)
    client.get(f"/admin/hub/{A.key}/", HTTP_HOST=PLATFORM_HOST)
    if how == "page":
        url, data = f"/admin/customer/customer/{card.pk}/delete/", {"post": "yes"}
    else:
        url, data = "/admin/customer/customer/", {
            "action": "delete_selected",
            "_selected_action": [str(card.pk)],
            "post": "yes",
        }
    return lambda: client.post(url, data, HTTP_HOST=PLATFORM_HOST, HTTP_ACCEPT_LANGUAGE="en")


@contextmanager
def card_deleted_on_screen(card, how: str, before: Callable[[str], bool]):
    """The platform staff delete business A's customer ``card`` in the Hub admin in another session, started right
    before the first statement of this one for which ``before`` holds; this one goes on once the deletion waits for
    what it holds (or has ended). Yields the answers they got (a 500 is the error raised)."""
    delete = _card_deletion(card, how)
    answers: list = []

    def deletion():
        try:
            answers.append(delete())
        except Exception as error:  # a 500, reported to the test
            answers.append(error)
        finally:
            close_this_threads_connections()

    thread = threading.Thread(target=deletion)

    def wrapper(execute, sql, params, many, call_context):
        if thread.ident is None and before(sql):
            thread.start()
            deadline = time.monotonic() + DELETION_WAIT
            while thread.is_alive() and not _waited_for() and time.monotonic() < deadline:
                time.sleep(0.02)
        return execute(sql, params, many, context)

    try:
        with connections[hubs.HUB_A_ALIAS].execute_wrapper(wrapper):
            yield answers
    finally:
        if thread.ident is not None:
            thread.join(30)
    assert thread.ident is not None, "the deletion never started"
