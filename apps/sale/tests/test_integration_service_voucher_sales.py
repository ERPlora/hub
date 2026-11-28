"""Sale and Services together, no mocks (SALE-F28; SERVICE-F14): the line of a sale that charged a voucher counts
for whoever sold it, until its sessions are done, the voucher is voided or the money goes back.
"""

from uuid import uuid7

import pytest
from live.errors import Conflict, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get, registry

from apps.sale.models.sales import SaleLine
from apps.sale.tests.conftest import HUB_DB, by_staff, charge, charged_open, check, ctx_for, grant_for, last_event, pay_with, refund, run, spend_session, svc, voucher_of_100
from apps.service.models.grants import Grant

pytestmark = HUB_DB

EMPLOYEE = "hub_employee"


# ── The line that sold a voucher (hub#769, SERVICE-F14) ─────────────────────────────────────


def test_a_voucher_sold_by_one_and_done_by_another_counts_once_and_to_the_cent(haircut, lucia):
    # flow: SERVICE-F14, SALE-F28: A sells it and counts 0; B does its 3 sessions and adds up 100.00. Money stays money.
    seller, doer = uuid7(), uuid7()
    grant = voucher_of_100(lucia, haircut, seller=seller)
    for key in ("value-0001", "value-0002", "value-0003"):
        spend_session(grant, haircut, lucia, key, staff=doer)
    rows = by_staff()
    assert (
        rows[seller].gross_total,
        rows[seller].total_revenue,
        rows[seller].voucher_sold_total,
        rows[seller].voucher_total,
        rows[seller].production_total,
    ) == (10000, 10000, 10000, 0, 0)
    assert (
        rows[doer].gross_total,
        rows[doer].total_revenue,
        rows[doer].voucher_sold_total,
        rows[doer].voucher_total,
        rows[doer].production_total,
    ) == (0, 0, 0, 10000, 10000)
    assert sum(row.production_total for row in rows.values()) == run("sale.sale.stats", {}).total_revenue == 10000
    assert Grant.objects.get(pk=grant.id).sale_line_id == SaleLine.objects.get(name="Bono de 100").id
    assert last_event("sale.sale.voucher_line_changed")["sale_id"] == str(SaleLine.objects.get(name="Bono de 100").sale_id)


def test_the_list_goes_by_what_each_one_produced_once_the_voucher_is_out(haircut, lucia):
    seller, doer = uuid7(), uuid7()
    grant = voucher_of_100(lucia, haircut, seller=seller)
    spend_session(grant, haircut, lucia, "value-0001", staff=doer)
    assert [row.staff_id for row in run("sale.sale.by_staff", {}).rows] == [doer, seller]


def test_a_voucher_granted_without_its_sale_counts_nothing_so_nothing_counts_twice(haircut, lucia):
    # flow: SERVICE-F14: its money may be on a line nobody named: that line counts for who sold it, as it did, and the
    # sessions for nobody. The same for a voucher sold before this existed (hub#769).
    seller, doer = uuid7(), uuid7()
    charged_open("sold-0001", ("Bono de 100", 10000, seller))
    grant = grant_for(lucia, haircut)
    sale = spend_session(grant, haircut, lucia, "value-0001", staff=doer)
    rows = by_staff()
    assert (rows[seller].production_total, rows[doer].production_total) == (10000, 0)
    assert SaleLine.objects.get(sale=sale.id).voucher_value == 0
    assert Grant.objects.get(pk=grant.id).sale_line_id is None


def test_a_voucher_given_away_needs_no_line_and_takes_none_out(haircut, lucia):
    seller = uuid7()
    sold = charged_open("sold-0001", ("Corte", 2500, seller), ("Champú", 1200, seller))
    grant = grant_for(lucia, haircut, amount=0, sale_id=str(sold.id))
    assert Grant.objects.get(pk=grant.id).sale_line_id is None
    assert by_staff()[seller].production_total == 3700


