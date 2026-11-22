"""The cash sessions: finding one, its row and its report, the one that may still be closed, and their reads."""

import datetime as dt
from uuid import UUID

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.cash_register.models import Session, Settings
from apps.cash_register.queries.auto_close import auto_close_due_at
from apps.cash_register.queries.figures import figures
from apps.cash_register.queries.lines import Line, session_lines
from apps.cash_register.queries.settings import current_settings
from apps.cash_register.queries.unassigned import (
    open_session_now,
    unassigned_totals,
    unassigned_window,
)
from apps.cash_register.schemas import (
    CurrentOut,
    EmptyIn,
    SessionGetIn,
    SessionListIn,
    SessionOut,
    SessionPage,
)
from base.business import business_zone
from base.ordering import list_order

VIEW_EXPECTED = "cash_register.view_expected_totals"

SESSION_NOT_FOUND = _("That cash session does not exist.")
NO_OPEN_SESSION = _("There is no open cash session: open one first.")
SESSION_NOT_OPEN = _(
    "That cash session is closed: a closed session takes no new movements."
)
CLOSING_BALANCE_REQUIRED = _("Give the counted cash to close the session.")
AUTO_CLOSE_DUE = _(
    "Session %(number)s was due to close by itself at %(time)s: open a new session (this one closes then)."
)


def hides_expected(ctx: OperationContext, session: Session, settings: Settings) -> bool:
    """A blind count hides an open session's expected cash from whoever may not see it."""
    return (
        session.is_open and settings.require_blind_count and not ctx.has(VIEW_EXPECTED)
    )


def session_row(
    ctx: OperationContext,
    session: Session,
    settings: Settings,
    now: dt.datetime,
    lines: list[Line] | None = None,
) -> dict:
    hidden = hides_expected(ctx, session, settings)
    cut = auto_close_due_at(session, settings, now)
    if session.is_open:
        if lines is None:
            lines = session_lines(session, until=cut)
        expected = None if hidden else session.opening_balance + sum(line.cash for line in lines)
    else:
        expected = session.expected_balance
    register = session.register
    return {
        "id": session.id,
        "number": session.number,
        "business_day": session.business_day,
        "status": session.status,
        "register_id": session.register_id,
        "register_name": register.name if register else "",
        "opened_at": session.opened_at,
        "opened_by": session.opened_by,
        "opening_balance": session.opening_balance,
        "closed_at": session.closed_at,
        "closed_by": session.closed_by,
        "closing_balance": session.closing_balance,
        "expected_balance": expected,
        "difference": session.difference,
        "auto_closed": session.auto_closed,
        "expected_hidden": hidden,
        "auto_close_due": cut is not None,
    }


def lines_of(session: Session, settings: Settings, now: dt.datetime) -> list[Line]:
    """The lines a session reads now: an open one past its daily cut-off stops at the cut."""
    return session_lines(session, until=auto_close_due_at(session, settings, now))


def session_detail(ctx: OperationContext, session: Session) -> dict:
    settings, now = current_settings(), timezone.now()
    lines = lines_of(session, settings, now)
    hidden = hides_expected(ctx, session, settings)
    return {
        **session_row(ctx, session, settings, now, lines),
        "opening_notes": session.opening_notes,
        "closing_notes": session.closing_notes,
        "summary": figures(session, lines, hidden=hidden),
    }


def find_session(
    session_id: UUID | None, number: str | None, *, lock: bool = False
) -> Session:
    sessions = (
        Session.objects.select_for_update()
        if lock
        else Session.objects.select_related("register")
    )
    session = (
        sessions.filter(pk=session_id).first()
        if session_id is not None
        else sessions.filter(number=(number or "").strip()).first()
    )
    if session is None:
        raise NotFound(str(SESSION_NOT_FOUND), code="cash_register.session_not_found")
    return session


def named_or_open(
    session_id: UUID | None, number: str | None, *, lock: bool = False
) -> Session:
    """The session named, or the open one when none is named (``Conflict`` if there is none)."""
    if session_id is not None or number is not None:
        return find_session(session_id, number, lock=lock)
    sessions = Session.objects.select_for_update() if lock else Session.objects.all()
    session = sessions.filter(status=Session.Status.OPEN).first()
    if session is None:
        raise Conflict(str(NO_OPEN_SESSION), code="cash_register.no_open_session")
    return session


def session_to_close(
    session_id: UUID | None, number: str | None, *, lock: bool = False
) -> Session:
    """The session named (or the open one), still open and not past its daily cut-off: what may be closed or
    written to. A forgotten session is closed as of its cut (by the next opening or the scheduled task), so
    nothing written after the cut may land in it. ``lock``: its row locked, for a write."""
    session = named_or_open(session_id, number, lock=lock)
    if not session.is_open:
        raise Conflict(str(SESSION_NOT_OPEN), code="cash_register.session_not_open")
    cut = auto_close_due_at(session, current_settings(), timezone.now())
    if cut is not None:
        raise Conflict(
            str(AUTO_CLOSE_DUE)
            % {"number": session.number, "time": f"{timezone.localtime(cut, business_zone()):%H:%M}"},
            code="cash_register.session_auto_close_due",
        )
    return session


