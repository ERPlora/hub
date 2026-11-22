"""Sale and Services together, no mocks (SALE-F28; SERVICE-F21, F24): what a session of a voucher counts for
whoever does it, spent at the till or outside it.
"""

import datetime as dt
from uuid import uuid7

import pytest
from live.context import Scope
from live.errors import PermissionDenied
from live.models import OutboxEvent
from live.operations import get, registry

from apps.sale.models import Sale, SaleLine, VoucherSession
from apps.sale.tests.conftest import HUB_DB, by_staff, charge, charged_open, ctx_for, pay_with, professional, redeem, refund, run, spend_session, svc, voucher_of_100
from apps.service.models import Grant, Redemption
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

pytestmark = HUB_DB

EMPLOYEE = "hub_employee"


# ── What a session counts for whoever does it (SALE-F28, SERVICE-F24) ────────────────────────


def test_a_session_counts_for_who_does_it_though_the_line_charged_nothing(haircut, lucia):
    # flow: SALE-F28: the reproduction of hub#685, gross_total 0 and nothing else to read.
    ana = uuid7()
    sale = spend_session(voucher_of_100(lucia, haircut), haircut, lucia, "value-0001", staff=ana)
    assert (sale.total, SaleLine.objects.get(sale=sale.id).voucher_value) == (0, 3333)
    row = by_staff()[ana]
    assert (row.sales_count, row.voucher_total, row.production_total) == (1, 3333, 3333)
    # Her line charged nothing: the money figures stay what they say. The period's revenue is the voucher's own sale.
    assert (row.gross_total, row.net_total, row.tax_total, row.total_revenue) == (0, 0, 0, 0)
    assert run("sale.sale.stats", {}).total_revenue == 10000


def test_the_three_sessions_of_a_voucher_of_100_euros_add_up_to_what_was_paid(haircut, lucia):
    ana, bea = uuid7(), uuid7()
    grant = voucher_of_100(lucia, haircut)
    spend_session(grant, haircut, lucia, "value-0001", staff=ana)
    spend_session(grant, haircut, lucia, "value-0002", staff=bea)
    spend_session(grant, haircut, lucia, "value-0003", staff=ana)
    rows = by_staff()
    assert (rows[ana].voucher_total, rows[bea].voucher_total) == (3333 + 3333, 3334)
    assert rows[ana].voucher_total + rows[bea].voucher_total == 10000


def test_a_line_that_names_nobody_counts_for_who_serves_the_check(haircut, lucia):
    ana, bea = uuid7(), uuid7()
    grant = voucher_of_100(lucia, haircut)
    spend_session(grant, haircut, lucia, "value-0001", sale_staff=ana)
    spend_session(grant, haircut, lucia, "value-0002", staff=bea, sale_staff=ana)
    rows = by_staff()
    assert (rows[ana].voucher_total, rows[bea].voucher_total) == (3333, 3334)


def test_what_was_charged_is_not_rewritten_when_the_voucher_changes_later(haircut, lucia):
    # flow: SALE-F27: the value is fixed at the charge, like the name of the voucher on the line.
    ana = uuid7()
    grant = voucher_of_100(lucia, haircut)
    spend_session(grant, haircut, lucia, "value-0001", staff=ana)
    svc(
        "service.package.update",
        {"id": str(grant.package_id), "max_uses": 10, "fixed_price": 90000},
    )
    svc("service.grant.adjust", {"id": str(grant.id), "uses_delta": 5, "reason": "courtesy"})
    assert by_staff()[ana].voucher_total == 3333


def test_a_session_keeps_counting_with_services_off(haircut, lucia, services_off):
    ana = uuid7()
    spend_session(voucher_of_100(lucia, haircut), haircut, lucia, "value-0001", staff=ana)
    services_off()
    assert by_staff()[ana].production_total == 3333


