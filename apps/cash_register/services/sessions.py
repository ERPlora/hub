"""The cash session (CASH_REGISTER-F03, F09, F10): opened with its day's number, closed with its count or by
itself at the daily cut-off."""

import datetime as dt

from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import atomic, operation
from live.outbox import record_event

from apps.cash_register import events
from apps.cash_register.models import (
    Movement,
    Register,
    Session,
    SessionCounter,
    Settings,
    session_number,
)
from apps.cash_register.queries.auto_close import last_cut_off
from apps.cash_register.queries.lines import sale_lines, stored_line
from apps.cash_register.queries.people import actor
from apps.cash_register.queries.registers import find_register
from apps.cash_register.queries.sessions import require_count, session_row, session_to_close
from apps.cash_register.queries.settings import current_settings
from apps.cash_register.schemas import (
    AutoCloseOut,
    EmptyIn,
    SessionCloseIn,
    SessionOpenIn,
    SessionRow,
)
from base.business import business_zone
from base.queries.people import signed_in_username

SESSION_ALREADY_OPEN = _(
    "There is already an open cash session. Close it before opening another one."
)
OPENING_BALANCE_REQUIRED = _(
    "This business requires an opening float: give the cash the drawer starts with."
)


def _number(day: dt.date) -> int:
    """The next session number of ``day``: its counter raised with ``UPDATE … RETURNING`` (no sequence)."""
    SessionCounter.objects.bulk_create([SessionCounter(day=day)], ignore_conflicts=True)
    counter = SessionCounter.objects.get(day=day)
    counter.last = F("last") + 1
    counter.save(update_fields=["last"])
    return counter.last


def _close(  # noqa: PLR0913
    ctx: OperationContext,
    session: Session,
    *,
    end: dt.datetime,
    counted: int | None,
    notes: str,
    by: str,
    auto: bool,
) -> Session:
    """Close ``session`` (locked) at ``end``: copy its sale lines of ``[opened_at, end)``, freeze the expected
    cash, the counted one and their difference, and say so. Closed by itself, it is closed by no one, whoever's
    opening closes it."""
    copies = [
        Movement(
            session=session,
            type=line.type,
            amount=line.amount,
            method_type=line.method_type,
            method_name=line.method_name,
            sale_id=line.sale_id,
            sale_number=line.sale_number,
            document_type=line.document_type,
            sale_payment_id=line.sale_payment_id,
            refund_payment_id=line.refund_payment_id,
            gift_total=line.gift_total,
            created_at=line.created_at,
            created_by=line.created_by,
        )
        for line in sale_lines(session.opened_at, end)
    ]
    Movement.objects.bulk_create(copies)
    lines = [stored_line(movement) for movement in session.movements.all()]
    expected = session.opening_balance + sum(line.cash for line in lines)
    session.status = Session.Status.CLOSED
    session.closed_at = end
    session.closed_by, session.closed_by_username = by, "" if auto else signed_in_username(ctx)
    session.closing_balance = counted
    session.expected_balance = expected
    session.difference = None if counted is None else counted - expected
    session.closing_notes = notes
    session.auto_closed = auto
    session.save(
        update_fields=[
            "status",
            "closed_at",
            "closed_by", "closed_by_username",
            "closing_balance",
            "expected_balance",
            "difference",
            "closing_notes",
            "auto_closed",
        ]
    )
    record_event(
        ctx,
        events.SESSION_CLOSED,
        {
            "session_id": str(session.id),
            "number": session.number,
            "expected_balance": session.expected_balance,
            "closing_balance": session.closing_balance,
            "difference": session.difference,
            "auto_closed": auto,
        },
    )
    return session


def _close_due(
    ctx: OperationContext, settings: Settings, now: dt.datetime
) -> list[Session]:
    """Close, at the last cut-off, every session still open from before it (the daily auto-close)."""
    if not settings.auto_close_enabled:
        return []
    cut = last_cut_off(now, settings.auto_close_time)
    due = Session.objects.select_for_update().filter(
        status=Session.Status.OPEN, opened_at__lt=cut
    )
    return [
        _close(ctx, session, end=cut, counted=None, notes="", by="", auto=True)
        for session in due
    ]


def _register_to_open(data: SessionOpenIn) -> Register | None:
    """The drawer named (active), or the only active one when none is named and there is just one."""
    if data.register_id is not None or data.register_name is not None:
        return find_register(data.register_id, data.register_name, active=True)
    active = list(Register.objects.filter(is_active=True)[:2])
    return active[0] if len(active) == 1 else None


def _already_open() -> Conflict:
    return Conflict(
        str(SESSION_ALREADY_OPEN), code="cash_register.session_already_open"
    )


