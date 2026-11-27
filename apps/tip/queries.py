"""Read operations of the tips app (``READ ONLY``): its settings, the tips, the team's report and one's own tips, which can
be followed live (live.py); and the finders services/ reuses: the settings row, a tip by its id or its sale's number, and
a tip as a row."""

import datetime as dt
from uuid import UUID

from django.db.models import Count, Q, QuerySet, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.sale.models import PaymentMethod
from apps.sale.schemas.fields import EmptyIn
from apps.staff.models import Member
from apps.tip.models import Settings, Tip
from apps.tip.schemas import (
    MineOut,
    ReportIn,
    ReportOut,
    SettingsOut,
    SuggestionIn,
    SuggestionOut,
    TipListIn,
    TipOut,
    TipPage,
    TipRefIn,
)
from base.business import business_zone
from base.operations import answer_if_on, call
from base.text_search import contains_text


TIP_NOT_FOUND = _("That tip no longer exists.")
SEVERAL_TIPS = _("The sale %(number)s has several tips: say which one by its id.")
MEMBER_NOT_LINKED = _("Your user is not linked to any staff record: ask a manager to link it in Staff.")

#: A payment method's suggestions from the factory: 3 %, 5 % and 10 % (what is usual in Spain, the WORKBOOK says).
FACTORY_SUGGESTIONS = [{"percent": value, "amount": None} for value in (3, 5, 10)]
#: Staff's answer to «whose record is the caller's?»: what an employee's own tips are.
CURRENT_MEMBER = "staff.member.current"
#: Time clock's working days, asked by name: Time clock is no requirement of Tips.
SHIFTS = "attendance.record.list"
#: How many working days each read of Time clock brings (its page's top).
SHIFTS_PAGE = 100


def current_settings() -> Settings:
    """The business's row, or an unsaved one with the factory values."""
    return Settings.objects.first() or Settings()


def settings_row(settings: Settings) -> dict:
    methods = PaymentMethod.objects.filter(is_active=True).order_by("sort_order", "name", "id")
    return {
        "enabled": settings.enabled,
        "allow_custom": settings.allow_custom,
        "preselected": settings.preselected,
        "methods": [
            {
                "method_id": method.id,
                "method_name": method.display_name,
                "method_type": method.type,
                "suggestions": settings.suggestions.get(str(method.id), FACTORY_SUGGESTIONS),
            }
            for method in methods
        ],
    }


@operation(
    "tip.settings.get",
    kind="query",
    permission="tip.view_tip",
    input=EmptyIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": ("show me the tip settings", "which tip suggestions does the card payment offer?"),
            "es": ("enséñame los ajustes de las propinas", "¿qué propinas sugiere el cobro con tarjeta?"),
        },
        "description": "The tip settings: whether a tip is asked for at the charge (off from the factory), which of the "
        "three suggestions comes chosen (0: no tip), whether another amount is allowed, and each active payment "
        "method's three suggestions, each a percentage of the check's total before discounts or an amount in cents.",
    },
)
def get_settings(ctx: OperationContext, params: EmptyIn) -> dict:
    return settings_row(current_settings())


def _tip_of(suggestion: dict, total: int) -> dict:
    """``suggestion`` as the tip it comes to on ``total``: a percentage rounded to the money's unit, half up."""
    percent = suggestion["percent"]
    amount = (total * percent + 50) // 100 if percent is not None else suggestion["amount"]
    return {"percent": percent, "amount": amount}


@operation(
    "tip.suggestion.get",
    kind="query",
    permission="tip.add_tip",
    input=SuggestionIn,
    output=SuggestionOut,
    expose_api=True,
    ai={
        "asks": {
            "en": ("what tips would a 40 € card payment suggest?", "how much is each suggested tip on a 25 € bill in cash?"),
            "es": ("¿qué propinas sugiere un cobro de 40 € con tarjeta?", "¿cuánto sale cada propina sugerida en una cuenta de 25 € en efectivo?"),
        },
        "description": "The tips the charge proposes for a payment method and the check's total before discounts, in "
        "cents: its three suggestions, each with the tip it comes to (a percentage rounded half up), which one comes "
        "chosen (0: no tip) and whether another amount is allowed. With tips off, none.",
    },
)
def get_suggestions(ctx: OperationContext, params: SuggestionIn) -> dict:
    settings = current_settings()
    suggestions = settings.suggestions.get(str(params.method_id), FACTORY_SUGGESTIONS) if settings.enabled else []
    return {
        "enabled": settings.enabled,
        "allow_custom": settings.allow_custom,
        "preselected": settings.preselected,
        "suggestions": [_tip_of(suggestion, params.total) for suggestion in suggestions],
    }


