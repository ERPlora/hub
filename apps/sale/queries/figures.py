"""The sales figures: a period's totals, today, the last seven days and by staff member."""

import datetime as dt
from fractions import Fraction
from itertools import groupby
from operator import attrgetter
from uuid import UUID

from django.db.models import Count, Exists, F, Func, JSONField, OuterRef, Sum
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Coalesce
from live.context import OperationContext
from live.operations import AI, operation

from apps.sale import pricing
from apps.sale.models import Refund, RefundLine, Sale, SaleLine, VoucherSession
from apps.sale.schemas.fields import EmptyIn
from apps.sale.schemas.figures import ByStaffOut, LastDaysOut, PeriodIn, StatsOut, TodayOut
from apps.tax.queries import business_tax_kind, business_today
from apps.tax.schemas import TAX_KIND_NAMES

#: A voided sale is no revenue; one refunded (in part or in full) is, minus what went back.
COUNTED = [Sale.Status.COMPLETED, Sale.Status.REFUNDED]


def _period(sales, period: PeriodIn):
    if period.date_from:
        sales = sales.filter(business_day__gte=period.date_from)
    if period.date_to:
        sales = sales.filter(business_day__lte=period.date_to)
    return sales


def declared_tax_kind(sales) -> str | None:
    """The tax ``sales`` were declared with (the ``tax_type`` of their breakdown rows), what their tax figure
    is named by (SALE-F28): the one family a territory declares (VAT, IGIC, IPSI) when they all share it;
    ``None`` for a mix — a change of territory in the period — or a tax of no territory (the equivalence
    surcharge, another country's). Without any row, the business territory's, what it would declare now."""
    elements = Func(F("tax_breakdown"), function="jsonb_array_elements", output_field=JSONField())
    declared = (
        sales.order_by()
        .annotate(family=KeyTextTransform("tax_type", elements))
        .values_list("family", flat=True)
        .distinct()
    )
    families = set(declared[:2])
    if not families:
        return business_tax_kind()
    if len(families) > 1:
        return None
    family = families.pop()
    return family if family in TAX_KIND_NAMES else None


@operation(
    "sale.sale.stats",
    kind="query",
    permission="sale.view_reports",
    input=PeriodIn,
    output=StatsOut,
    ai=AI(
        description="How the business is doing in a period of business days (a week, a month, a quarter; inclusive; "
        "empty = all): tickets, revenue (refunds taken off), average ticket, taxable base, tax, discounts, refunds and "
        "voided sales, in cents; and the tax the sales were declared with (VAT, IGIC, IPSI; empty when they mix "
        "taxes).",
        asks={
            "en": (
                "how are we doing this month?",
                "what's the average ticket this week?",
                "what VAT did we charge last quarter?",
            ),
            "es": (
                "¿cómo vamos este mes?",
                "¿cuál es el ticket medio de la semana?",
                "¿cuánto IVA hemos cobrado este trimestre?",
            ),
        },
    ),
)
def stats(ctx: OperationContext, params: PeriodIn) -> dict:
    sales = _period(Sale.objects.all(), params)
    zero = 0
    charged = sales.filter(status__in=COUNTED)
    counted = charged.aggregate(
        count=Count("id"),
        gross=Coalesce(Sum("total"), zero),
        refunded=Coalesce(Sum("refunded_total"), zero),
        net=Coalesce(Sum("subtotal"), zero),
        tax=Coalesce(Sum("tax_total"), zero),
        discounts=Coalesce(Sum("discount_amount"), zero),
    )
    revenue = counted["gross"] - counted["refunded"]
    count = counted["count"]
    return {
        "count": count,
        "total_revenue": revenue,
        "avg_ticket": pricing.half_up(Fraction(revenue, count)) if count else 0,
        "net_total": counted["net"],
        "tax_total": counted["tax"],
        "discount_total": counted["discounts"],
        "refunded_total": counted["refunded"],
        "voided_count": sales.filter(status=Sale.Status.VOIDED).count(),
        "tax_kind": declared_tax_kind(charged),
    }