@operation(
    "cash_register.session.open",
    kind="command",
    permission="cash_register.add_session",
    input=SessionOpenIn,
    output=SessionRow,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "open the till with a 150 € float",
                "start the bar shift with 200 euros",
            ),
            "es": (
                "abre la caja con 100 € de fondo",
                "empieza el turno de la barra con 200 euros",
            ),
        },
        "description": "Open the cash session (the shift of the drawer) with its opening float in cents and, if the business "
        "has several drawers, the drawer by its name. One session open at a time; the system numbers it "
        "(S-AAMMDD-NNNN). A session forgotten past the daily cut-off is closed by itself first.",
        "risk": "high",
    },
)
def open_session(ctx: OperationContext, data: SessionOpenIn) -> dict:
    settings, now = current_settings(), timezone.now()
    _close_due(ctx, settings, now)
    if Session.objects.filter(status=Session.Status.OPEN).exists():
        raise _already_open()
    if settings.require_opening_balance and not data.opening_balance:
        raise Conflict(
            str(OPENING_BALANCE_REQUIRED),
            code="cash_register.opening_balance_required",
            fields={"opening_balance": str(OPENING_BALANCE_REQUIRED)},
        )
    register = _register_to_open(data)
    day = timezone.localdate(now, business_zone())
    sequence = _number(day)
    try:
        with atomic():
            session = Session.objects.create(
                number=session_number(day, sequence),
                business_day=day,
                sequence=sequence,
                register=register,
                opened_at=now,
                opened_by=actor(ctx), opened_by_username=signed_in_username(ctx),
                opening_balance=data.opening_balance or 0,
                opening_notes=data.opening_notes,
            )
    except IntegrityError:
        raise _already_open() from None
    record_event(
        ctx,
        events.SESSION_OPENED,
        {
            "session_id": str(session.id),
            "number": session.number,
            "opening_balance": session.opening_balance,
            "register_id": str(register.id) if register else None,
            "opened_by": session.opened_by,
        },
    )
    return session_row(ctx, session, settings, now, [])


@operation(
    "cash_register.session.close",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cash_register.close_session",
    input=SessionCloseIn,
    output=SessionRow,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "close the till with 250 € counted",
                "end the till shift, I counted 310 euros",
            ),
            "es": (
                "cierra la caja con 250 € contados",
                "termina el turno de caja, he contado 310 euros",
            ),
        },
        "description": "Close a cash session (the open one unless its number is said) with the cash counted in the drawer, "
        "in cents, and closing notes: the expected cash, the counted one and their difference (negative = short) are "
        "frozen for good. The count is required unless the settings say otherwise. A closed session is never reopened. "
        "Read cash_register.session.closing_summary first with the same count; then, in the same answer where you tell "
        "the person its summary, call this tool naming the session by the number it gave: do not stop at the summary "
        "nor wait for a yes in the chat, its card is where the person confirms.",
        "risk": "high",
        # Its card shows what closing gives, not only the session and the count it sends; a blind count's expected
        # stays hidden from whoever may not see it (BASE-F98).
        "preview": {
            "operation": "cash_register.session.closing_summary",
            "fields": ["number", "register_name", "expected_balance", "difference"],
        },
    },
)
def close_session(ctx: OperationContext, data: SessionCloseIn) -> dict:
    session = session_to_close(ctx, data.session_id, data.session, lock=True)
    settings = current_settings()
    require_count(data.closing_balance, settings)
    now = timezone.now()
    _close(
        ctx,
        session,
        end=now,
        counted=data.closing_balance,
        notes=data.closing_notes,
        by=actor(ctx),
        auto=False,
    )
    return session_row(ctx, session, settings, now)


@operation(
    "cash_register.session.auto_close",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cash_register.close_session",
    input=EmptyIn,
    output=AutoCloseOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "run the till's daily auto-close now",
                "close the forgotten sessions from earlier days",
                "close the till shifts still open past the cut-off hour",
            ),
            "es": (
                "lanza ya el cierre automático de la caja",
                "cierra las sesiones olvidadas de días anteriores",
                "cierra los turnos de caja que siguen abiertos tras la hora de corte",
            ),
        },
        "description": "The daily auto-close (the system runs it every 5 minutes): when it is on, close at the cut-off hour, "
        "without a count, every session still open from before the last cut-off. Nothing is due: nothing happens.",
        "risk": "high",
    },
)
def auto_close(ctx: OperationContext, data: EmptyIn) -> dict:
    settings, now = current_settings(), timezone.now()
    closed = _close_due(ctx, settings, now)
    return {"closed": [session_row(ctx, session, settings, now) for session in closed]}
