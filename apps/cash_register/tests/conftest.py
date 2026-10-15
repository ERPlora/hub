"""Fixtures of the cash register tests: contexts per role and scope, users with a role on a host, and the
real sale app the drawer reads (products made by inventory, sales charged, voided and refunded by sale).

Nothing of sale is made by hand: every charge, void and refund goes through sale's own operations, so
the drawer is tested against what sale really writes (no mocks).
"""

from contextlib import contextmanager

import pytest
from django.contrib.auth import get_user_model
from django.utils import translation
from live.context import OperationContext, Scope, system_context
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get

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
    return OperationContext(
        scope=scope, actor=actor, permissions=permissions, language=language
    )


def run(name: str, data: dict | None = None, ctx: OperationContext | None = None):
    """Runs the operation ``name`` with ``data`` as its input (validated as a route would)."""
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data or {}))


@pytest.fixture(autouse=True)
def english():
    """Each test starts in English: a request of an earlier test may have left another language."""
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
def coffee(db):
    """A 1.50 € product (21 % VAT included) made by inventory, SKU ``COF``."""
    return run(
        "inventory.product.create",
        {
            "name": "Coffee",
            "sku": "COF",
            "price": 150,
            "tax_category_key": "product.generic",
        },
        system_context(A),
    )


_keys = iter(range(1, 10**6))


def charge(quantity: str = "1", payments: list | None = None, **more):
    """Charges ``quantity`` coffees through sale (cash by default, what was handed over = the total)."""
    data = {
        "idempotency_key": f"cash-register-{next(_keys):06d}",
        "lines": [{"product": "COF", "quantity": quantity}],
        **more,
    }
    if payments is not None:
        data["payments"] = payments
    return run("sale.sale.complete", data)


def void(sale, reason: str = "wrong ticket"):
    return run("sale.sale.void", {"sale_id": str(sale.id), "reason": reason})


def refund(sale, amount: int, *, payment: int = 0, to_method_id=None):
    """Refunds ``amount`` cents of ``sale`` from its ``payment``-th tender (to another method if given)."""
    allocation = {"payment_id": str(sale.payments[payment].id), "amount": amount}
    if to_method_id is not None:
        allocation["to_method_id"] = str(to_method_id)
    return run(
        "sale.sale.refund",
        {"sale_id": str(sale.id), "reason": "returned", "allocations": [allocation]},
    )


def open_session(opening_balance: int = 10000, **more):
    return run(
        "cash_register.session.open", {"opening_balance": opening_balance, **more}
    )


@contextmanager
def drawer_lock_off():
    """«Activar caja» off for what runs inside (Sales then charges cash with no session open: F04), and on
    again after it: how a cash sale ends up out of every shift (CASH_REGISTER-F17)."""
    run("cash_register.settings.update", {"enable_cash_register": False})
    try:
        yield
    finally:
        run("cash_register.settings.update", {"enable_cash_register": True})
