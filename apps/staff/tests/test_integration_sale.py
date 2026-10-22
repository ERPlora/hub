"""The commission report of Staff (STAFF-F21, step 3) against real sales of Sales: what each professional
sold in a period, refunds taken off (``sale.sale.by_staff``), times their rate, to the cent.

Sales is no requirement of Staff: the report asks Sales by the name of its operation, and a business
without Sales gets ``sales_available: false``. Every sale here is charged by card: a cash charge would
ask Cash register for an open drawer (SALE-F08), which is not what these tests are about.
"""

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid7

import pytest
from django.utils import timezone
from live.context import system_context
from live.errors import PermissionDenied
from live.live_registry import live_registry
from live.operations import get, registry

from apps.staff.models import Member
from apps.staff.schemas import CommissionReportIn

from .conftest import A, ctx_for, make_member, make_role

pytestmark = pytest.mark.django_db

CARD = [{"method": "card"}]
# A Wednesday, 10:00 in Madrid (the business's zone): its week starts on Monday the 17th.
WEDNESDAY = dt.datetime(2026, 8, 19, 8, 0, tzinfo=dt.UTC)


def run(name, data, role="hub_admin", **ctx):
    op = get(name)
    return op(ctx_for(role, **ctx), op.input.model_validate(data))


def report(role="hub_admin", **params):
    return run("staff.commission.report", params, role)


@pytest.fixture
def catalog():
    """Products made by Inventory, prices with tax included (what a line charges)."""
    for name, sku, price in (("Cut", "CUT", 1800), ("Fringe", "FRG", 506), ("Shampoo", "SHP", 121)):
        get("inventory.product.create")(
            system_context(A),
            get("inventory.product.create").input.model_validate(
                {"name": name, "sku": sku, "price": price, "tax_category_key": "product.generic"}
            ),
        )


@pytest.fixture
def frozen_now(monkeypatch):
    """Freeze ``timezone.now`` (and so the business day of a sale and of the report) at an instant."""

    def freeze(instant):
        monkeypatch.setattr(timezone, "now", lambda: instant)

    return freeze


def charge(key, *lines, staff=None):
    """A sale charged by card: ``lines`` as (sku, member or None); ``staff`` serves the whole sale."""
    return run(
        "sale.sale.complete",
        {
            "idempotency_key": key,
            "lines": [
                {"product": sku, **({"staff_id": str(member.id)} if member else {})} for sku, member in lines
            ],
            **({"staff_id": str(staff.id)} if staff else {}),
            "payments": CARD,
        },
    )


def give_back(sale, amount):
    """Money back on the sale's tender, nothing returned (SALE-F31)."""
    return run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "unhappy",
            "allocations": [{"payment_id": str(sale.payments[0].id), "amount": amount}],
        },
    )


def figures(page):
    return [(row.full_name, row.sold, row.commission_rate, row.commission) for row in page.rows]


# What each one sold and earned


def test_each_professional_earns_their_rate_on_what_they_sold_refunds_taken_off(catalog):
    # flow: STAFF-F21 (paso 3: la comisión del día)
    ana = make_member("Ana", commission_rate=Decimal("15"), role=make_role("Stylist"))
    luis = make_member("Luis", commission_rate=Decimal("10"))
    # Ana serves the sale; Luis did the cut line: a line's own professional wins over the sale's.
    first = charge("commission-0001", ("CUT", luis), ("SHP", None), staff=ana)
    charge("commission-0002", ("CUT", None), staff=ana)
    # 10.00 of the second sale's 18.00 go back: they come off Ana, who sold it.
    give_back(charge("commission-0003", ("CUT", None), staff=ana), 1000)

    page = report()

    assert first.lines[0].staff_id == luis.id
    # Ana: 1.21 + 18.00 + (18.00 − 10.00) = 27.21 → 15 % = 4.0815 → 4.08. Luis: 18.00 → 10 % = 1.80.
    assert figures(page) == [
        ("Ana López", 2721, Decimal("15.00"), 408),
        ("Luis López", 1800, Decimal("10.00"), 180),
    ]
    assert page.rows[0].role_name == "Stylist" and page.rows[1].role_name is None
    assert (page.total_sold, page.total_commission) == (4521, 588)
    assert page.sales_available is True
    # Contrasted with another query: what the rows sold is Sales' revenue of the day, refunds taken off.
    assert page.total_sold == run("sale.sale.stats", {}).total_revenue


def test_the_commission_is_rounded_half_up_once_on_what_the_person_sold(catalog):
    bea = make_member("Bea", commission_rate=Decimal("12.5"))
    # Two fringes of 5.06: each would earn 0.6325 → 0.63 (1.26 in all), but she sold 10.12 → 1.265 → 1.27.
    charge("commission-0004", ("FRG", None), staff=bea)
    charge("commission-0005", ("FRG", None), staff=bea)
    # 12.5 % of 10.12 is 126.5 cents: half up gives 127 (half to even and truncating, 126).
    assert figures(report()) == [("Bea López", 1012, Decimal("12.50"), 127)]