def _revenue_by_day(first: dt.date, last: dt.date) -> dict[dt.date, int]:
    rows = (
        Sale.objects.filter(
            status__in=COUNTED, business_day__gte=first, business_day__lte=last
        )
        .values("business_day")
        .annotate(total=Sum(F("total") - F("refunded_total")))
    )
    return {row["business_day"]: row["total"] for row in rows}


@operation(
    "sale.sale.today",
    kind="query",
    permission="sale.view_reports",
    input=EmptyIn,
    output=TodayOut,
    ai=AI(
        description="What was sold today (business day) in cents, refunds taken off, and how many tickets.",
        asks={
            "en": (
                "what have I sold today?",
                "how much did we take today?",
                "how many tickets so far today?",
            ),
            "es": (
                "¿cuánto llevo hoy?",
                "¿qué vendí hoy?",
                "¿cuánto hemos hecho hoy?",
                "¿cuántos tickets van hoy?",
            ),
        },
    ),
)
def today(ctx: OperationContext, params: EmptyIn) -> dict:
    day = business_today()
    sales = Sale.objects.filter(status__in=COUNTED, business_day=day)
    return {
        "day": day,
        "total": _revenue_by_day(day, day).get(day, 0),
        "tickets": sales.count(),
    }


@operation(
    "sale.sale.last_7_days",
    kind="query",
    permission="sale.view_reports",
    input=EmptyIn,
    output=LastDaysOut,
    ai=AI(
        description="What was sold each of the last seven business days, today included, oldest first, 0 on a day without sales.",
        asks={
            "en": (
                "how did the last seven days go?",
                "show me sales day by day this past week",
            ),
            "es": (
                "¿cómo han ido los últimos siete días?",
                "¿cuánto hicimos cada día esta semana?",
            ),
        },
    ),
)
def last_7_days(ctx: OperationContext, params: EmptyIn) -> dict:
    last = business_today()
    first = last - dt.timedelta(days=6)
    totals = _revenue_by_day(first, last)
    days = [first + dt.timedelta(days=offset) for offset in range(7)]
    return {"rows": [{"day": day, "total": totals.get(day, 0)} for day in days]}


@operation(
    "sale.sale.by_staff",
    kind="query",
    permission="sale.view_reports",
    input=PeriodIn,
    output=ByStaffOut,
    expose_api=True,
    ai=AI(
        description="What each professional sold in a period of business days: their lines (a line's own professional wins "
        "over the sale's), the sales they served, gross, base and tax in cents, what refunds gave back on their lines "
        "and the revenue left; what of it paid for vouchers they sold; what the voucher sessions they did are worth (no "
        "money of the period: the voucher was paid when it was sold); and their production, the revenue without the "
        "vouchers sold plus the sessions, which is what a commission is on. For the per-professional close.",
        asks={
            "en": (
                "how much did each waiter sell this month?",
                "what did Laura bring in this week?",
                "work out the stylists' commissions",
            ),
            "es": (
                "¿cuánto ha facturado cada peluquera este mes?",
                "¿cuánto vendió Laura esta semana?",
                "¿qué comisión le toca a cada uno?",
            ),
        },
    ),
)
def by_staff(ctx: OperationContext, params: PeriodIn) -> dict:
    lines = SaleLine.objects.filter(sale__status__in=COUNTED)
    if params.date_from:
        lines = lines.filter(sale__business_day__gte=params.date_from)
    if params.date_to:
        lines = lines.filter(sale__business_day__lte=params.date_to)
    rows = (
        lines.annotate(served_by=Coalesce("staff_id", "sale__staff_id"))
        .filter(served_by__isnull=False)
        .values("served_by")
        .annotate(
            sales_count=Count("sale", distinct=True),
            gross=Sum("line_total"),
            net=Sum("net_amount"),
            voucher_sold=Sum("voucher_sold_amount"),
            # A session that came back (SALE-F32) is no longer theirs; a voided sale is not counted at all.
            sessions=Sum(
                "voucher_value",
                filter=~Exists(RefundLine.objects.filter(sale_line=OuterRef("pk"))),
                default=0,
            ),
        )
    )
    refunded, voucher_sold_back = _refunded_by_staff(params)
    # The sessions spent outside the till (SERVICE-F21) are on no line: they count apart, each once.
    off_till = dict(
        _period(VoucherSession.objects.order_by(), params)
        .values("staff_id")
        .annotate(worth=Sum("value"))
        .values_list("staff_id", "worth")
    )
    totals = []
    for row in rows:
        given_back = refunded.get(row["served_by"], 0)
        revenue = row["gross"] - given_back
        voucher_sold = row["voucher_sold"] - voucher_sold_back.get(row["served_by"], 0)
        sessions = row["sessions"] + off_till.pop(row["served_by"], 0)
        totals.append(
            {
                "staff_id": row["served_by"],
                "sales_count": row["sales_count"],
                "gross_total": row["gross"],
                "net_total": row["net"],
                "tax_total": row["gross"] - row["net"],
                "refunded_total": given_back,
                "total_revenue": revenue,
                "voucher_sold_total": voucher_sold,
                "voucher_total": sessions,
                "production_total": revenue - voucher_sold + sessions,
            }
        )
    for staff_id, sessions in off_till.items():
        totals.append({"staff_id": staff_id, **NO_MONEY, "voucher_total": sessions, "production_total": sessions})
    totals.sort(key=lambda total: (-total["production_total"], total["staff_id"]))
    return {"rows": totals}