def tips() -> QuerySet[Tip]:
    return Tip.objects.select_related("sale", "member")


def tip_row(tip: Tip) -> dict:
    return {
        "id": tip.id,
        "sale_id": tip.sale_id,
        "sale_number": tip.sale.number if tip.sale else "",
        "pool": tip.pool,
        "member_id": tip.member_id,
        "member_name": tip.member.full_name if tip.member else "",
        "method_id": tip.method_id,
        "method_name": tip.method_name,
        "method_type": tip.method_type,
        "amount": tip.amount,
        "status": tip.status,
        "created_at": tip.created_at,
        "created_by": tip.created_by,
        "adjusted_at": tip.adjusted_at,
        "adjusted_by": tip.adjusted_by,
        "adjust_reason": tip.adjust_reason,
        "voided_at": tip.voided_at,
        "voided_by": tip.voided_by,
        "void_reason": tip.void_reason,
    }


def find_tip(ref: TipRefIn, *, lock: bool = False) -> Tip:
    """The tip ``ref`` names: by its id; else, by its sale's number, the one active tip of that sale (409
    ``tip.tip_ambiguous`` with several) or, with none active, its newest one, which says it no longer changes."""
    found = Tip.objects.select_for_update(of=("self",)) if lock else Tip.objects.all()
    if ref.id is not None:
        rows = list(found.filter(pk=ref.id)[:1])
    else:
        of_sale = found.filter(sale__number=ref.sale).order_by("-created_at", "id")
        rows = list(of_sale.filter(status=Tip.Status.ACTIVE)[:2]) or list(of_sale[:1])
    if not rows:
        raise NotFound(str(TIP_NOT_FOUND), code="tip.tip_not_found")
    if len(rows) > 1:
        raise Conflict(str(SEVERAL_TIPS) % {"number": ref.sale}, code="tip.tip_ambiguous")
    return tips().get(pk=rows[0].pk)


@operation(
    "tip.tip.get",
    kind="query",
    permission="tip.view_tip",
    input=TipRefIn,
    output=TipOut,
    expose_api=True,
    ai={
        "asks": {
            "en": ("show me the tip of sale 20261114-0007", "who got the tip of sale 20261114-0009?"),
            "es": ("enséñame la propina de la venta 20261114-0007", "¿para quién fue la propina de la 20261114-0009?"),
        },
        "description": "One tip, by its id or its sale's number (the active one of that sale): who it belongs to, its "
        "payment method, its amount in cents, whether it is active or voided, and who adjusted or voided it and why. "
        "An employee reads only their own.",
    },
)
def get_tip(ctx: OperationContext, params: TipRefIn) -> dict:
    tip = find_tip(params)
    if not ctx.has("tip.manage") and (tip.member_id is None or tip.member_id != own_member_id(ctx)):
        raise NotFound(str(TIP_NOT_FOUND), code="tip.tip_not_found")
    return tip_row(tip)


def own_member_id(ctx: OperationContext) -> UUID | None:
    """The caller's own record of the team, asked of Staff; ``None`` without one."""
    current = call(ctx, CURRENT_MEMBER, {})
    return current.member.id if current.member else None


def _day_start(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, dt.time.min, tzinfo=business_zone())


