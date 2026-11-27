"""The time off of the staff: the list, one request, who is away today and a person's own (STAFF-F08, F17–F20)."""

from babel.dates import format_date
from live.context import OperationContext
from live.errors import NotFound
from live.operations import INTERNAL, operation

from apps.staff.models import TimeOff
from apps.staff.schemas.fields import ByIdIn
from apps.staff.schemas.time_off import (
    MyTimeOffIn,
    TimeOffDetailOut,
    TimeOffNamedOut,
    TimeOffDetailPage,
    TimeOffListIn,
    TimeOffPage,
    TodayIn,
)
from base.business import babel_locale
from base.ordering import list_order_for
from base.text_search import contains_text

from .reads import _page, business_today, own_member
from .time_off_reads import TIME_OFF_NOT_FOUND, _away_on, _name_approvers, _with_approver, live_time_off, load_time_off

TIME_OFF_ORDER = {
    "start_date": ("start_date",),
    "end_date": ("end_date",),
    "member_name": ("member_name",),
    "leave_type": ("leave_type",),
    "status": ("status",),
    "is_full_day": ("is_full_day",),
    "approved_at": ("approved_at",),
    "id": (),
}


@operation(
    "staff.time_off.list",
    kind="query",
    permission="staff.view_time_off",
    input=TimeOffListIn,
    output=TimeOffPage,
    ai={
        "asks": {
            "en": (
                "list all the time off",
                "which vacations are there this month?",
                "Lucía's pending time off",
            ),
            "es": (
                "lista todas las ausencias",
                "vacaciones de este mes",
                "ausencias pendientes de Lucía",
            ),
        },
        "description": "Lists the time-off requests of the staff (without their reason), filtered by "
        "person, status, type or dates."
    },
)
def list_time_off(ctx: OperationContext, params: TimeOffListIn) -> dict:  # noqa: C901
    time_off = live_time_off()
    if params.search:
        time_off = time_off.filter(contains_text(params.search, "member_name"))
    if params.member_id:
        time_off = time_off.filter(member_id=params.member_id)
    if params.status:
        time_off = time_off.filter(status=params.status)
    if params.leave_type:
        time_off = time_off.filter(leave_type=params.leave_type)
    if params.is_full_day is not None:
        time_off = time_off.filter(is_full_day=params.is_full_day)
    if params.approved_by_id:
        time_off = time_off.filter(approved_by_id=params.approved_by_id)
    if params.date_from:
        time_off = time_off.filter(end_date__gte=params.date_from)
    if params.date_to:
        time_off = time_off.filter(start_date__lte=params.date_to)
    for field, lookup in (
        ("start_date_from", "start_date__gte"),
        ("start_date_to", "start_date__lte"),
        ("end_date_from", "end_date__gte"),
        ("end_date_to", "end_date__lte"),
    ):
        value = getattr(params, field)
        if value:
            time_off = time_off.filter(**{lookup: value})
    return _page(time_off.order_by(*list_order_for(params.sort, columns=TIME_OFF_ORDER, nulls_last=True)), params)


@operation(
    "staff.time_off.detail",
    kind="query",
    permission="staff.view_time_off_detail",
    input=ByIdIn,
    output=TimeOffDetailOut,
    ai={
        "asks": {
            "en": (
                "open Pablo's time off and tell me who approved it",
                "what reason and notes does Ana's vacation have?",
                "why is Lucía absent on Monday?",
            ),
            "es": (
                "¿quién aprobó las vacaciones de Pablo?",
                "¿qué motivo y notas tiene la ausencia de Ana?",
                "¿por qué falta Lucía el lunes?",
            ),
        },
        "description": "Returns one time-off request with its reason, notes and who approved it."
    },
)
def time_off_detail(ctx: OperationContext, data: ByIdIn) -> TimeOff:
    time_off = load_time_off(data.id)
    if time_off is None:
        raise NotFound(str(TIME_OFF_NOT_FOUND))
    return time_off


# Not an assistant tool: what names a request on the card of a write (``schemas.time_off.A_TIME_OFF``). The detail holds its
# reason and needs a right an employee withdrawing their own does not have; this says what their list already shows.
@operation(
    "staff.time_off.get",
    kind="query",
    permission="staff.view_time_off",
    input=ByIdIn,
    output=TimeOffNamedOut,
    ai=INTERNAL,
)
def get_time_off(ctx: OperationContext, data: ByIdIn) -> TimeOff:
    time_off = live_time_off().filter(pk=data.id).first()
    if time_off is None:
        raise NotFound(str(TIME_OFF_NOT_FOUND))
    days = _days_of(time_off, ctx.language)
    time_off.label = f"{time_off.member_name} · {time_off.leave_type_label} · {days}"
    return time_off


def _days_of(time_off: TimeOff, language: str) -> str:
    """Its days as the card writes a date: the one day, or the first and the last."""
    locale = babel_locale(language)
    first = format_date(time_off.start_date, "medium", locale=locale)
    if time_off.end_date == time_off.start_date:
        return first
    return f"{first} – {format_date(time_off.end_date, 'medium', locale=locale)}"


@operation(
    "staff.time_off.today",
    kind="query",
    permission="staff.view_time_off",
    input=TodayIn,
    output=TimeOffPage,
    ai={
        "asks": {
            "en": (
                "who is off today?",
                "who is away today on approved leave?",
                "is anyone on vacation today?",
            ),
            "es": (
                "¿quién falta hoy?",
                "¿quién libra hoy?",
                "¿hay alguien de vacaciones hoy?",
            ),
        },
        "description": "Lists the approved time off covering today: who is away today."
    },
)
def away_today(ctx: OperationContext, params: TodayIn) -> dict:
    """Approved time off covering today: whole days first, then by name (STAFF-F20)."""
    time_off = _away_on(business_today()).order_by(
        "-is_full_day", "member__first_name", "member__last_name", "start_time", "id"
    )
    return _page(time_off, params)


@operation(
    "staff.time_off.mine",
    kind="query",
    permission="staff.view_time_off",
    input=MyTimeOffIn,
    output=TimeOffDetailPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "my time-off requests",
                "have they approved my vacation?",
                "what state are my days off in?",
            ),
            "es": (
                "¿cómo están mis ausencias?",
                "estado de mis vacaciones y días libres",
                "¿me han aprobado mis días libres?",
            ),
        },
        "description": "Lists the time-off requests of the current user, with their reason and notes."
    },
)
def my_time_off(ctx: OperationContext, params: MyTimeOffIn) -> dict:
    """The caller's own time off; empty without a linked record (STAFF-F08)."""
    member = own_member(ctx)
    if member is None:
        return {"rows": [], "total": 0, "limit": params.limit, "offset": params.offset}
    page = _page(
        _with_approver(live_time_off().filter(member=member)).order_by(
            "-start_date", "id"
        ),
        params,
    )
    _name_approvers(page["rows"])
    return page
