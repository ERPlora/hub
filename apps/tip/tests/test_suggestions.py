"""The suggestions the charge sheet proposes (TIP-F02): with tips on, the three of the payment method chosen, each with the
tip it comes to on the check's total before discounts (a percentage rounded to the unit of the money, half up), which
one comes chosen and whether another amount is allowed; with tips off, nothing to propose."""

import pytest
from live.context import OperationContext
from live.errors import PermissionDenied
from live.operations import registry

from apps.sale.models import PaymentMethod
from base.tenancy.context import use_hub

from .conftest import HUB_DB, A, B, ctx_for, run

pytestmark = HUB_DB


def method(kind: str) -> PaymentMethod:
    return PaymentMethod.objects.get(type=kind, is_active=True)


def suggested(kind: str = "card", total: int = 1000, ctx=None):
    return run("tip.suggestion.get", {"method_id": str(method(kind).id), "total": total}, ctx)


def tips_on(ctx=None, **more):
    run("tip.settings.update", {"enabled": True, **more}, ctx)


def test_with_tips_off_there_is_nothing_to_propose():
    read = suggested()
    assert (read.enabled, read.suggestions) == (False, [])


def test_with_tips_on_the_factory_ones_come_as_the_tip_they_make_on_the_total():
    tips_on()
    read = suggested(total=1234)
    assert (read.enabled, read.allow_custom, read.preselected) == (True, True, 0)
    assert [(s.percent, s.amount) for s in read.suggestions] == [(3, 37), (5, 62), (10, 123)]


def test_a_percentage_is_rounded_to_the_unit_of_the_money_half_up():
    tips_on()
    assert [s.amount for s in suggested(total=50).suggestions] == [2, 3, 5]


def test_an_amount_is_the_same_whatever_the_total_and_each_method_has_its_own():
    mine = [{"percent": None, "amount": 100}, {"percent": 5, "amount": None}, {"percent": None, "amount": 500}]
    tips_on(methods=[{"method_id": str(method("card").id), "suggestions": mine}], preselected=2, allow_custom=False)
    card = suggested("card", total=2000)
    assert [(s.percent, s.amount) for s in card.suggestions] == [(None, 100), (5, 100), (None, 500)]
    assert (card.preselected, card.allow_custom) == (2, False)
    assert [s.amount for s in suggested("cash", total=2000).suggestions] == [60, 100, 200]


def test_whoever_records_tips_reads_them_and_nobody_else():
    assert registry["tip.suggestion.get"].permission == "tip.add_tip"
    assert suggested(ctx=ctx_for("hub_employee")).enabled is False
    with pytest.raises(PermissionDenied):
        suggested(ctx=OperationContext(scope=A, actor="viewer", permissions=frozenset({"tip.view_tip"})))


def test_each_business_proposes_its_own(hub_b):
    tips_on()
    with use_hub(hub_b):
        assert suggested(ctx=ctx_for(scope=B)).enabled is False
    assert suggested().enabled is True
