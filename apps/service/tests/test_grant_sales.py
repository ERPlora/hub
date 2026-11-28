"""Saying later which sale charged a voucher granted without it (SERVICE-F36), with Sales' real operations.

From that moment its sessions count for whoever does them; the ones already done keep what they were worth; and its
line stops counting for whoever sold it on the day of that sale, as when the sale is said on granting it (SERVICE-F14).
"""

import datetime as dt
from uuid import uuid7

import pytest
from live.context import Scope
from live.errors import Conflict, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import registry
from pydantic import ValidationError

from apps.sale.models.sales import Sale, SaleLine
from apps.sale.models.voucher_sessions import VoucherSession
from apps.sale.tests.conftest import by_staff, charged_open, ctx_for, professional, redeem, run
from apps.service.models.grants import Grant, Redemption
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

from .conftest import HUB_DB

pytestmark = HUB_DB

LINK = "service.grant.link"


@pytest.fixture
def haircut(db):
    return run("service.service.create", {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"})


@pytest.fixture
def lucia(db):
    return run("customer.customer.create", {"name": "Lucía Pérez"})


def voucher(owner, service, *, uses=5, amount=10000, ctx=None):
    """A voucher of ``uses`` sessions of ``service`` granted to ``owner`` for ``amount``, without its sale unless said."""
    package = run(
        "service.package.create",
        {"name": f"Bono {uuid7().hex[-8:]}", "max_uses": uses, "items": [{"service_id": str(service.id)}]},
        ctx,
    )
    return run(
        "service.grant.create",
        {"package_id": str(package.id), "customer_id": str(owner.id), "amount": amount},
        ctx,
    )


def link(grant, ctx=None, **said):
    return run(LINK, {"id": str(grant.id), **said}, ctx)


def sold_once():
    """A sale charged at the till for 100.00 by Ana, a professional of the team: Ana and the sale."""
    seller = professional("Ana")
    return seller, charged_open("sold-0001", ("Bono de 100", 10000, seller))


def test_a_voucher_granted_without_its_sale_counts_for_who_does_its_sessions_once_it_is_said(haircut, lucia):
    # flow: SERVICE-F36: the reproduction of hub#786, 0 for whoever does its sessions while it says no sale.
    seller, sold = sold_once()
    bea = professional("Bea")
    grant = voucher(lucia, haircut, uses=3)
    linked = link(grant, sale_id=str(sold.id))
    redeem(grant, member=bea)
    rows = by_staff()
    assert (rows[seller].production_total, rows[bea].production_total) == (0, 3333)
    assert (Grant.objects.get(pk=grant.id).sale_line_id, linked.sale_id) == (sold.lines[0].id, sold.id)


def test_the_sessions_done_before_keep_what_they_were_worth_and_the_rest_share_all_that_was_paid(haircut, lucia):
    _seller, sold = sold_once()
    bea = professional("Bea")
    grant = voucher(lucia, haircut, uses=5)
    early = [redeem(grant, member=bea).id for _ in range(2)]
    link(grant, sale_id=str(sold.id))
    later = [redeem(grant, member=bea).id for _ in range(3)]
    value = dict(Redemption.objects.filter(grant_id=grant.id).values_list("id", "value"))
    assert [value[session] for session in early + later] == [0, 0, 3333, 3334, 3333]
    # What Sales counted for them stays as it was, on the day they were done.
    counted = dict(VoucherSession.objects.values_list("session_id", "value"))
    assert [counted[session] for session in early] == [0, 0]
    assert by_staff()[bea].voucher_total == 10000


def test_the_line_stops_counting_for_who_sold_it_on_the_day_of_its_sale(haircut, lucia):
    seller, sold = sold_once()
    today = run("sale.business_day.get").today
    sale_day = today - dt.timedelta(days=40)
    Sale.objects.filter(pk=sold.id).update(business_day=sale_day)
    on_that_day = {"date_from": str(sale_day), "date_to": str(sale_day)}
    grant = voucher(lucia, haircut)
    assert by_staff(**on_that_day)[seller].production_total == 10000
    link(grant, sale_id=str(sold.id))
    row = by_staff(**on_that_day)[seller]
    assert (row.total_revenue, row.voucher_sold_total, row.production_total) == (10000, 10000, 0)
    assert seller not in by_staff(date_from=str(today), date_to=str(today))


def test_a_voucher_whose_sale_is_said_twice_is_refused_and_its_line_counts_once(haircut, lucia):
    seller = professional("Ana")
    sold = charged_open("sold-0001", ("Dos bonos", 20000, seller))
    grant = voucher(lucia, haircut)
    link(grant, sale_id=str(sold.id))
    with pytest.raises(Conflict) as refusal:
        link(grant, sale_id=str(sold.id))
    assert refusal.value.code == "service.grant_already_sold"
    assert SaleLine.objects.get(pk=sold.lines[0].id).voucher_sold_amount == 10000
    assert by_staff()[seller].production_total == 10000


def test_a_voucher_granted_saying_its_sale_has_no_sale_left_to_say(haircut, lucia):
    _seller, sold = sold_once()
    package = run("service.package.create", {"name": "Bono de 100", "max_uses": 3, "items": [{"service_id": str(haircut.id)}]})
    grant = run(
        "service.grant.create",
        {"package_id": str(package.id), "customer_id": str(lucia.id), "amount": 10000, "sale_id": str(sold.id)},
    )
    with pytest.raises(Conflict) as refusal:
        link(grant, sale_id=str(sold.id))
    assert refusal.value.code == "service.grant_already_sold"


def test_a_line_that_already_paid_another_voucher_is_refused(haircut, lucia):
    seller, sold = sold_once()
    paid = voucher(lucia, haircut)
    link(paid, sale_id=str(sold.id))
    other = voucher(lucia, haircut)
    with pytest.raises(Conflict) as refusal:
        link(other, sale_id=str(sold.id))
    assert refusal.value.code == "sale.voucher_over_line"
    assert Grant.objects.get(pk=other.id).sale_line_id is None
    assert SaleLine.objects.get(pk=sold.lines[0].id).voucher_sold_amount == 10000
    assert not OutboxEvent.objects.filter(name="service.grant.sale_linked", payload__id=str(other.id)).exists()
    assert by_staff()[seller].production_total == 0


def test_the_sale_is_checked_as_when_granting(haircut, lucia):
    first = charged_open("sold-0001", ("Bono de 100", 10000, None))
    several = charged_open("sold-0002", ("Bono de 100", 10000, None), ("Champú", 1200, None))
    grant = voucher(lucia, haircut)
    with pytest.raises(NotFound) as refusal:
        link(grant, sale_id=str(several.id), sale_line_id=str(first.lines[0].id))
    assert refusal.value.code == "sale.sale_line_not_found"
    with pytest.raises(Conflict) as refusal:
        link(grant, sale_id=str(several.id))
    assert refusal.value.code == "sale.voucher_line_required"
    # The line alone names its sale.
    link(grant, sale_line_id=str(first.lines[0].id))
    assert Grant.objects.get(pk=grant.id).sale_id == first.id


def expired(grant):
    Grant.objects.filter(pk=grant.id).update(validity_days=1, granted_at=Grant.objects.get(pk=grant.id).granted_at - dt.timedelta(days=3))


def used_up(grant):
    redeem(grant)


def voided(grant):
    run("service.grant.void", {"id": str(grant.id), "reason": "wrong customer"})


@pytest.mark.parametrize(
    ("spoil", "uses", "amount", "code"),
    [
        (None, 3, 0, "service.grant_given_away"),
        (voided, 3, 10000, "service.grant_voided"),
        (expired, 3, 10000, "service.grant_expired"),
        (used_up, 1, 10000, "service.grant_no_uses_left"),
    ],
    ids=["given away", "voided", "expired", "used up"],
)
def test_a_voucher_with_no_session_left_to_count_says_no_sale(haircut, lucia, spoil, uses, amount, code):
    _seller, sold = sold_once()
    grant = voucher(lucia, haircut, uses=uses, amount=amount)
    if spoil:
        spoil(grant)
    with pytest.raises(Conflict) as refusal:
        link(grant, sale_id=str(sold.id))
    assert refusal.value.code == code
    assert SaleLine.objects.get(pk=sold.lines[0].id).voucher_sold_amount == 0
    assert Grant.objects.get(pk=grant.id).sale_line_id is None


def test_an_unlimited_voucher_says_its_sale_too(haircut, lucia):
    seller, sold = sold_once()
    package = run("service.package.create", {"name": "Bono libre", "items": [{"service_id": str(haircut.id)}]})
    grant = run("service.grant.create", {"package_id": str(package.id), "customer_id": str(lucia.id), "amount": 10000})
    link(grant, sale_id=str(sold.id))
    assert by_staff()[seller].production_total == 0


def test_neither_a_sale_nor_a_line_is_refused_before_anything(haircut, lucia):
    with pytest.raises(ValidationError) as refusal:
        link(voucher(lucia, haircut))
    assert "Say which sale charged the voucher." in str(refusal.value)


def test_with_sales_off_there_is_no_sale_to_say(haircut, lucia, monkeypatch):
    grant = voucher(lucia, haircut)
    for name in [name for name in registry if name.startswith("sale.")]:
        monkeypatch.delitem(registry, name)
    with pytest.raises(Conflict) as refusal:
        link(grant, sale_id=str(uuid7()))
    assert refusal.value.code == "service.sales_unavailable"
    assert Grant.objects.get(pk=grant.id).sale_id is None


def test_saying_the_sale_is_told_in_the_outbox_with_the_line(haircut, lucia):
    _seller, sold = sold_once()
    grant = voucher(lucia, haircut)
    link(grant, sale_id=str(sold.id))
    told = OutboxEvent.objects.get(name="service.grant.sale_linked")
    assert told.payload == {
        "id": str(grant.id),
        "package_id": str(Grant.objects.get(pk=grant.id).package_id),
        "customer_id": str(lucia.id),
        "sale_id": str(sold.id),
        "sale_line_id": str(sold.lines[0].id),
    }
    # The commission screens hear of the line too.
    assert OutboxEvent.objects.filter(name="sale.sale.voucher_line_changed").count() == 1


def test_voiding_it_afterwards_gives_the_line_back_to_who_sold_it(haircut, lucia):
    seller, sold = sold_once()
    grant = voucher(lucia, haircut)
    link(grant, sale_id=str(sold.id))
    run("service.grant.void", {"id": str(grant.id), "reason": "wrong customer"})
    assert by_staff()[seller].production_total == 10000


def test_a_manager_says_it_and_an_employee_may_not(haircut, lucia):
    _seller, sold = sold_once()
    grant = voucher(lucia, haircut)
    with pytest.raises(PermissionDenied):
        link(grant, ctx_for("hub_employee"), sale_id=str(sold.id))
    link(grant, ctx_for("hub_manager"), sale_id=str(sold.id))
    assert Grant.objects.get(pk=grant.id).sale_id == sold.id


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_sale_of_one_business_is_no_sale_of_another(hub_a, hub_b):
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    with use_hub(hub_a):
        sold = charged_open("sold-a-0001", ("Bono de 100", 10000, None), ctx=in_a)
    with use_hub(hub_b):
        cut = run("service.service.create", {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"}, in_b)
        owner = run("customer.customer.create", {"name": "Lucía Pérez"}, in_b)
        grant = voucher(owner, cut, ctx=in_b)
        with pytest.raises(NotFound) as refusal:
            link(grant, in_b, sale_line_id=str(sold.lines[0].id))
        assert refusal.value.code == "sale.sale_line_not_found"
    assert SaleLine.objects.using(hubs.HUB_A_ALIAS).get(pk=sold.lines[0].id).voucher_sold_amount == 0
