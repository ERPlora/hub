"""Fixtures of the tips tests: contexts per role and scope, and the real apps a tip goes with (sales charged, voided and
refunded by Sales, sessions opened by Cash register, people made by Staff).

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``). Business B (``hub_b``) has its own database beside it; a test of B asks for ``hub_b`` and enters it.
Nothing of another app is made by hand: it goes through that app's own operations.
"""

import dataclasses

from live.context import system_context

from apps.sale.models.payment_methods import PaymentMethod

from apps.cash_register.tests.conftest import (
    HUB_DB,
    HUB_DB_COMMITTED,
    A,
    B,
    charge,
    coffee,
    ctx_for,
    in_business_a,
    make_user,
    open_session,
    refund,
    run,
    void,
)
from apps.sale.tests.conftest import db_dsn

__all__ = [
    "B", "HUB_DB", "HUB_DB_COMMITTED", "charge", "coffee", "ctx_for", "db_dsn", "in_business_a", "make_user", "open_session",
    "refund", "run", "void",
]

CARD = [{"method": "card"}]


def member(first_name: str = "Bea", **more):
    """A member of the team, made by Staff."""
    return run("staff.member.create", {"first_name": first_name, "last_name": "Ruiz", **more}, system_context(A))


def as_user(user, role: str = "hub_employee"):
    """The context of ``user`` (made by ``make_user``) with what ``role`` may do."""
    return dataclasses.replace(ctx_for(role), actor=user)


def add_tip(amount: int = 200, method: str = "card", ctx=None, **more):
    """A tip of ``amount`` cents recorded by Tips."""
    return run("tip.tip.add", {"amount": amount, "method": method, **more}, ctx)


def with_cash(ctx=None):
    """The business of ``ctx`` with an active cash payment method, made by Sales when another test left it none: what
    a tip to the pool is in."""
    if not PaymentMethod.objects.filter(type=PaymentMethod.Type.CASH, is_active=True).exists():
        run("sale.payment_method.create", {"name": "Cash", "type": "cash"}, ctx)
