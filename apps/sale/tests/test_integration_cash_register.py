"""Sale and Cash register together, no mocks (SALE-F08, CASH_REGISTER-F04): with the cash register on and
no session open, the till charges no cash; cards and the rest charge as ever. Sales asks Cash register by
the name of its operation (``cash_register.session.current``) with the seller's session; with Cash
register off, absent or failing, the till charges (the lock gives way before the sales stop).
"""

import pytest
from django.utils import translation
from live.errors import Conflict
from live.operations import registry

from apps.sale.models import Sale, SaleCounter
from apps.sale.tests.conftest import ctx_for, run

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"


@pytest.fixture(autouse=True)
def without_cash_register():
    """Here Cash register IS in the business (the conftest takes it out for the rest of sale's tests)."""


@pytest.fixture(autouse=True)
def coffee(product):
    return product("Coffee", "COF", 150, "restaurant.drink")


def charge(key, payments=None, ctx=None, **more):
    data = {"idempotency_key": key, "lines": [{"product": "COF"}], **more}
    if payments is not None:
        data["payments"] = payments
    return run("sale.sale.complete", data, ctx)


def cash_register(on: bool):
    run("cash_register.settings.update", {"enable_cash_register": on})


def test_with_the_drawer_closed_cash_is_refused_and_nothing_is_charged():
    with pytest.raises(Conflict) as refusal:
        charge("drawer-0001", ctx=ctx_for(EMPLOYEE))
    assert refusal.value.code == "sale.cash_register_closed"
    assert refusal.value.message == (
        "The cash register is closed: open a cash session to charge in cash."
    )
    assert Sale.objects.count() == 0
    # The refusal burns no number of the day.
    assert not SaleCounter.objects.filter(last__gt=0).exists()


def test_cash_in_one_leg_of_a_split_is_refused_too():
    with pytest.raises(Conflict) as refusal:
        charge(
            "drawer-0002",
            payments=[{"method": "card", "amount": 100}, {"method": "cash"}],
        )
    assert refusal.value.code == "sale.cash_register_closed"


def test_a_card_charges_with_the_drawer_closed():
    sale = charge("drawer-0003", payments=[{"method": "card"}], ctx=ctx_for(EMPLOYEE))
    assert sale.status == "completed"


def test_with_a_session_open_cash_charges():
    run("cash_register.session.open", {"opening_balance": 10000})
    sale = charge("drawer-0004", ctx=ctx_for(EMPLOYEE))
    assert sale.payments[0].method_type == "cash"


def test_with_the_cash_register_off_cash_charges():
    cash_register(False)
    assert charge("drawer-0005").status == "completed"


def test_without_cash_register_in_the_business_cash_charges(monkeypatch):
    # Not installed or off for this hub: its operations are not there (the same path as app_inactive).
    monkeypatch.delitem(registry, "cash_register.session.current")
    assert charge("drawer-0006").status == "completed"


def test_a_seller_who_may_not_ask_cash_register_still_charges():
    # The lock gives way before the sales stop: a refusal of Cash register is not a refusal of the sale.
    ctx = ctx_for(EMPLOYEE)
    ctx = type(ctx)(
        scope=ctx.scope,
        actor=ctx.actor,
        permissions=ctx.permissions - {"cash_register.view_session"},
    )
    assert charge("drawer-0007", ctx=ctx).status == "completed"


def test_a_charge_of_nothing_asks_nothing(product):
    product("Water", "WAT", 100, "restaurant.drink")
    sale = run(
        "sale.sale.complete",
        {"idempotency_key": "drawer-0008", "lines": [{"product": "WAT", "is_gift": True}]},
    )
    assert sale.total == 0


def test_the_refusal_is_said_in_spanish():
    with translation.override("es"), pytest.raises(Conflict) as refusal:
        charge("drawer-0009", ctx=ctx_for(language="es"))
    assert refusal.value.message == (
        "La caja está cerrada: abre una sesión de caja para cobrar en efectivo."
    )