def test_who_can_earn_a_commission_is_listed_without_sales_and_who_sold_though_no_longer_active(catalog):
    active = make_member("Ana", commission_rate=Decimal("15"))
    on_leave = make_member("Bea", status=Member.Status.ON_LEAVE)  # a zero rate is listed too
    make_member("Carla", status=Member.Status.INACTIVE, commission_rate=Decimal("10"))
    left = make_member("Dora", commission_rate=Decimal("20"))
    charge("commission-0006", ("CUT", None), staff=left)
    run("staff.member.terminate", {"id": str(left.id)})  # she sold today and left today

    page = report()

    assert [(row.member_id, row.full_name, row.status, row.sold, row.commission) for row in page.rows] == [
        (active.id, "Ana López", "active", 0, 0),
        (on_leave.id, "Bea López", "on_leave", 0, 0),
        (left.id, "Dora López", "terminated", 1800, 360),
    ]
    assert page.total_commission == 360


def test_a_sale_nobody_served_or_served_by_someone_not_on_the_team_counts_for_nobody(catalog):
    make_member("Ana", commission_rate=Decimal("15"))
    charge("commission-0007", ("CUT", None))  # the till's «Me»: no professional on the sale
    charge("commission-0010", ("CUT", None), staff=SimpleNamespace(id=uuid7()))  # an id of no record
    page = report()
    assert [(row.full_name, row.sold) for row in page.rows] == [("Ana López", 0)]
    assert (page.total_sold, page.total_commission) == (0, 0)


# The period


def test_the_period_is_the_business_day_by_default_and_yesterday_week_or_month_count_up_to_today(frozen_now):
    frozen_now(WEDNESDAY)
    assert [(p.date_from, p.date_to) for p in (report(), report(period="today"))] == [
        (dt.date(2026, 8, 19), dt.date(2026, 8, 19)),
    ] * 2
    assert (report(period="yesterday").date_from, report(period="yesterday").date_to) == (
        dt.date(2026, 8, 18),
        dt.date(2026, 8, 18),
    )
    assert (report(period="this_week").date_from, report(period="this_week").date_to) == (
        dt.date(2026, 8, 17),
        dt.date(2026, 8, 19),
    )
    assert (report(period="this_month").date_from, report(period="this_month").date_to) == (
        dt.date(2026, 8, 1),
        dt.date(2026, 8, 19),
    )
    custom = report(period="this_month", date_from="2026-07-01", date_to="2026-07-31")
    assert (custom.date_from, custom.date_to) == (dt.date(2026, 7, 1), dt.date(2026, 7, 31))


def test_each_sale_counts_on_its_business_day(catalog, frozen_now):
    ana = make_member("Ana", commission_rate=Decimal("10"))
    frozen_now(dt.datetime(2026, 8, 17, 21, 30, tzinfo=dt.UTC))  # Monday 23:30 in Madrid
    charge("commission-0008", ("CUT", None), staff=ana)
    # Wednesday 00:30 in Madrid, still Tuesday in UTC: the sale is the business's Wednesday.
    frozen_now(dt.datetime(2026, 8, 18, 22, 30, tzinfo=dt.UTC))
    charge("commission-0009", ("SHP", None), staff=ana)
    frozen_now(WEDNESDAY)

    assert [row.sold for row in report().rows] == [121]
    assert [row.sold for row in report(period="yesterday").rows] == [0]
    assert [row.sold for row in report(period="this_week").rows] == [1921]
    monday = report(date_from="2026-08-17", date_to="2026-08-17")
    assert [(row.sold, row.commission) for row in monday.rows] == [(1800, 180)]


@pytest.mark.parametrize(
    "params, field",
    [
        ({"date_from": "2026-08-19"}, "date_to"),
        ({"date_to": "2026-08-19"}, "date_to"),
        ({"date_from": "2026-08-19", "date_to": "2026-08-18"}, "date_to"),
        ({"date_from": "2024-08-18", "date_to": "2026-08-19"}, "date_to"),
        ({"period": "last_year"}, "period"),
    ],
)
def test_a_custom_period_needs_both_days_in_order_and_at_most_731(params, field):
    with pytest.raises(ValueError) as refused:
        CommissionReportIn.model_validate(params)
    assert [error["loc"][0] for error in refused.value.errors()] == [field]


# Sales off, and who may read it


@pytest.fixture
def sales_off(monkeypatch):
    """A business without Sales: none of its operations is declared, as when the app is not there."""
    for name in [name for name in registry if name.startswith("sale.")]:
        monkeypatch.delitem(registry, name)


def test_without_sales_the_report_says_so_and_lists_nobody(sales_off):
    make_member("Ana", commission_rate=Decimal("15"))
    page = report()
    assert (page.sales_available, page.rows, page.total_sold, page.total_commission) == (False, [], 0, 0)


def test_whoever_sees_the_pay_reads_it_and_an_employee_does_not():
    make_member("Ana", commission_rate=Decimal("15"))
    assert [row.full_name for row in report("hub_manager").rows] == ["Ana López"]
    with pytest.raises(PermissionDenied):
        report("hub_employee")


def test_the_pay_permission_alone_does_not_open_the_sales_figures():
    # The report shows what each one sold: it needs Sales' own permission for its figures too.
    make_member("Ana", commission_rate=Decimal("15"))
    op = get("staff.commission.report")
    with pytest.raises(PermissionDenied):
        op(ctx_for(permissions={"staff.view", "staff.view_compensation"}), op.input.model_validate({}))


# Live


def test_a_sale_charged_voided_or_refunded_re_runs_the_report():
    for event in ("sale.sale.completed", "sale.sale.voided", "sale.sale.refunded"):
        assert "staff.commission.report" in live_registry.affected([event]), event