def test_a_sale_of_several_lines_says_which_one_paid_the_voucher(haircut, lucia):
    seller = uuid7()
    sold = charged_open("sold-0001", ("Bono de 100", 10000, seller), ("Champú", 1200, seller))
    with pytest.raises(Conflict) as refusal:
        grant_for(lucia, haircut, sale_id=str(sold.id))
    assert refusal.value.code == "sale.voucher_line_required"
    # It says the lines to choose from: the name of each is what a person tells them apart by.
    assert "Bono de 100" in str(refusal.value) and "Champú" in str(refusal.value)
    assert not Grant.objects.exists()
    line = next(line for line in sold.lines if line.name == "Bono de 100")
    grant = grant_for(lucia, haircut, name="Otro bono", sale_id=str(sold.id), sale_line_id=str(line.id))
    assert Grant.objects.get(pk=grant.id).sale_line_id == line.id
    # What is left for who sold them is the shampoo.
    assert by_staff()[seller].production_total == 1200


def test_the_line_alone_names_its_sale(haircut, lucia):
    sold = charged_open("sold-0001", ("Bono de 100", 10000, None))
    grant = grant_for(lucia, haircut, sale_line_id=str(sold.lines[0].id))
    assert Grant.objects.get(pk=grant.id).sale_id == sold.id


def test_a_line_of_another_sale_or_a_sale_that_does_not_exist_is_refused(haircut, lucia):
    one = charged_open("sold-0001", ("Bono de 100", 10000, None))
    other = charged_open("sold-0002", ("Bono de 100", 10000, None))
    with pytest.raises(NotFound) as refusal:
        grant_for(lucia, haircut, sale_id=str(one.id), sale_line_id=str(other.lines[0].id))
    assert refusal.value.code == "sale.sale_line_not_found"
    with pytest.raises(NotFound) as refusal:
        grant_for(lucia, haircut, name="Otro", sale_id=str(uuid7()))
    assert refusal.value.code == "sale.sale_not_found"
    with pytest.raises(NotFound) as refusal:
        grant_for(lucia, haircut, name="Otro más", sale_line_id=str(uuid7()))
    assert refusal.value.code == "sale.sale_line_not_found"
    assert not Grant.objects.exists()


def test_a_line_pays_no_more_vouchers_than_it_charged(haircut, lucia):
    # Two vouchers charged on a line of two units fit; a third, or one dearer than the line, does not.
    seller = uuid7()
    order = run(
        "sale.order.open",
        {
            "open_lines": [
                {
                    "name": "Bono x 2",
                    "unit_price": 10000,
                    "quantity": "2",
                    "tax_category_key": "service.generic",
                    "staff_id": str(seller),
                }
            ]
        },
    )
    sold = charge(order, key="sold-0001", payments=[{"method": "card"}])
    grant_for(lucia, haircut, name="Uno", sale_id=str(sold.id))
    assert by_staff()[seller].production_total == 10000
    grant_for(lucia, haircut, name="Dos", sale_id=str(sold.id))
    assert by_staff()[seller].production_total == 0
    with pytest.raises(Conflict) as refusal:
        grant_for(lucia, haircut, name="Tres", amount=1, sale_id=str(sold.id))
    assert refusal.value.code == "sale.voucher_over_line"
    assert Grant.objects.count() == 2
    # Voiding one gives back only its part of the line.
    svc("service.grant.void", {"id": str(Grant.objects.get(package__name="Uno").id), "reason": "wrong customer"})
    assert by_staff()[seller].production_total == 10000


def test_a_line_a_voucher_paid_is_no_line_to_choose_from(haircut, lucia):
    # It charged 0: the only line that charged anything is the voucher's, with nothing to guess.
    seller = uuid7()
    other = voucher_of_100(lucia, haircut, name="El de la clienta", key="sold-0000")
    order = run(
        "sale.order.open",
        {
            "service_lines": [{"service_id": str(haircut.id)}],
            "open_lines": [
                {"name": "Otro bono", "unit_price": 5000, "tax_category_key": "service.generic", "staff_id": str(seller)}
            ],
        },
    )
    covered = next(line for line in order.lines if line.service_id)
    order = pay_with(order, covered.id, other)
    sold = charge(order, key="sold-0001", customer_id=str(lucia.id), payments=[{"method": "card"}])
    grant = grant_for(lucia, haircut, name="Otro bono", amount=5000, sale_id=str(sold.id))
    assert Grant.objects.get(pk=grant.id).sale_line_id == SaleLine.objects.get(sale=sold.id, name="Otro bono").id
    assert by_staff()[seller].production_total == 0


