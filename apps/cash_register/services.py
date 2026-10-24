"""Write operations of the cash register app: one operation = one transaction, with its events in the outbox.

Opening numbers the session with its day's counter (``UPDATE … RETURNING``, in the same transaction: a
refused open never burns a number) and one open session at a time is the database's (a partial unique
index): two opens at once open one. Closing, recording and counting lock the session's row first
(``select_for_update``), so two closes at once close it once and nothing lands in a session being closed.
Closing copies the shift's sale lines into the session: a closed session never moves again. Printing a
session's report puts it in Printing's queue by its operation's name (``printing.job.create``): Printing off
or absent, or no active receipt printer in it, is nothing queued, and the screen prints through the browser.
"""

import datetime as dt
import uuid
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F
from django.db.models.functions import Lower
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.context import OperationContext
from live.errors import AppInactive, Conflict
from live.operations import UnknownOperation, operation
from live.operations import get as operation_named
from live.outbox import record_event

from apps.cash_register import events
from apps.cash_register.models import (
    Count,
    Movement,
    Register,
    Session,
    SessionCounter,
    Settings,
    session_number,
)
from apps.cash_register.queries import (
    actor,
    business_currency,
    count_row,
    count_total,
    currency_decimals,
    current_settings,
    expected_now,
    find_register,
    find_session,
    hides_expected,
    last_cut_off,
    line_row,
    normalized_count,
    register_row,
    require_count,
    sale_lines,
    session_detail,
    session_row,
    session_to_close,
    settings_row,
    stored_line,
)
from apps.cash_register.schemas import (
    AutoCloseOut,
    CountAddIn,
    CountOut,
    EmptyIn,
    MovementAddIn,
    MovementRow,
    RegisterIn,
    RegisterOut,
    RegisterUpdateIn,
    SessionCloseIn,
    SessionGetIn,
    SessionOpenIn,
    SessionPrintOut,
    SessionRow,
    SettingsOut,
    SettingsPatchIn,
)

SESSION_ALREADY_OPEN = _(
    "There is already an open cash session. Close it before opening another one."
)
OPENING_BALANCE_REQUIRED = _(
    "This business requires an opening float: give the cash the drawer starts with."
)
NEGATIVE_BALANCE = _(
    "This cash-out would leave the drawer below zero and a negative balance is not allowed."
)
REGISTER_EXISTS = _("There is already a drawer with that name.")
REPORT_HIDDEN = _(
    "With the blind count on, the report of an open session is printed by whoever may see the expected cash."
)
#: The words of the X and Z reports (their own context: «Cash in» is a total on the paper, «Entradas»).
CLOSED_BY_ITSELF = pgettext_lazy("cash report", "Closed by itself")
COUNTED = pgettext_lazy("cash report", "Counted")
#: The drawer's difference is its over/short, as Toast prints it; the device's paper prints no other
#: difference of its own.
OVER_SHORT = pgettext_lazy("cash report", "Over/short")
#: The lines of the X and Z reports, as the detail shows them: (figure, label, sign on the paper).
REPORT_LINES = (
    ("total_sales", pgettext_lazy("cash report", "Sales"), 1),
    ("cash_sales", pgettext_lazy("cash report", "Cash sales"), 1),
    ("card_sales", pgettext_lazy("cash report", "Card sales"), 1),
    ("other_sales", pgettext_lazy("cash report", "Sales with other payment methods"), 1),
    ("total_refunds", pgettext_lazy("cash report", "Refunds"), -1),
    ("total_cash_in", pgettext_lazy("cash report", "Cash in"), 1),
    ("total_cash_out", pgettext_lazy("cash report", "Cash out"), -1),
    ("total_gifts", pgettext_lazy("cash report", "Comps"), 1),
    ("expected_cash", pgettext_lazy("cash report", "Expected"), 1),
)


# ── Settings ─────────────────────────────────────────────────────────────────────────────────────


def _locked_settings(ctx: OperationContext) -> Settings:
    """The business's settings row, locked; created with the factory values the first time."""
    settings = Settings.objects.select_for_update().first()
    if settings is not None:
        return settings
    try:
        with transaction.atomic():
            return Settings.objects.create(updated_by=actor(ctx))
    except IntegrityError:
        return Settings.objects.select_for_update().get()