#: The money figures of a professional who only did sessions outside the till: no line of the period is hers.
NO_MONEY = {
    "sales_count": 0,
    "gross_total": 0,
    "net_total": 0,
    "tax_total": 0,
    "refunded_total": 0,
    "total_revenue": 0,
    "voucher_sold_total": 0,
}


def _refunded_by_staff(params: PeriodIn) -> tuple[dict[UUID, int], dict[UUID, int]]:
    """What the refunds of the period's sales gave back on each professional's lines (SALE-F31), in cents, and how much
    of what those lines paid for vouchers went with it: a line never pays for more than it has left.

    The refunds of a sale are taken in the order they were made, against what each line has left to give
    back (what it charged minus what earlier refunds already took off it). A refund's money goes first to
    the lines it returned, by what the units that came back were worth (never more than a line has left);
    the rest (all of it for money only, a comp or a voucher's session) goes to the sale's lines by what
    each has left. No line gives back more than it charged, so no professional's revenue falls below 0.
    Each refund is shared out whole, to the cent (``pricing.allocate``): with the lines no professional
    served, the rows square with the period's revenue, which takes refunds off on the day of their sale
    too (``sale.sale.stats``)."""
    sales = _period(Sale.objects.filter(status__in=COUNTED), params)
    refunds = (
        Refund.objects.filter(total__gt=0, sale__in=sales)
        .select_related("sale")
        .prefetch_related("sale__lines", "lines")
        .order_by("sale_id", "created_at", "id")
    )
    given: dict[UUID, int] = {}
    voucher_sold_back: dict[UUID, int] = {}
    for _sale_id, of_sale in groupby(refunds, key=attrgetter("sale_id")):
        of_sale = list(of_sale)
        sale = of_sale[0].sale
        lines = list(sale.lines.all())
        left = [line.line_total for line in lines]
        for refund in of_sale:
            returned = {back.sale_line_id: back.quantity for back in refund.lines.all()}
            worth = [
                min(
                    have,
                    pricing.half_up(
                        Fraction(line.line_total) * Fraction(returned[line.id]) / Fraction(line.quantity)
                    ),
                )
                if line.id in returned
                else 0
                for line, have in zip(lines, left, strict=True)
            ]
            on_returned = min(refund.total, sum(worth))
            left = _take_off(left, pricing.allocate(on_returned, worth))
            left = _take_off(left, pricing.allocate(refund.total - on_returned, left))
        for line, have in zip(lines, left, strict=True):
            served_by = line.staff_id or sale.staff_id
            if served_by is not None:
                given[served_by] = given.get(served_by, 0) + line.line_total - have
                voucher_sold_back[served_by] = voucher_sold_back.get(served_by, 0) + max(
                    line.voucher_sold_amount - have, 0
                )
    return given, voucher_sold_back


def _take_off(left: list[int], shares: list[int]) -> list[int]:
    """What each line has left to give back once ``shares`` came off it."""
    return [have - share for have, share in zip(left, shares, strict=True)]
