"""Fixtures of the cash register tests: contexts per role and scope, and the real sale app the drawer reads (products
made by inventory, sales charged, voided and refunded by sale).

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``). Business B (``hub_b``) has its own database beside it; a test of B asks for ``hub_b`` and enters it.

Nothing of sale is made by hand: every charge, void and refund goes through sale's own operations, so
the drawer is tested against what sale really writes (no mocks).
"""

from contextlib import contextmanager

import pytest
from django.utils import timezone, translation
from live.context import OperationContext, Scope, system_context
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get

from apps.invoice.tests.conftest import catalog_of
from apps.sale.tests.conftest import ELSEWHERE, NIGHT_THERE, db_dsn, make_user, night_elsewhere
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, factory_data, in_business_a
from base.tenancy.tests.concurrency import hub_staff, plan_with_room

#: The marks, scopes and fixtures of the businesses' own databases, users with a role on a host, the raw DSN of
#: control's database and business A at night in another zone as Sales makes them, and the assistant's catalogue of a
#: person of business A, that these tests take from here.
__all__ = [
    "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "catalog_of", "db_dsn", "factory_data", "hub_staff", "in_business_a",
    "make_user", "night_elsewhere", "plan_with_room",
]


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


@pytest.fixture
def across_a_change_of_zone(monkeypatch, in_business_a):
    """What ``make()`` gives at one single instant in business A while it moves from another zone to Madrid and back:
    the 2nd, the 3rd and the 2nd again (hub#771). The root conftest's opens a business without a database of its own."""

    def across(make):
        monkeypatch.setattr(timezone, "now", lambda: NIGHT_THERE)
        made = []
        for zone in (ELSEWHERE, "Europe/Madrid", ELSEWHERE):
            monkeypatch.setattr(in_business_a, "timezone", zone)
            made.append(make())
        return made

    return across


@pytest.fixture(autouse=True)
def english():
    """Each test starts in English: a request of an earlier test may have left another language."""
    with translation.override("en"):
        yield


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


@pytest.fixture
def till(db):
    """The business's receipt printer, made by Printing."""
    return run(
        "printing.printer.create",
        {"name": "Till", "kind": "network", "address": "192.168.1.50", "usage": "receipt"},
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