def test_voiding_the_sale_takes_the_session_off_who_did_it(haircut, lucia):
    ana = uuid7()
    grant = voucher_of_100(lucia, haircut)
    sale = spend_session(grant, haircut, lucia, "value-0001", staff=ana)
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "wrong customer"})
    assert ana not in by_staff()
    # Its share went back to the voucher, for the session spent in its place.
    bea = uuid7()
    spend_session(grant, haircut, lucia, "value-0002", staff=bea)
    assert by_staff()[bea].voucher_total == 3333


def test_refunding_the_session_takes_it_off_who_did_it_though_no_money_moved(haircut, lucia):
    ana = uuid7()
    grant = voucher_of_100(lucia, haircut)
    kept = spend_session(grant, haircut, lucia, "value-0001", staff=ana)
    back = spend_session(grant, haircut, lucia, "value-0002", staff=ana)
    done = refund(back, lines=[back.lines[0]], key="value-refund-0001")
    assert done.total == 0
    row = by_staff()[ana]
    assert (row.voucher_total, row.production_total, row.refunded_total) == (3333, 3333, 0)
    assert SaleLine.objects.get(sale=kept.id).voucher_value == 3333
    # The sale that went back stays with its value: a sale is never edited.
    assert SaleLine.objects.get(sale=back.id).voucher_value == 3334


def test_a_professional_whose_only_session_came_back_counts_nothing(haircut, lucia):
    ana = uuid7()
    sale = spend_session(voucher_of_100(lucia, haircut), haircut, lucia, "value-0001", staff=ana)
    refund(sale, lines=[sale.lines[0]], key="value-refund-0001")
    row = by_staff()[ana]
    assert (row.sales_count, row.voucher_total, row.production_total) == (1, 0, 0)


def test_a_session_and_money_add_up_in_what_the_commission_goes_on(haircut, colour, lucia):
    # Bea charged more money, Ana made more with the session: the list goes by what each one produced.
    ana, bea = uuid7(), uuid7()
    grant = voucher_of_100(lucia, haircut, uses=1)
    order = run(
        "sale.order.open",
        {
            "service_lines": [
                {"service_id": str(haircut.id), "staff_id": str(ana)},
                {"service_id": str(haircut.id), "staff_id": str(ana)},
                {"service_id": str(haircut.id), "staff_id": str(bea)},
                {"service_id": str(haircut.id), "staff_id": str(bea)},
            ]
        },
    )
    order = pay_with(order, order.lines[0].id, grant)
    charge(order, key="value-0001", customer_id=str(lucia.id), payments=[{"method": "card"}])
    rows = run("sale.sale.by_staff", {}).rows
    assert [
        (row.staff_id, row.gross_total, row.total_revenue, row.voucher_total, row.production_total)
        for row in rows
    ] == [
        (ana, 2500, 2500, 10000, 12500),
        (bea, 5000, 5000, 0, 5000),
    ]
    # With the voucher's own sale, which nobody served, the rows square with the period's revenue.
    assert sum(row.total_revenue for row in rows) + 10000 == run("sale.sale.stats", {}).total_revenue


def test_a_session_of_an_unlimited_voucher_counts_at_the_price_of_its_line(haircut, lucia):
    # There are no sessions to divide by: like a salon's till (Meevo), at the service's own price, frozen on the line.
    ana = uuid7()
    grant = voucher_of_100(lucia, haircut, name="Bono sin límite", uses=None)
    spend_session(grant, haircut, lucia, "value-0001", staff=ana)
    assert by_staff()[ana].voucher_total == 2500


def test_a_line_no_voucher_pays_is_worth_no_session(haircut, lucia):
    ana = uuid7()
    order = run(
        "sale.order.open", {"service_lines": [{"service_id": str(haircut.id), "staff_id": str(ana)}]}
    )
    sale = charge(order, key="value-0001", payments=[{"method": "card"}])
    assert SaleLine.objects.get(sale=sale.id).voucher_value == 0
    row = by_staff()[ana]
    assert (row.voucher_total, row.production_total) == (0, 2500)