def test_a_sale_that_charged_nothing_pays_for_no_voucher(haircut, lucia):
    other = voucher_of_100(lucia, haircut, name="El de la clienta", key="sold-0000")
    order = check(haircut)
    sold = charge(pay_with(order, order.lines[0].id, other), key="sold-0001", customer_id=str(lucia.id))
    assert sold.total == 0
    with pytest.raises(Conflict) as refusal:
        grant_for(lucia, haircut, name="Otro bono", amount=5000, sale_id=str(sold.id))
    assert refusal.value.code == "sale.voucher_over_line"


def test_a_voided_sale_pays_no_voucher(haircut, lucia):
    sold = charged_open("sold-0001", ("Bono de 100", 10000, None))
    run("sale.sale.void", {"sale_id": str(sold.id), "reason": "wrong customer"})
    with pytest.raises(Conflict) as refusal:
        grant_for(lucia, haircut, sale_id=str(sold.id))
    assert refusal.value.code == "sale.voucher_sale_voided"


def test_voiding_the_voucher_gives_its_line_back_to_who_sold_it(haircut, lucia):
    # The money is still charged and no voucher lives on it, until a refund says otherwise (SERVICE-F17).
    seller = uuid7()
    grant = voucher_of_100(lucia, haircut, seller=seller)
    assert by_staff()[seller].production_total == 0
    notices = OutboxEvent.objects.filter(name="sale.sale.voucher_line_changed")
    assert notices.count() == 1
    svc("service.grant.void", {"id": str(grant.id), "reason": "wrong customer"})
    row = by_staff()[seller]
    assert (row.voucher_sold_total, row.production_total) == (0, 10000)
    # The screens hear of this one too.
    assert notices.count() == 2
    assert last_event("sale.sale.voucher_line_changed")["line_id"] == str(SaleLine.objects.get(name="Bono de 100").id)
    # The same line can pay the voucher granted in its place.
    line = SaleLine.objects.get(name="Bono de 100")
    grant_for(lucia, haircut, name="El bueno", sale_id=str(line.sale_id))
    assert by_staff()[seller].production_total == 0


def test_voiding_a_voucher_not_linked_to_a_line_tells_sales_nothing(haircut, lucia):
    seller = uuid7()
    charged_open("sold-0001", ("Bono de 100", 10000, seller))
    before = OutboxEvent.objects.filter(name="sale.sale.voucher_line_changed").count()
    svc("service.grant.void", {"id": str(grant_for(lucia, haircut).id), "reason": "wrong customer"})
    assert OutboxEvent.objects.filter(name="sale.sale.voucher_line_changed").count() == before == 0


def test_money_back_on_the_line_of_a_voucher_never_takes_production_below_nothing(haircut, lucia):
    seller = uuid7()
    grant_sale = charged_open("sold-0001", ("Bono de 100", 10000, seller))
    grant_for(lucia, haircut, sale_id=str(grant_sale.id))
    allocation = {"payment_id": str(grant_sale.payments[0].id)}
    refund(grant_sale, allocations=[{**allocation, "amount": 3000}], key="value-refund-0001")
    row = by_staff()[seller]
    assert (row.total_revenue, row.voucher_sold_total, row.production_total) == (7000, 7000, 0)
    refund(grant_sale, allocations=[{**allocation, "amount": 7000}], key="value-refund-0002")
    row = by_staff()[seller]
    assert (row.total_revenue, row.voucher_sold_total, row.production_total) == (0, 0, 0)


