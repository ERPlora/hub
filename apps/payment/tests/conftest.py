"""Fixtures of the payment tests: contexts per role and scope, users with a role on a host, a raw DSN,
and builders of the data a test starts from (straight to the models: the operations are under test).

The builders import the models lazily, so that the tests of apps.py still collect while models.py
does not exist.
"""

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from psycopg.conninfo import make_conninfo

from base.models import Membership

A = Scope("host", "a")
B = Scope("host", "b")


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: object = "tester",
    permissions: set[str] | None = None,
) -> OperationContext:
    """The context a caller with ``role`` on ``scope`` gets (permissions from the apps' AppConfig).

    ``permissions`` replaces the role's when a test needs a combination no role has.
    """
    if permissions is None:
        permissions = permissions_for_role(all_live_app_configs(), role)
    return OperationContext(scope=scope, actor=actor, permissions=permissions)


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English: a request in Spanish leaves its language active on the thread."""
    with translation.override("en"):
        yield


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


# Builders


def make_method(name: str = "BBVA account", method_type: str = "transfer", **fields):
    from apps.payment.models import PaymentMethod

    return PaymentMethod.objects.create(name=name, method_type=method_type, **fields)


def make_payment(
    method=None,
    *,
    reference: str = "PAY-20261014-0001",
    amount: int = 12_50,
    beneficiary_name: str = "Proveedor Norte SL",
    payment_date: dt.date = dt.date(2026, 10, 14),
    currency: str = "EUR",
    **fields,
):
    from apps.payment.models import Payment

    return Payment.objects.create(
        method=method or make_method(),
        reference=reference,
        amount=amount,
        beneficiary_name=beneficiary_name,
        payment_date=payment_date,
        currency=currency,
        **fields,
    )