def require_count(counted: int | None, settings: Settings) -> None:
    """The count is required to close (the setting): no count, no close — from the screen, the assistant or the API."""
    if counted is None and settings.require_closing_balance:
        raise Conflict(
            str(CLOSING_BALANCE_REQUIRED),
            code="cash_register.closing_balance_required",
            fields={"closing_balance": str(CLOSING_BALANCE_REQUIRED)},
        )


_SESSION_SORT = {"number": ("business_day", "sequence")}


@operation(
    "cash_register.session.list",
    kind="query",
    permission="cash_register.view_session",
    input=SessionListIn,
    output=SessionPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "show me this week's cash sessions",
                "which till closes came out short?",
            ),
            "es": (
                "enséñame las sesiones de caja de esta semana",
                "¿qué cierres de caja tuvieron diferencia?",
            ),
        },
        "description": "List the cash sessions, newest first: search by number; filter by status (open, closed), drawer, "
        "business days and amounts in cents (opening float, expected, counted, difference; negative = short). The open "
        "session carries its live expected cash unless a blind count hides it from the reader. Closed sessions sorted "
        "by closed_at desc, limit 8, are the recent discrepancies."
    },
)
def list_sessions(ctx: OperationContext, params: SessionListIn) -> dict:
    sessions = Session.objects.select_related("register")
    if params.search:
        sessions = sessions.filter(number__icontains=params.search.strip())
    exact = {
        "number": params.number,
        "status": params.status,
        "register_id": params.register_id,
        "business_day__gte": params.opened_from,
        "business_day__lte": params.opened_to,
        "opening_balance__gte": params.opening_min,
        "opening_balance__lte": params.opening_max,
        "expected_balance__gte": params.expected_min,
        "expected_balance__lte": params.expected_max,
        "closing_balance__gte": params.counted_min,
        "closing_balance__lte": params.counted_max,
        "difference__gte": params.difference_min,
        "difference__lte": params.difference_max,
    }
    sessions = sessions.filter(
        **{key: value for key, value in exact.items() if value is not None}
    )
    columns = _SESSION_SORT.get(params.sort, (params.sort,))
    page = sessions.order_by(*list_order(*columns, descending=params.dir == "desc", nulls_last=True))[
        params.offset : params.offset + params.limit
    ]
    settings, now = current_settings(), timezone.now()
    return {
        "rows": [session_row(ctx, session, settings, now) for session in page],
        "total": sessions.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


@operation(
    "cash_register.session.current",
    kind="query",
    permission="cash_register.view_session",
    input=EmptyIn,
    output=CurrentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "is the till open right now?",
                "how much cash should be in the drawer now?",
                "which cash shift is open?",
            ),
            "es": (
                "¿está abierta la caja?",
                "¿cuánto dinero tendría que haber ahora en el cajón?",
                "¿qué turno de caja está abierto?",
            ),
        },
        "description": "Is the drawer open? The open session (with its live expected cash, unless a blind count hides it), "
        "whether the cash register is on (Sales should then charge cash only with a session open), whether the open "
        "session is past its daily cut-off (it then takes nothing more), and how many sale lines fell in no shift and "
        "their cash. A blind count hides the expected from whoever may not see it."
    },
)
def current_session(ctx: OperationContext, params: EmptyIn) -> dict:
    settings, now = current_settings(), timezone.now()
    session = open_session_now()
    count, cash = 0, 0
    # With the cash register off, nothing is out of a shift: there are no shifts to be in.
    if settings.enable_cash_register:
        window = unassigned_window(session, settings, now)
        if window is not None:
            count, cash = unassigned_totals(window)
    return {
        "required": settings.enable_cash_register,
        "session": session_row(ctx, session, settings, now) if session else None,
        "auto_close_at": auto_close_due_at(session, settings, now) if session else None,
        "unassigned_count": count,
        "unassigned_cash": cash,
    }


@operation(
    "cash_register.session.get",
    kind="query",
    permission="cash_register.view_session",
    input=SessionGetIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "show me the report of session S-261014-0001",
                "how did Monday's till shift go?",
                "what difference did last night's session give and with what float did it start?",
            ),
            "es": (
                "enséñame el informe de la sesión S-261014-0001",
                "¿cómo fue el turno de caja del lunes?",
                "¿qué diferencia dio la sesión de anoche y con cuánto fondo empezó?",
            ),
        },
        "description": "One cash session by its id or number (S-261014-0001) with its report: who opened and closed it, its "
        "drawer, opening float, sales by payment method, refunds and voids, cash in and out, comps at cost, expected, "
        "counted, difference and notes, in cents. A blind count hides the expected of an open session from the reader."
    },
)
def get_session(ctx: OperationContext, params: SessionGetIn) -> dict:
    return session_detail(ctx, find_session(params.session_id, params.session))
