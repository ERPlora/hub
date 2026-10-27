"""Fixtures of the sale tests: contexts per role and scope, users with a role on a host, and the real
apps sale works with (tax's factory catalogue, inventory's products, customer's cards).

The products and the customers are created through their own apps' operations, never by hand: the
integration with ``tax``, ``inventory`` and ``customer`` is tested as it runs (no mocks).
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import timezone, translation
from live.context import OperationContext, Scope, system_context
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
    """The context a user with ``role`` on ``scope`` gets (permissions from the apps' AppConfig).

    Owner and admin get every declared permission (base.permissions); the others what each app's
    ``role_permissions`` gives them.
    """
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


@pytest.fixture(autouse=True)
def without_cash_register(monkeypatch):
    """Sale's own tests sell as a business without Cash register: the till asks an operation nobody
    declares, as when the app is not installed (``UnknownOperation``). Its lock on cash (SALE-F08) is
    tested apart, with Cash register in the business (``test_integration_cash_register.py`` overrides
    this fixture)."""
    monkeypatch.setattr(
        "apps.sale.services.DRAWER_CHECK", "cash_register.session.not_installed"
    )


@pytest.fixture(autouse=True)
def english():
    """Each test starts in English: a request of an earlier test may have left another language."""
    with translation.override("en"):
        yield


@pytest.fixture
def today():
    """The business day the test runs on, taken when it runs as the operations take it: a date taken at import
    is the day of the collection, and a run that crosses New Year's Eve would expect the numbers of the year
    before (``test_clock_at_import.py``)."""
    return timezone.localdate()


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


@pytest.fixture
def product(db):
    """``product(name, sku, price, tax_category_key, **more)``: an inventory product, made by inventory."""

    def make(
        name: str = "Coffee",
        sku: str = "COF",
        price: int = 150,
        tax_category_key: str = "restaurant.drink",
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

    def make(name: str = "Ana López", **more):
        return run(
            "customer.customer.create", {"name": name, **more}, system_context(A)
        )

    return make


@pytest.fixture
def factory_data(transactional_db):
    """A transactional test starts from a flushed database: tax's factory catalogue and the factory
    payment methods are planted again, as their migrations do (idempotent)."""
    from importlib import import_module

    from django.apps import apps as registry

    with connections["default"].schema_editor() as editor:
        for module in (
            "apps.tax.migrations.0002_factory_catalogue",
            "apps.tax.migrations.0005_retail_alcohol",
            "apps.sale.migrations.0002_factory_payment_methods",
        ):
            import_module(module).plant(registry, editor)


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of the test database, for raw psycopg sessions (reading only what is committed)."""
    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )


Q = Decimal
