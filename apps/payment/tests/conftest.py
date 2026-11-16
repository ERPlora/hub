"""Fixtures of the payment tests: contexts per role and scope, and builders of the data a test starts from (straight to
the models: the operations are under test).

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``). Business B (``hub_b``) has its own database beside it; a test of B asks for ``hub_b`` and enters it.

The builders import the models lazily, so that the tests of apps.py still collect while models.py
does not exist.
"""

import datetime as dt

import pytest
from django.utils import translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role

from apps.cash_register.tests.conftest import across_a_change_of_zone
from apps.flow.tests.test_relay import listen, worker_loop
from apps.invoice.tests.conftest import catalog_of, in_hubs
from apps.sale.tests.conftest import db_dsn, make_user, night_elsewhere
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, in_business_a
from base.tenancy.tests.concurrency import hub_staff, plan_with_room

#: The marks, scopes and fixtures of the businesses' own databases, users with a role on a host, the raw DSN of
#: control's database and business A at night in another zone as Sales makes them, business A across a change of its
#: zone as Cash register makes it, a raw session listening on a scope's channel and one tick of the worker's real loop
#: over every business as Automations' tests make them, and the assistant's catalogue of a person of business A as
#: Invoicing reads it, that these tests take from here.
__all__ = [
    "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "across_a_change_of_zone", "catalog_of", "db_dsn", "hub_staff",
    "in_business_a", "in_hubs", "listen", "make_user", "night_elsewhere", "plan_with_room", "worker_loop",
]


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