@operation(
    "cash_register.settings.update",
    kind="command",
    permission="cash_register.manage_settings",
    input=SettingsPatchIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "Change how the drawer works, field by field: cash register on, opening float required, count "
        "required to close, negative balance allowed, blind count, daily auto-close and its hour («04:00»). What is not "
        "sent is kept.",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsPatchIn) -> dict:
    settings = _locked_settings(ctx)
    sent = data.model_dump(exclude_unset=True, exclude_none=True)
    if "auto_close_time" in sent:
        sent["auto_close_time"] = dt.time.fromisoformat(sent["auto_close_time"])
    changes = {
        field: value
        for field, value in sent.items()
        if getattr(settings, field) != value
    }
    if changes:
        for field, value in changes.items():
            setattr(settings, field, value)
        settings.updated_by = actor(ctx)
        settings.save(update_fields=[*changes, "updated_by", "updated_at"])
        record_event(ctx, events.SETTINGS_UPDATED, {"fields": sorted(changes)})
    return settings_row(settings)


# ── Drawers ──────────────────────────────────────────────────────────────────────────────────────


def _name_taken(name: str, *, but: Register | None = None) -> bool:
    others = Register.objects.annotate(lowered=Lower("name")).filter(
        lowered=name.lower()
    )
    if but is not None:
        others = others.exclude(pk=but.pk)
    return others.exists()


def _refuse_taken_name() -> Conflict:
    return Conflict(
        str(REGISTER_EXISTS),
        code="cash_register.register_exists",
        fields={"name": str(REGISTER_EXISTS)},
    )


@operation(
    "cash_register.register.create",
    kind="command",
    permission="cash_register.manage_settings",
    input=RegisterIn,
    output=RegisterOut,
    expose_api=True,
    ai={
        "description": "Create a drawer by its name (Bar, Terrace), one per physical drawer; it is offered when opening a "
        "session. Two drawers never share a name.",
        "risk": "normal",
    },
)
def create_register(ctx: OperationContext, data: RegisterIn) -> dict:
    if _name_taken(data.name):
        raise _refuse_taken_name()
    try:
        with transaction.atomic():
            register = Register.objects.create(name=data.name, created_by=actor(ctx))
    except IntegrityError:
        raise _refuse_taken_name() from None
    record_event(ctx, events.REGISTER_CREATED, {"id": str(register.id)})
    return register_row(register)


@operation(
    "cash_register.register.update",
    kind="command",
    permission="cash_register.manage_settings",
    input=RegisterUpdateIn,
    output=RegisterOut,
    expose_api=True,
    ai={
        "description": "Rename a drawer, or deactivate it (it is no longer offered when opening) and activate it again. "
        "Name it by its id or its current name. A drawer is never deleted.",
        "risk": "normal",
    },
)
def update_register(ctx: OperationContext, data: RegisterUpdateIn) -> dict:
    register = find_register(data.register_id, data.register_name, lock=True)
    if data.name is not None and _name_taken(data.name, but=register):
        raise _refuse_taken_name()
    if data.name is not None:
        register.name = data.name
    if data.is_active is not None:
        register.is_active = data.is_active
    try:
        with transaction.atomic():
            register.save(update_fields=["name", "is_active", "updated_at"])
    except IntegrityError:
        raise _refuse_taken_name() from None
    record_event(ctx, events.REGISTER_UPDATED, {"id": str(register.id)})
    return register_row(register)


# ── Sessions ─────────────────────────────────────────────────────────────────────────────────────


def _number(day: dt.date) -> int:
    """The next session number of ``day``: its counter raised with ``UPDATE … RETURNING`` (no sequence)."""
    SessionCounter.objects.bulk_create([SessionCounter(day=day)], ignore_conflicts=True)
    counter = SessionCounter.objects.get(day=day)
    counter.last = F("last") + 1
    counter.save(update_fields=["last"])
    return counter.last