def _filtered(params: TipListIn) -> QuerySet[Tip]:
    rows = tips()
    if params.search:
        rows = rows.filter(contains_text(params.search, "sale__number", "member__first_name", "member__last_name"))
    for field in ("member_id", "method_type", "status"):
        if getattr(params, field) is not None:
            rows = rows.filter(**{field: getattr(params, field)})
    if params.date_from is not None:
        rows = rows.filter(created_at__gte=_day_start(params.date_from))
    if params.date_to is not None:
        rows = rows.filter(created_at__lt=_day_start(params.date_to + dt.timedelta(days=1)))
    return rows


@operation(
    "tip.tip.list",
    kind="query",
    permission="tip.view_tip",
    input=TipListIn,
    output=TipPage,
    expose_api=True,
    ai={
        "asks": {
            "en": ("what tips were left today?", "show me Bea's tips by card this week"),
            "es": ("¿qué propinas han dejado hoy?", "enséñame las propinas con tarjeta de Bea de esta semana"),
        },
        "description": "Lists the tips, newest first, a page at a time: each with its sale's number (none: to the pool), "
        "who it belongs to, its payment method, its amount in cents and whether it is active or voided, with who "
        "adjusted or voided it and why. Searches by a piece of the sale's number or of the person's name and filters by "
        "person, payment type, status and business days. An employee sees only their own.",
    },
)
def list_tips(ctx: OperationContext, params: TipListIn) -> dict:
    rows = _filtered(params)
    if not ctx.has("tip.manage"):
        own = own_member_id(ctx)
        rows = rows.filter(member_id=own) if own is not None else rows.none()
    rows = rows.order_by("-created_at", "id")
    return {
        "rows": [tip_row(tip) for tip in rows[params.offset : params.offset + params.limit]],
        "total": rows.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


def _figures() -> dict:
    """What the report says of some tips: by card, in cash and any other way, in all and how many."""
    other = ~Q(method_type__in=(PaymentMethod.Type.CARD, PaymentMethod.Type.CASH))
    return {
        "card": Sum("amount", filter=Q(method_type=PaymentMethod.Type.CARD), default=0),
        "cash": Sum("amount", filter=Q(method_type=PaymentMethod.Type.CASH), default=0),
        "other": Sum("amount", filter=other, default=0),
        "total": Sum("amount", default=0),
        "count": Count("id"),
    }


def _active(first: dt.date, last: dt.date) -> QuerySet[Tip]:
    """The active tips recorded from the business day ``first`` to ``last``, both included."""
    return Tip.objects.filter(
        status=Tip.Status.ACTIVE,
        created_at__gte=_day_start(first),
        created_at__lt=_day_start(last + dt.timedelta(days=1)),
    )


def _business_today() -> dt.date:
    return timezone.localdate(timezone=business_zone())


def _no_one(**more) -> dict:
    return {"member_id": None, "member_name": "", "shift_id": None, "clock_in_at": None, "clock_out_at": None, **more}


def _by_person(rows: QuerySet[Tip]) -> list[dict]:
    lines = list(rows.order_by().values("member_id").annotate(**_figures()))
    members = Member.objects.in_bulk([line["member_id"] for line in lines if line["member_id"]])
    named = [
        _no_one(**line, member_name=members[line["member_id"]].full_name) for line in lines if line["member_id"]
    ]
    unassigned = [_no_one(**line) for line in lines if not line["member_id"]]
    return sorted(named, key=lambda line: (line["member_name"].casefold(), str(line["member_id"]))) + unassigned


def _shifts(ctx: OperationContext, first: dt.date, last: dt.date) -> list | None:
    """Time clock's working days that ran in the period, as the caller may read them; ``None`` with Time clock absent,
    off or not theirs to read. A working day belongs to the day it was clocked in on, so those of the evening before
    are asked for too: one still running after midnight keeps its tips."""
    since, found = _day_start(first), []
    while True:
        asked = {"date_from": first - dt.timedelta(days=1), "date_to": last, "sort": "clock_in_at"}
        page = answer_if_on(ctx, SHIFTS, {**asked, "limit": SHIFTS_PAGE, "offset": len(found)})
        if page is None:
            return None
        found += page.rows
        if not page.rows or len(found) >= page.total:
            return [shift for shift in found if shift.clock_out_at is None or shift.clock_out_at > since]


def _count(line: dict, tip: Tip) -> None:
    kind = tip.method_type if tip.method_type in (PaymentMethod.Type.CARD, PaymentMethod.Type.CASH) else "other"
    line[kind] += tip.amount
    line["total"] += tip.amount
    line["count"] += 1


def _by_shift(shifts: list, rows: QuerySet[Tip]) -> list[dict]:
    """A line per working day with the tips of its person recorded while it ran (an open one, up to now), and one line
    with the tips recorded outside every working day, when there are any."""
    now = timezone.now()
    zero = {"card": 0, "cash": 0, "other": 0, "total": 0, "count": 0}
    lines = [
        _no_one(**zero, member_id=shift.member_id, member_name=shift.member_name, shift_id=shift.id,
                clock_in_at=shift.clock_in_at, clock_out_at=shift.clock_out_at)
        for shift in shifts
    ]
    outside = _no_one(**zero)
    for tip in rows.order_by("created_at", "id").only("member_id", "created_at", "method_type", "amount"):
        ran = (
            line for line in lines
            if line["member_id"] == tip.member_id and line["clock_in_at"] <= tip.created_at < (line["clock_out_at"] or now)
        )
        _count(next(ran, outside), tip)
    return lines + ([outside] if outside["count"] else [])


@operation(
    "tip.report.get",
    kind="query",
    permission="tip.manage",
    input=ReportIn,
    output=ReportOut,
    expose_api=True,
    ai={
        "asks": {
            "en": ("how much did each waiter get in tips this week?", "show me today's tips by shift"),
            "es": ("¿cuánto ha sacado de propinas cada camarero esta semana?", "enséñame las propinas de hoy por turno"),
        },
        "description": "The team's active tips of a period of business days (today when none is said), by card, in "
        "cash and any other way, in cents, with how many: a line per person (the unassigned and the pool's last) or, by "
        "shift, a line per working day clocked in Time clock with the tips of its person recorded while it ran and one "
        "line with those recorded outside every working day; and the period's totals. Without Time clock on, by shift "
        "gives no lines and shifts_available is false.",
    },
)
def get_report(ctx: OperationContext, params: ReportIn) -> dict:
    last = params.date_to or _business_today()
    first = params.date_from or last
    rows = _active(first, last)
    lines = _by_person(rows) if params.by == "person" else _shift_lines(ctx, first, last, rows)
    return {
        "by": params.by,
        "date_from": first,
        "date_to": last,
        "shifts_available": lines is not None,
        "rows": lines or [],
        "totals": rows.aggregate(**_figures()),
    }


def _shift_lines(ctx: OperationContext, first: dt.date, last: dt.date, rows: QuerySet[Tip]) -> list[dict] | None:
    shifts = _shifts(ctx, first, last)
    return None if shifts is None else _by_shift(shifts, rows)


@operation(
    "tip.report.mine",
    kind="query",
    permission="tip.view_tip",
    input=EmptyIn,
    output=MineOut,
    expose_api=True,
    ai={
        "asks": {
            "en": ("how much have I made in tips today?", "show me my tips of this week"),
            "es": ("¿cuánto llevo hoy de propinas?", "enséñame mis propinas de esta semana"),
        },
        "description": "The caller's own active tips, those of their record of the team: today's and this week's (from "
        "Monday), by card, in cash and any other way, in cents, with how many. Refused when the caller's user has no "
        "record of the team.",
    },
)
def my_tips(ctx: OperationContext, params: EmptyIn) -> dict:
    current = call(ctx, CURRENT_MEMBER, {}).member
    if current is None:
        raise Conflict(str(MEMBER_NOT_LINKED), code="tip.member_not_linked")
    today = _business_today()
    week_from = today - dt.timedelta(days=today.weekday())
    own = _active(week_from, today).filter(member_id=current.id)
    return {
        "member_name": current.full_name,
        "today": today,
        "week_from": week_from,
        "day": own.filter(created_at__gte=_day_start(today)).aggregate(**_figures()),
        "week": own.aggregate(**_figures()),
    }