def test_the_session_counts_on_the_business_day_of_its_sale(haircut, lucia):
    ana = uuid7()
    sale = spend_session(voucher_of_100(lucia, haircut), haircut, lucia, "value-0001", staff=ana)
    day = Sale.objects.get(pk=sale.id).business_day
    assert by_staff(date_from=str(day), date_to=str(day))[ana].voucher_total == 3333
    assert ana not in by_staff(date_from=str(day + dt.timedelta(days=1)))


# ── A session spent outside the till (SERVICE-F21, hub#770): no line carries it ─────────────


def voucher_of_100_in(ctx, *, seller=None):
    """In the business of ``ctx``: a haircut of 25.00, Lucía and a voucher of 3 sessions of it, charged at the till for
    100.00 (by ``seller``) and granted saying that sale. Its service, its owner, the voucher sold and the sale."""
    cut = run("service.service.create", {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"}, ctx)
    owner = run("customer.customer.create", {"name": "Lucía Pérez"}, ctx)
    package = run(
        "service.package.create", {"name": "Bono de 100", "max_uses": 3, "items": [{"service_id": str(cut.id)}]}, ctx
    )
    sold = charged_open("value-b-0000", ("Bono de 100", 10000, seller), ctx=ctx)
    grant = run(
        "service.grant.create",
        {"package_id": str(package.id), "customer_id": str(owner.id), "amount": 10000, "sale_id": str(sold.id)},
        ctx,
    )
    return cut, owner, grant, sold


def test_a_session_spent_outside_the_till_counts_for_who_did_it(haircut, lucia):
    # flow: SERVICE-F21, SALE-F28: the reproduction of hub#770, `rows: []` before.
    ana, bea = professional("Ana"), professional("Bea")
    redeem(voucher_of_100(lucia, haircut), member=ana, service=haircut)
    charged_open("money-0001", ("Corte", 2500, bea))
    rows = run("sale.sale.by_staff", {}).rows
    assert [
        (row.staff_id, row.sales_count, row.gross_total, row.total_revenue, row.voucher_total, row.production_total)
        for row in rows
    ] == [(ana, 0, 0, 0, 3333, 3333), (bea, 1, 2500, 2500, 0, 2500)]
    assert VoucherSession.objects.get().session_id == Redemption.objects.get(order_line_id=None).id


def test_a_session_at_the_till_and_one_outside_it_count_once_each(haircut, lucia):
    ana = professional("Ana")
    grant = voucher_of_100(lucia, haircut)
    spend_session(grant, haircut, lucia, "value-0001", staff=ana)
    redeem(grant, member=ana)
    row = by_staff()[ana]
    assert (row.sales_count, row.voucher_total, row.production_total) == (1, 3333 + 3334, 3333 + 3334)
    # The session of the till is on its line, the other one apart: neither is in both.
    assert VoucherSession.objects.count() == 1


def test_a_session_outside_the_till_that_names_nobody_counts_for_nobody(haircut, lucia):
    grant = voucher_of_100(lucia, haircut)
    redeem(grant)
    assert by_staff() == {}
    ana = professional("Ana")
    redeem(grant, member=ana)
    # The one that named nobody kept its share of the price: Ana's is the second of three.
    assert {staff_id: row.voucher_total for staff_id, row in by_staff().items()} == {ana: 3334}


def test_a_session_outside_the_till_keeps_counting_with_services_off(haircut, lucia, services_off):
    ana = professional("Ana")
    redeem(voucher_of_100(lucia, haircut), member=ana)
    services_off()
    assert by_staff()[ana].production_total == 3333


def test_a_session_outside_the_till_counts_on_the_business_day_it_was_spent(haircut, lucia):
    ana = professional("Ana")
    redeem(voucher_of_100(lucia, haircut), member=ana)
    today = run("sale.business_day.get").today
    assert by_staff(date_from=str(today), date_to=str(today))[ana].voucher_total == 3333
    assert ana not in by_staff(date_from=str(today + dt.timedelta(days=1)))
    assert ana not in by_staff(date_to=str(today - dt.timedelta(days=1)))


def test_a_session_outside_the_till_of_an_unlimited_voucher_counts_at_her_price_of_the_service(haircut, lucia):
    # As the till counts it, at the price of its line: her own price for the service, else the service's. Without the
    # service said there is nothing to price it by.
    ana, bea = professional("Ana"), professional("Bea")
    run("service.assignment.assign", {"service_id": str(haircut.id), "member_id": str(ana), "custom_price": 3000})
    grant = voucher_of_100(lucia, haircut, name="Bono sin límite", uses=None)
    redeem(grant, member=ana, service=haircut)
    redeem(grant, member=bea, service=haircut)
    redeem(grant, member=bea)
    rows = by_staff()
    assert (rows[ana].voucher_total, rows[bea].voucher_total) == (3000, 2500)
    assert Redemption.objects.filter(value=None).count() == 3


def test_a_session_told_twice_counts_once(lucia):
    session, ana = uuid7(), uuid7()
    for _ in range(2):
        run("sale.voucher_session.record", {"session_id": str(session), "staff_id": str(ana), "value": 3333})
    assert by_staff()[ana].voucher_total == 3333
    assert VoucherSession.objects.count() == 1
    # The second telling changed nothing: nothing to repaint.
    assert OutboxEvent.objects.filter(name="sale.voucher_session.recorded").count() == 1


def test_who_may_not_sell_may_not_say_who_did_a_session():
    op = get("sale.voucher_session.record")
    assert op.permission == "sale.add_sale"
    employee = ctx_for(EMPLOYEE)
    no_sell = employee.__class__(**{**employee.__dict__, "permissions": employee.permissions - {"sale.add_sale"}})
    with pytest.raises(PermissionDenied):
        op(no_sell, op.input.model_validate({"session_id": str(uuid7()), "staff_id": str(uuid7()), "value": 1}))
    assert not VoucherSession.objects.exists()


def test_the_employee_who_spends_a_session_says_who_did_it_with_their_own_permissions(haircut, lucia):
    ana = professional("Ana")
    redeem(voucher_of_100(lucia, haircut), member=ana, ctx=ctx_for(EMPLOYEE))
    assert by_staff()[ana].voucher_total == 3333


def test_with_sales_off_the_session_is_spent_and_says_who_did_it_all_the_same(haircut, lucia, monkeypatch):
    ana = professional("Ana")
    grant = voucher_of_100(lucia, haircut)
    for name in [name for name in registry if name.startswith("sale.")]:
        monkeypatch.delitem(registry, name)
    out = redeem(grant, member=ana)
    assert (out.remaining, Redemption.objects.get(pk=out.id).member_id) == (2, ana)
    assert not VoucherSession.objects.exists()


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_session_outside_the_till_in_one_business_counts_nothing_in_another(hub_a, hub_b):
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    with use_hub(hub_b):
        _cut, _owner, grant, _sold = voucher_of_100_in(in_b)
        ana = professional("Ana", in_b)
        redeem(grant, member=ana, ctx=in_b)
        # Positive control: it counts, in its own business.
        assert {row.staff_id: row.production_total for row in run("sale.sale.by_staff", {}, in_b).rows} == {
            ana: 3333
        }
    with use_hub(hub_a):
        assert run("sale.sale.by_staff", {}, in_a).rows == []
    assert VoucherSession.objects.using(hubs.HUB_B_ALIAS).get().staff_id == ana


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_session_in_one_business_counts_nothing_in_another(hub_a, hub_b):
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    ana, seller = uuid7(), uuid7()
    with use_hub(hub_b):
        cut, owner, grant, sold = voucher_of_100_in(in_b, seller=seller)
        spend_session(grant, cut, owner, "value-b-0001", staff=ana, ctx=in_b)
        # Positive control: they count, in their own business.
        rows = {row.staff_id: row for row in run("sale.sale.by_staff", {}, in_b).rows}
        assert (rows[ana].production_total, rows[seller].production_total) == (3333, 0)
    with use_hub(hub_a):
        assert run("sale.sale.by_staff", {}, in_a).rows == []
    assert Grant.objects.using(hubs.HUB_B_ALIAS).get(pk=grant.id).sale_line_id == sold.lines[0].id
