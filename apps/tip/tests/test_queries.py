"""The tips, newest first, a page at a time, with their search and filters (TIP-F03 to TIP-F06); an employee sees only
their own, and a business never sees another's."""

import datetime as dt

import pydantic
import pytest
from live.errors import NotFound
from django.utils import timezone

from apps.tip.models import Tip
from apps.tip.schemas import TipListIn
from base.tenancy.context import use_hub

from .conftest import CARD, HUB_DB, B, add_tip, as_user, charge, ctx_for, member, run, with_cash

pytestmark = HUB_DB


def listed(ctx=None, **params) -> list[int]:
    return [row.amount for row in run("tip.tip.list", params, ctx).rows]


@pytest.fixture
def three(coffee):
    """Three card tips: 100 for Bea, 200 for Ana and 300 to nobody, recorded in that order."""
    bea, ana = member("Bea"), member("Ana")
    sales = [charge(payments=CARD, staff_id=str(person.id)) for person in (bea, ana)] + [charge(payments=CARD)]
    tips = [add_tip(amount, sale_id=str(sale.id)) for amount, sale in zip((100, 200, 300), sales, strict=True)]
    return {"bea": bea, "ana": ana, "sales": sales, "tips": tips}


def test_newest_first_with_their_sale_person_and_method(three):
    page = run("tip.tip.list", {})
    assert [row.amount for row in page.rows] == [300, 200, 100]
    assert (page.total, page.limit, page.offset) == (3, 50, 0)
    newest = page.rows[0]
    assert (newest.sale_number, newest.member_name, newest.method_name) == (three["sales"][2].number, "", "Card")


def test_a_page_at_a_time_up_to_100():
    assert run("tip.tip.list", {"limit": 2, "offset": 1}).limit == 2
    with pytest.raises(pydantic.ValidationError):
        TipListIn.model_validate({"limit": 101})


def test_search_by_the_sale_number_or_the_persons_name(three):
    assert listed(search=three["sales"][1].number) == [200]
    assert listed(search="bea") == [100]


def test_filters_by_person_payment_method_and_status(three):
    assert listed(member_id=str(three["ana"].id)) == [200]
    assert listed(method_type="cash") == []
    run("tip.tip.void", {"id": str(three["tips"][0].id), "reason": "wrong sale"})
    assert listed(status="voided") == [100]
    assert listed(status="active") == [300, 200]


def test_filters_by_the_business_day_it_was_recorded(three):
    yesterday = timezone.now() - dt.timedelta(days=1)
    Tip.objects.filter(pk=three["tips"][0].id).update(created_at=yesterday)
    today = timezone.localdate()
    assert listed(date_from=today.isoformat()) == [300, 200]
    assert listed(date_to=(today - dt.timedelta(days=1)).isoformat()) == [100]


def test_an_employee_sees_only_their_own_tips(coffee, make_user):
    user = make_user("bea", role="hub_employee")
    bea = member("Bea", user_id=str(user.person.pk))
    add_tip(100, sale_id=str(charge(payments=CARD, staff_id=str(bea.id)).id))
    add_tip(200, sale_id=str(charge(payments=CARD).id))
    assert listed(as_user(user)) == [100]
    assert listed(ctx_for("hub_manager")) == [200, 100]


def test_an_employee_without_a_record_of_the_team_sees_none(coffee, make_user):
    add_tip(200, sale_id=str(charge(payments=CARD).id))
    assert listed(as_user(make_user("eva", role="hub_employee"))) == []


def test_a_business_never_sees_the_tips_of_another(hub_b):
    with_cash()
    run("cash_register.settings.update", {"enable_cash_register": False})
    run("tip.tip.add", {"amount": 500, "pool": True})
    with use_hub(hub_b):
        assert listed(ctx_for(scope=B)) == []
        with_cash(ctx_for(scope=B))
        run("cash_register.settings.update", {"enable_cash_register": False}, ctx_for(scope=B))
        run("tip.tip.add", {"amount": 700, "pool": True}, ctx_for(scope=B))
        assert listed(ctx_for(scope=B)) == [700]
    assert listed() == [500]


def test_one_tip_by_its_id_or_its_sale_s_number(three):
    tip, sale = three["tips"][1], three["sales"][1]
    by_id = run("tip.tip.get", {"id": str(tip.id)})
    assert (by_id.id, by_id.sale_number, by_id.member_name, by_id.amount) == (tip.id, sale.number, "Ana Ruiz", 200)
    assert run("tip.tip.get", {"sale": sale.number}).id == tip.id


def test_a_tip_that_does_not_exist_is_not_found():
    with pytest.raises(NotFound) as refused:
        run("tip.tip.get", {"id": "0190f0f0-0000-7000-8000-000000000000"})
    assert refused.value.code == "tip.tip_not_found"


def test_an_employee_reads_only_their_own_tip(coffee, make_user):
    user = make_user("bea", role="hub_employee")
    bea = member("Bea", user_id=str(user.person.pk))
    own = add_tip(100, sale_id=str(charge(payments=CARD, staff_id=str(bea.id)).id))
    other = add_tip(200, sale_id=str(charge(payments=CARD).id))
    assert run("tip.tip.get", {"id": str(own.id)}, as_user(user)).id == own.id
    with pytest.raises(NotFound):
        run("tip.tip.get", {"id": str(other.id)}, as_user(user))