def test_money_back_shared_with_another_line_comes_off_each_as_it_always_did(haircut, lucia):
    # 100.00 of the voucher and 25.00 of a cut: 50.00 back share out 40.00 and 10.00: 15.00 of the cut are left.
    seller = uuid7()
    sold = charged_open("sold-0001", ("Bono de 100", 10000, seller), ("Corte", 2500, seller))
    line = next(line for line in sold.lines if line.name == "Bono de 100")
    grant_for(lucia, haircut, sale_id=str(sold.id), sale_line_id=str(line.id))
    refund(sold, allocations=[{"payment_id": str(sold.payments[0].id), "amount": 5000}], key="value-refund-0001")
    row = by_staff()[seller]
    assert (row.total_revenue, row.voucher_sold_total, row.production_total) == (7500, 6000, 1500)


def test_voiding_the_sale_of_a_voucher_takes_it_off_every_figure_of_who_sold_it(haircut, lucia):
    seller, doer = uuid7(), uuid7()
    grant = voucher_of_100(lucia, haircut, seller=seller)
    spend_session(grant, haircut, lucia, "value-0001", staff=doer)
    run("sale.sale.void", {"sale_id": str(SaleLine.objects.get(name="Bono de 100").sale_id), "reason": "wrong"})
    rows = by_staff()
    assert seller not in rows
    # The voucher sold lives on (SERVICE-F27 does not void it): its session stays with who did it.
    assert rows[doer].production_total == 3333


def test_the_employee_who_grants_says_the_sale_with_their_own_permissions(haircut, lucia):
    employee = ctx_for(EMPLOYEE)
    sold = charged_open("sold-0001", ("Bono de 100", 10000, None))
    package = svc("service.package.create", {"name": "Bono", "max_uses": 3, "items": [{"service_id": str(haircut.id)}]})
    grant = run(
        "service.grant.create",
        {"package_id": str(package.id), "customer_id": str(lucia.id), "amount": 10000, "sale_id": str(sold.id)},
        employee,
    )
    assert Grant.objects.get(pk=grant.id).sale_line_id == sold.lines[0].id


def test_who_may_not_charge_may_not_say_what_a_line_paid(haircut, lucia):
    op = get("sale.sale.voucher_sold")
    assert op.permission == "sale.take_payment"
    assert get("sale.sale.voucher_unsold").permission == "sale.take_payment"
    sold = charged_open("sold-0001", ("Bono de 100", 10000, None))
    no_charge = ctx_for(EMPLOYEE)
    no_charge = no_charge.__class__(
        **{**no_charge.__dict__, "permissions": no_charge.permissions - {"sale.take_payment"}}
    )
    with pytest.raises(PermissionDenied):
        op(no_charge, op.input.model_validate({"sale_id": str(sold.id), "amount": 10000}))


def test_a_grant_that_says_its_sale_with_sales_off_is_granted_without_a_line(haircut, lucia, monkeypatch):
    # With Sales off there is no figure to count it in; the voucher is sold all the same. It says no line, so its
    # sessions count nothing. Voiding it asks nothing of Sales either.
    for name in [name for name in registry if name.startswith("sale.")]:
        monkeypatch.delitem(registry, name)
    grant = grant_for(lucia, haircut, sale_id=str(uuid7()))
    row = Grant.objects.get(pk=grant.id)
    assert (row.sale_id is not None, row.sale_line_id) == (True, None)
    svc("service.grant.void", {"id": str(grant.id), "reason": "wrong customer"})
    assert Grant.objects.get(pk=grant.id).voided_at is not None


def test_voiding_a_linked_voucher_with_sales_off_still_voids_and_the_line_stays_out(haircut, lucia, monkeypatch):
    seller = uuid7()
    grant = voucher_of_100(lucia, haircut, seller=seller)
    saved = {name: op for name, op in registry.items() if name.startswith("sale.")}
    for name in saved:
        monkeypatch.delitem(registry, name)
    svc("service.grant.void", {"id": str(grant.id), "reason": "wrong customer"})
    assert Grant.objects.get(pk=grant.id).voided_at is not None
    for name, op in saved.items():
        monkeypatch.setitem(registry, name, op)
    # Nothing counts twice: the line stays out of who sold it until a person sees to it.
    assert by_staff()[seller].production_total == 0