def _close(
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
    cash, the counted one and their difference, and say so."""
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
    session.closed_by = by
    session.closing_balance = counted
    session.expected_balance = expected
    session.difference = None if counted is None else counted - expected
    session.closing_notes = notes
    session.auto_closed = auto
    session.save(
        update_fields=[
            "status",
            "closed_at",
            "closed_by",
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
    day = timezone.localdate(now)
    sequence = _number(day)
    try:
        with transaction.atomic():
            session = Session.objects.create(
                number=session_number(day, sequence),
                business_day=day,
                sequence=sequence,
                register=register,
                opened_at=now,
                opened_by=actor(ctx),
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


def _open_for_writing(session_id, number) -> Session:
    """The session named (or the open one), locked, still open and not past its daily cut-off."""
    return session_to_close(session_id, number, lock=True)


@operation(
    "cash_register.session.close",
    kind="command",
    permission="cash_register.close_session",
    input=SessionCloseIn,
    output=SessionRow,
    expose_api=True,
    ai={
        "description": "Close a cash session (the open one unless its number is said) with the cash counted in the drawer, "
        "in cents, and closing notes: the expected cash, the counted one and their difference (negative = short) are "
        "frozen for good. The count is required unless the settings say otherwise. A closed session is never reopened. "
        "Read cash_register.session.closing_summary first with the same count, tell the person its summary, then close "
        "naming the session by the number it gave.",
        "risk": "high",
    },
)
def close_session(ctx: OperationContext, data: SessionCloseIn) -> dict:
    session = _open_for_writing(data.session_id, data.session)
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
    permission="cash_register.close_session",
    input=EmptyIn,
    output=AutoCloseOut,
    expose_api=True,
    ai={
        "description": "The daily auto-close (the system runs it every 5 minutes): when it is on, close at the cut-off hour, "
        "without a count, every session still open from before the last cut-off. Nothing is due: nothing happens.",
        "risk": "high",
    },
)
def auto_close(ctx: OperationContext, data: EmptyIn) -> dict:
    settings, now = current_settings(), timezone.now()
    closed = _close_due(ctx, settings, now)
    return {"closed": [session_row(ctx, session, settings, now) for session in closed]}


# ── Movements and counts ─────────────────────────────────────────────────────────────────────────


@operation(
    "cash_register.movement.add",
    kind="command",
    permission="cash_register.add_movement",
    input=MovementAddIn,
    output=MovementRow,
    expose_api=True,
    ai={
        "description": "Record cash brought into the drawer (type in: change from the safe) or taken out (type out: a "
        "supplier paid, money to the bank) in the open session (or the one whose number is said), with its amount in "
        "cents, always positive, and why. Cash by default; card, transfer or other do not count for the drawer. A "
        "cash-out that leaves the drawer below zero is refused unless the settings allow it.",
        "risk": "high",
    },
)
def add_movement(ctx: OperationContext, data: MovementAddIn) -> dict:
    session = _open_for_writing(data.session_id, data.session)
    settings = current_settings()
    if (
        data.type == Movement.Type.OUT
        and data.method_type == "cash"
        and not settings.allow_negative_balance
        and expected_now(session) - data.amount < 0
    ):
        raise Conflict(
            str(NEGATIVE_BALANCE), code="cash_register.negative_balance_not_allowed"
        )
    movement = Movement.objects.create(
        session=session,
        type=data.type,
        amount=data.amount,
        method_type=data.method_type,
        description=data.description,
        created_by=actor(ctx),
    )
    record_event(
        ctx,
        events.MOVEMENT_ADDED,
        {
            "session_id": str(session.id),
            "movement_id": str(movement.id),
            "type": movement.type,
            "amount": movement.amount,
            "method_type": movement.method_type,
        },
    )
    return line_row(stored_line(movement))


@operation(
    "cash_register.count.add",
    kind="command",
    permission="cash_register.add_count",
    input=CountAddIn,
    output=CountOut,
    expose_api=True,
    ai={
        "description": "Record a count of the drawer of the open session (or the one whose number is said): opening (check "
        'the float) or closing (end of the shift). Give the notes and coins as {bills: {"50": 2}, coins: {"0.50": 3}} '
        "with face values in major units of the business's currency (the server adds them up), or the total in cents, "
        "which prevails. It closes nothing by itself.",
        "risk": "high",
    },
)
def add_count(ctx: OperationContext, data: CountAddIn) -> dict:
    session = _open_for_writing(data.session_id, data.session)
    currency = business_currency()
    sent = data.denominations.model_dump() if data.denominations is not None else {}
    denominations = normalized_count(sent, currency) if sent else {}
    total = (
        data.total if data.total is not None else count_total(denominations, currency)
    )
    count = Count.objects.create(
        session=session,
        type=data.type,
        denominations=denominations,
        total=total,
        notes=data.notes,
        counted_by=actor(ctx),
    )
    record_event(
        ctx,
        events.COUNT_ADDED,
        {
            "session_id": str(session.id),
            "count_id": str(count.id),
            "type": count.type,
            "total": count.total,
        },
    )
    return count_row(count)


# ── The X and Z reports (CASH_REGISTER-F16) ──────────────────────────────────────────────────────


def _units(cents: int, scale: Decimal, sign: int = 1) -> float:
    """Minor units as the paper's money (12.50): Printing takes amounts in units."""
    return float(Decimal(sign * cents) / scale)


def _report(ctx: OperationContext, session: Session, report: str) -> dict:
    """The ``cash_session_report`` the receipt printer paints: the session, who, the float and the expected
    cash at the close (or now), and the detail's figures as its lines, in the language of who prints."""
    scale = Decimal(10) ** currency_decimals(business_currency())
    with translation.override(ctx.language):
        figures = session_detail(ctx, session)["summary"]
        lines = [
            {"label": str(label), "amount": _units(figures[key], scale, sign)}
            for key, label, sign in REPORT_LINES
            if figures[key] is not None and (key != "other_sales" or figures[key])
        ]
        if report == "z" and session.closing_balance is not None:
            lines.append({"label": str(COUNTED), "amount": _units(session.closing_balance, scale)})
        if report == "z" and session.difference is not None:
            lines.append({"label": str(OVER_SHORT), "amount": _units(session.difference, scale)})
        if report == "x":
            cashier = session.opened_by
        else:
            cashier = str(CLOSED_BY_ITSELF) if session.auto_closed else session.closed_by
    return {
        "receipt_id": f"{session.number} ({report.upper()})",
        "cashier": cashier,
        "opening_balance": _units(session.opening_balance, scale),
        "closing_balance": _units(figures["expected_cash"], scale),
        "transactions": lines,
    }


@operation(
    "cash_register.session.print",
    kind="command",
    permission="cash_register.view_session",
    input=SessionGetIn,
    output=SessionPrintOut,
    expose_api=True,
    ai={
        "description": "Print the report of a cash session (by its id or number) on the receipt printer: the partial "
        "report (X) while it is open, the closing (Z) once closed, with its float, sales by payment method, refunds, "
        "cash in and out, comps, expected, counted and difference. Without Printing on or an active receipt printer, "
        "nothing is queued. A blind "
        "count keeps an open session's report from whoever may not see the expected cash.",
        "risk": "normal",
    },
)
def print_session(ctx: OperationContext, data: SessionGetIn) -> dict:
    session = find_session(data.session_id, data.session)
    if hides_expected(ctx, session, current_settings()):
        raise Conflict(str(REPORT_HIDDEN), code="cash_register.report_hidden")
    report = "x" if session.is_open else "z"
    nothing = {"report": report, "queued": False, "job_id": None, "printer": None}
    try:
        summary = operation_named("printing.job.summary")
        create = operation_named("printing.job.create")
        printing = summary(ctx, summary.input.model_validate({}))
    except (UnknownOperation, AppInactive):
        return nothing
    # Without an active receipt printer the paper would wait in the queue for ever: the browser prints it.
    if not any(row.usage == "receipt" and row.printers for row in printing.usages):
        return nothing
    request = {
        "job_key": f"cash-session-{session.id}-{report}-{uuid.uuid7()}",
        "document_type": "cash_session_report",
        "document": _report(ctx, session, report),
        "usage": "receipt",
        "currency": business_currency(),
        "source_app": "cash_register",
        "source_ref": session.number,
    }
    try:
        queued = create(ctx, create.input.model_validate(request))
    except AppInactive:
        return nothing
    job = queued.job
    if job is None:
        return nothing
    return {"report": report, "queued": True, "job_id": job.id, "printer": job.printer_name}
