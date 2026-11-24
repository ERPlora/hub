"""The commission sheet and the report (STAFF-F21), and whose a commission line is: a person's own, and the whole
team's with «See pay».

Declared here and not in ``ownership.py``: the team reads every staff record (the directory, the agenda, the clock), so
the record is nobody's to hide; only the pay on it is a person's own. ``tests/test_guardrails_sensitive.py`` holds the
pay of the lines to this declaration."""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from django.db.models import F, Q, Value
from django.db.models.functions import Concat
from live.context import OperationContext, system_context
from live.errors import AppInactive
from live.operations import UnknownOperation, get, operation

from apps.staff.models import Member
from apps.staff.schemas.commissions import CommissionPage, CommissionReportIn, CommissionReportOut, CommissionSummaryIn
from base.queries.ownership import Owned

from .reads import _page, business_today, live_members

COMMISSION_LINES = Owned(
    Member,
    all_permission="staff.view_compensation",
    mine=lambda person: Q(pk__in=person.records),
)


@operation(
    "staff.commission.summary",
    kind="query",
    permission="staff.view_compensation",
    input=CommissionSummaryIn,
    output=CommissionPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what commission rate does each professional have?",
                "the team's commission sheet with each one's linked user",
                "what percentage does Lucía get as commission?",
            ),
            "es": (
                "¿con qué comisión trabaja cada profesional?",
                "hoja de comisiones del equipo con el usuario vinculado de cada uno",
                "¿qué porcentaje se lleva Lucía de comisión?",
            ),
        },
        "description": "Returns each staff member who can earn a commission (active or on leave) with "
        "their record id, the user id their record hangs from and their commission rate. What each one "
        "earned in a period is staff.commission.report."
    },
)
def commission_summary(ctx: OperationContext, params: CommissionSummaryIn) -> dict:
    members = live_members().exclude(status=Member.Status.INACTIVE)
    if params.search:
        members = members.annotate(
            search_name=Concat("first_name", Value(" "), "last_name")
        ).filter(search_name__icontains=params.search)
    return _page(members.order_by("first_name", "last_name", "id"), params)


#: Sales' figure per professional (SALE-F28), asked by name: Sales is no requirement of Staff.
SALES_BY_STAFF = "sale.sale.by_staff"
#: Who can earn a commission: listed in the report even without sales (STAFF-F21).
EARNING = (Member.Status.ACTIVE, Member.Status.ON_LEAVE)


@operation(
    "staff.commission.report",
    kind="query",
    permission="staff.view",
    input=CommissionReportIn,
    output=CommissionReportOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how much commission did each stylist earn this week?",
                "work out the team's commissions for yesterday",
                "sales and commission per professional this month",
            ),
            "es": (
                "¿cuánto ha ganado de comisión cada estilista esta semana?",
                "calcula las comisiones del equipo de ayer",
                "comisiones ganadas por cada profesional en lo que va de mes",
            ),
        },
        "description": "The commission each professional earned in a period of business days: today by default, "
        "yesterday, this week, this month or two days of your own. Per person: what they sold (refunds and the "
        "vouchers they sold taken off, the value of the voucher sessions they did added), their rate and their "
        "commission, in cents, and the totals. Lists everyone who can earn a commission, also without sales, and "
        "whoever sold in the period though no longer active; whoever lacks the team's pay or the business's totals "
        "gets only their own line. Without Sales in the business, sales_available is false and nobody is listed."
    },
)
def commission_report(ctx: OperationContext, params: CommissionReportIn) -> dict:
    """STAFF-F21 step 3: what each professional produced in the period (``sale.sale.by_staff``, refunds and vouchers
    sold taken off, voucher sessions added) times their rate, rounded half up once per person, on the lines the caller
    counts (``COMMISSION_LINES``). A sale with nobody, or with an id of no record, counts for nobody."""
    first, last = report_period(params, business_today())
    sold = _sold_by_staff(ctx, first, last)
    if sold is None:
        nothing = {"rows": [], "total_sold": 0, "total_commission": 0}
        return {"date_from": first, "date_to": last, "sales_available": False, **nothing}
    members = (
        COMMISSION_LINES.counted(ctx).filter(Q(status__in=EARNING) | Q(pk__in=list(sold)))
        .annotate(role_name=F("role__name"))
        .order_by("first_name", "last_name", "id")
    )
    rows = [
        {
            "member_id": member.id,
            "full_name": member.full_name,
            "role_name": member.role_name,
            "status": member.status,
            "commission_rate": member.commission_rate,
            "sold": sold.get(member.id, 0),
            "commission": commission_cents(sold.get(member.id, 0), member.commission_rate),
        }
        for member in members
    ]
    return {
        "date_from": first,
        "date_to": last,
        "sales_available": True,
        "rows": rows,
        "total_sold": sum(row["sold"] for row in rows),
        "total_commission": sum(row["commission"] for row in rows),
    }


def report_period(params: CommissionReportIn, today: dt.date) -> tuple[dt.date, dt.date]:
    """The report's first and last business day: the days given, or the period counted up to ``today``
    (a week starts on Monday)."""
    if params.date_from is not None and params.date_to is not None:
        return params.date_from, params.date_to
    if params.period == "yesterday":
        yesterday = today - dt.timedelta(days=1)
        return yesterday, yesterday
    if params.period == "this_week":
        return today - dt.timedelta(days=today.weekday()), today
    if params.period == "this_month":
        return today.replace(day=1), today
    return today, today


def commission_cents(sold: int, rate: Decimal) -> int:
    """``sold`` x ``rate`` / 100 in whole cents, half up (126.5 → 127)."""
    return int((Decimal(sold) * rate / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _sold_by_staff(ctx: OperationContext, first: dt.date, last: dt.date) -> dict[UUID, int] | None:
    """What each record produced from ``first`` to ``last``, refunds and vouchers sold taken off and voucher sessions
    added. Asked to Sales as the platform: a line is all its person did, also on a sale they may not open, and
    ``COMMISSION_LINES`` says who reads which line. ``None`` when the business has no Sales (absent or off)."""
    try:
        op = get(SALES_BY_STAFF)
        page = op(system_context(ctx.scope), op.input.model_validate({"date_from": first, "date_to": last}))
    except (UnknownOperation, AppInactive):
        return None
    return {row.staff_id: row.production_total for row in page.rows}
