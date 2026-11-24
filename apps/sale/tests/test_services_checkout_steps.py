"""What another app adds to a tender is charged only while an app on in the business adds a step to the charge of the
person charging (SALE-F39): that app records it in its own place too, so the drawer, the card total and the receipt
never hold money nobody accounts for. The reference app stands for one that declares a step, as Tips does."""

import pytest
from django.apps import apps
from live.context import system_context
from live.errors import Conflict
from live.meta import CheckoutStep

from apps.sale.models import Sale, SalePayment
from apps.sale.tests.conftest import HUB_DB, B, ctx_for, run
from base import activation
from base.tenancy.context import use_hub

pytestmark = HUB_DB

REFUSED = "sale.added_amount_not_accepted"
#: A charge split in two whose second tender alone adds something: the refusal looks at every tender, not the first.
SPLIT = ({"method": "card", "amount": 1000}, {"method": "cash", "tendered": 1100, "extra": 300, "extra_label": "Tip"})


@pytest.fixture
def steak(product):
    return product("Steak", "STK", 1800, "restaurant.food")


def complete(*payments, key: str = "pos-steps-0001", ctx=None):
    return run("sale.sale.complete", {"idempotency_key": key, "lines": [{"product": "STK"}], "payments": list(payments)}, ctx)


def tipped(method: str, extra: int, **leg) -> dict:
    return {"method": method, "extra": extra, "extra_label": "Tip", **leg}


def refused(*payments, ctx=None) -> str:
    with pytest.raises(Conflict) as refusal:
        complete(*payments, ctx=ctx)
    return refusal.value.code


def test_with_a_step_at_the_charge_what_is_added_is_charged_on_every_tender(steak, a_step_at_the_charge):
    sale = complete(*SPLIT)
    assert [(leg.amount, leg.extra, leg.change) for leg in sale.payments] == [(1000, 0, 0), (800, 300, 0)]


def test_an_app_turned_off_takes_away_what_its_step_adds_to_the_charge(steak, a_step_at_the_charge, monkeypatch):
    monkeypatch.setattr(activation, "off_apps", lambda scope: frozenset({"demo"}))
    assert refused(tipped("card", 200)) == REFUSED
    assert refused(*SPLIT) == REFUSED
    assert Sale.objects.count() == 0


def test_what_is_added_is_refused_to_whoever_may_not_see_the_step(steak, monkeypatch):
    step = CheckoutStep(key="tip", component="TipStep", permission="demo.manage")
    monkeypatch.setattr(apps.get_app_config("demo"), "checkout", [step])
    assert refused(*SPLIT, ctx=ctx_for("hub_employee")) == REFUSED
    sale = complete(tipped("card", 200), ctx=ctx_for("hub_admin"))
    assert [(leg.amount, leg.extra) for leg in sale.payments] == [(1800, 200)]


def test_each_business_takes_what_is_added_only_with_a_step_of_its_own_apps(steak, a_step_at_the_charge, monkeypatch, hub_b):
    monkeypatch.setattr(activation, "off_apps", lambda scope: frozenset({"demo"}) if scope == B else frozenset())
    with use_hub(hub_b):
        run(
            "inventory.product.create",
            {"name": "Steak", "sku": "STK", "price": 2000, "tax_category_key": "restaurant.food"},
            system_context(B),
        )
        assert refused(tipped("card", 700), ctx=ctx_for(scope=B)) == REFUSED
        assert not Sale.objects.exists()
    complete(tipped("card", 700))
    assert [(leg.amount, leg.extra) for leg in SalePayment.objects.all()] == [(1800, 700)]
