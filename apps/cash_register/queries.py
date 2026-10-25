"""Read operations of the cash register app (``READ ONLY``) and the helpers the writes share with them.

The sale lines of a shift are **read from sale** (its requirement: ``Sale``, ``SalePayment``,
``RefundPayment``) at the moment of looking, by their time: a charge belongs to the shift open when it
was charged, a void to the shift open when it was voided, a refund to the shift open when it was given.
A closed session reads only its own copies (``Movement``), made when it closed, so it never moves again.
What fell in no session (with the drawer closed, after a forgotten shift's cut-off, or confirmed while a
shift was closing) is the «unassigned» lines. The close's summary (``session.closing_summary``) reads the shift review
of other apps by their operations' names (Sales' open checks, Kitchen's board, Printing's queue), as the person.
"""

import datetime as dt
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from uuid import UUID

from babel.numbers import get_currency_precision
from django.db.models import Count as CountOf
from django.db.models import Exists, F, OuterRef, Q, Sum
from django.db.models.functions import Coalesce, Lower
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, system_context
from live.errors import AppInactive, Conflict, InvalidPayload, NotFound, OperationError
from live.operations import UnknownOperation, operation
from live.operations import get as operation_named

from apps.cash_register.models import Count, Movement, Register, Session, Settings
from apps.cash_register.schemas import (
    ClosingSummaryIn,
    ClosingSummaryOut,
    CountListIn,
    CountPage,
    CurrencyOut,
    CurrentOut,
    EmptyIn,
    MovementListIn,
    MovementPage,
    RegisterListIn,
    RegisterPage,
    SessionGetIn,
    SessionListIn,
    SessionOut,
    SessionPage,
    SettingsOut,
)
from apps.sale.models import RefundPayment, Sale, SalePayment

VIEW_EXPECTED = "cash_register.view_expected_totals"
CASH = "cash"

SESSION_NOT_FOUND = _("That cash session does not exist.")
NO_OPEN_SESSION = _("There is no open cash session: open one first.")
SESSION_NOT_OPEN = _(
    "That cash session is closed: a closed session takes no new movements."
)
CLOSING_BALANCE_REQUIRED = _("Give the counted cash to close the session.")
AUTO_CLOSE_DUE = _(
    "Session %(number)s was due to close by itself at %(time)s: open a new session (this one closes then)."
)
REGISTER_NOT_FOUND = _("That drawer is not available.")
UNKNOWN_DENOMINATION = _("%(value)s is not a note or coin of %(currency)s.")
NO_DENOMINATIONS = _(
    "There is no table of notes and coins for %(currency)s: count the drawer and give its total."
)

#: The notes and coins of the till count, per currency, largest first (face value in major units): the
#: eighteen of the product (cash_register#111, #113). Only what circulates today; a currency that is not
#: here has no breakdown and its count is a total.
DENOMINATIONS: dict[str, dict[str, list[str]]] = {
    "EUR": {
        "bills": ["500", "200", "100", "50", "20", "10", "5"],
        "coins": ["2", "1", "0.50", "0.20", "0.10", "0.05", "0.02", "0.01"],
    },
    "USD": {
        "bills": ["100", "50", "20", "10", "5", "2", "1"],
        "coins": ["0.50", "0.25", "0.10", "0.05", "0.01"],
    },
    "GBP": {
        "bills": ["50", "20", "10", "5"],
        "coins": ["2", "1", "0.50", "0.20", "0.10", "0.05", "0.02", "0.01"],
    },
    "CHF": {
        "bills": ["1000", "200", "100", "50", "20", "10"],
        "coins": ["5", "2", "1", "0.50", "0.20", "0.10", "0.05"],
    },
    "PLN": {
        "bills": ["500", "200", "100", "50", "20", "10"],
        "coins": ["5", "2", "1", "0.50", "0.20", "0.10", "0.05", "0.02", "0.01"],
    },
    "RON": {
        "bills": ["500", "200", "100", "50", "20", "10", "5", "1"],
        "coins": ["0.50", "0.10", "0.05", "0.01"],
    },
    "MXN": {
        "bills": ["1000", "500", "200", "100", "50", "20"],
        "coins": ["10", "5", "2", "1", "0.50"],
    },
    "JPY": {
        "bills": ["10000", "5000", "2000", "1000"],
        "coins": ["500", "100", "50", "10", "5", "1"],
    },
    "KWD": {
        "bills": ["20", "10", "5", "1", "0.5", "0.25"],
        "coins": ["0.1", "0.05", "0.02", "0.01", "0.005"],
    },
    "SEK": {
        "bills": ["1000", "500", "200", "100", "50", "20"],
        "coins": ["10", "5", "2", "1"],
    },
    "NOK": {
        "bills": ["1000", "500", "200", "100", "50"],
        "coins": ["20", "10", "5", "1"],
    },
    "DKK": {
        "bills": ["1000", "500", "200", "100", "50"],
        "coins": ["20", "10", "5", "2", "1", "0.50"],
    },
    "BRL": {
        "bills": ["200", "100", "50", "20", "10", "5", "2"],
        "coins": ["1", "0.50", "0.25", "0.10", "0.05"],
    },
    "CZK": {
        "bills": ["5000", "2000", "1000", "500", "200", "100"],
        "coins": ["50", "20", "10", "5", "2", "1"],
    },
    "HUF": {
        "bills": ["20000", "10000", "5000", "2000", "1000", "500"],
        "coins": ["200", "100", "50", "20", "10", "5"],
    },
    "COP": {
        "bills": ["100000", "50000", "20000", "10000", "5000", "2000"],
        "coins": ["1000", "500", "200", "100", "50"],
    },
    "CLP": {
        "bills": ["20000", "10000", "5000", "2000", "1000"],
        "coins": ["500", "100", "50", "10"],
    },
    "PEN": {
        "bills": ["200", "100", "50", "20", "10"],
        "coins": ["5", "2", "1", "0.50", "0.20", "0.10"],
    },
}


def actor(ctx: OperationContext) -> str:
    """Who acts, as a person reads it: a user's name (or e-mail, or username); the system's own label."""
    who = ctx.actor
    if who is None:
        return ""
    if hasattr(who, "get_username"):
        label = who.get_full_name() or getattr(who, "email", "") or who.get_username()
    else:
        label = str(who)
    return label[:128]


# ── Money ────────────────────────────────────────────────────────────────────────────────────────


#: What tells the business's currency: its country's, from this hub's registry, never asking erplora.com (APP-BASE-6).
BUSINESS = "base.business.get"


def business_currency(ctx: OperationContext) -> str:
    """The currency of ``ctx``'s business (ISO 4217), as ``base.business.get`` reads it. Read as the platform: an API
    key holds only the permission of the operation it opened, and every person of the hub may see it anyway."""
    business = operation_named(BUSINESS)
    return business(system_context(ctx.scope), business.input()).currency


def currency_decimals(currency: str) -> int:
    """The decimals of ``currency`` (ISO 4217) as CLDR knows them: 2 in EUR, 0 in JPY, 3 in KWD."""
    return get_currency_precision(currency)


def _face(value: str) -> Decimal | None:
    try:
        face = Decimal(str(value))
    except InvalidOperation:
        return None
    return face if face.is_finite() and face > 0 else None


def normalized_count(denominations: dict, currency: str) -> dict[str, dict[str, int]]:
    """The notes and coins counted, keyed as the currency's table writes them, without empty boxes.

    A face value that is not one of the currency's (or a currency without a table) is a 422.
    """
    table = DENOMINATIONS.get(currency)
    out: dict[str, dict[str, int]] = {}
    for kind in ("bills", "coins"):
        known = {_face(face): face for face in (table or {}).get(kind, [])}
        for face, pieces in (denominations.get(kind) or {}).items():
            key = known.get(_face(face))
            if table is None:
                raise InvalidPayload(
                    str(NO_DENOMINATIONS) % {"currency": currency},
                    fields={
                        "denominations": str(NO_DENOMINATIONS) % {"currency": currency}
                    },
                )
            if key is None:
                message = str(UNKNOWN_DENOMINATION) % {
                    "value": face,
                    "currency": currency,
                }
                raise InvalidPayload(message, fields={"denominations": message})
            if pieces:
                out.setdefault(kind, {})[key] = pieces
    return out


def count_total(denominations: dict, currency: str) -> int:
    """The total of a count in whole minor units: each face value scaled once with the currency's decimals."""
    scale = Decimal(10) ** currency_decimals(currency)
    counted = normalized_count(denominations, currency)
    return sum(
        int(Decimal(face) * scale) * pieces
        for kind in counted.values()
        for face, pieces in kind.items()
    )


# ── Settings ─────────────────────────────────────────────────────────────────────────────────────

SETTINGS_FIELDS = [
    "enable_cash_register",
    "require_opening_balance",
    "require_closing_balance",
    "allow_negative_balance",
    "require_blind_count",
    "auto_close_enabled",
]


def current_settings() -> Settings:
    """The business's row, or an unsaved one with the factory values."""
    return Settings.objects.first() or Settings()


def settings_row(settings: Settings) -> dict:
    row = {field: getattr(settings, field) for field in SETTINGS_FIELDS}
    row["auto_close_time"] = f"{settings.auto_close_time:%H:%M}"
    row["updated_at"] = None if settings._state.adding else settings.updated_at
    return row


@operation(
    "cash_register.settings.get",
    kind="query",
    permission="cash_register.view_session",
    input=EmptyIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "Read how the drawer works: cash register on, opening float required, count required to close, "
        "negative balance allowed, blind count, and the daily auto-close with its hour (the factory values until saved)."
    },
)
def get_settings(ctx: OperationContext, params: EmptyIn) -> dict:
    return settings_row(current_settings())


# ── Drawers ──────────────────────────────────────────────────────────────────────────────────────


def register_row(register: Register) -> dict:
    return {"id": register.id, "name": register.name, "is_active": register.is_active}


def find_register(
    register_id: UUID | None,
    name: str | None,
    *,
    lock: bool = False,
    active: bool = False,
) -> Register:
    registers = Register.objects.select_for_update() if lock else Register.objects.all()
    if active:
        registers = registers.filter(is_active=True)
    register = (
        registers.filter(pk=register_id).first()
        if register_id is not None
        else registers.annotate(lowered=Lower("name"))
        .filter(lowered=(name or "").strip().lower())
        .first()
    )
    if register is None:
        raise NotFound(str(REGISTER_NOT_FOUND), code="cash_register.register_not_found")
    return register


@operation(
    "cash_register.register.list",
    kind="query",
    permission="cash_register.view_session",
    input=RegisterListIn,
    output=RegisterPage,
    expose_api=True,
    ai={
        "description": "List the drawers by name: search by name, only active or inactive ones."
    },
)
def list_registers(ctx: OperationContext, params: RegisterListIn) -> dict:
    registers = Register.objects.all()
    if params.search:
        registers = registers.filter(name__icontains=params.search.strip())
    if params.is_active is not None:
        registers = registers.filter(is_active=params.is_active)
    registers = registers.order_by(Lower("name"), "id")
    page = registers[params.offset : params.offset + params.limit]
    return {
        "rows": [register_row(register) for register in page],
        "total": registers.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


# ── The lines of a shift ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Line:
    """A line of a shift: a movement written by hand, or a charge, void or refund of sale."""

    key: str
    session_id: UUID | None
    type: str
    amount: int
    method_type: str
    method_name: str
    created_at: dt.datetime
    created_by: str
    description: str = ""
    sale_id: UUID | None = None
    sale_number: str = ""
    document_type: str = ""
    gift_total: int = 0
    sale_payment_id: UUID | None = None
    refund_payment_id: UUID | None = None

    @property
    def signed_amount(self) -> int:
        return -self.amount if self.type in Movement.OUTFLOWS else self.amount

    @property
    def cash(self) -> int:
        """What the line puts in (or takes out of) the drawer."""
        return self.signed_amount if self.method_type == CASH else 0


def movement_key(movement: Movement) -> str:
    """The stable key of a stored line: a copy keeps the key it had while it was read from sale."""
    if movement.type in (Movement.Type.SALE, Movement.Type.VOID):
        if movement.sale_payment_id is None:
            return f"gift-{movement.sale_id}"
        return f"{movement.type}-{movement.sale_payment_id}"
    if movement.type == Movement.Type.REFUND:
        return f"refund-{movement.refund_payment_id}"
    return str(movement.id)


def stored_line(movement: Movement) -> Line:
    return Line(
        key=movement_key(movement),
        session_id=movement.session_id,
        type=movement.type,
        amount=movement.amount,
        method_type=movement.method_type,
        method_name=movement.method_name,
        created_at=movement.created_at,
        created_by=movement.created_by,
        description=movement.description,
        sale_id=movement.sale_id,
        sale_number=movement.sale_number,
        document_type=movement.document_type,
        gift_total=movement.gift_total,
        sale_payment_id=movement.sale_payment_id,
        refund_payment_id=movement.refund_payment_id,
    )


def _between(field: str, start: dt.datetime, end: dt.datetime | None) -> Q:
    window = Q(**{f"{field}__gte": start})
    return window & Q(**{f"{field}__lt": end}) if end is not None else window


def sale_lines(start: dt.datetime, end: dt.datetime | None = None) -> list[Line]:
    """The lines sale wrote in ``[start, end)`` and no session copied yet: every tender of a charge (and a
    sale of comps only, once), every tender of a void, every leg of a refund."""
    lines: list[Line] = []
    charged = Sale.objects.filter(_between("created_at", start, end)).prefetch_related(
        "payments"
    )
    for sale in charged:
        payments = list(sale.payments.all())
        common = {
            "session_id": None,
            "created_at": sale.created_at,
            "created_by": sale.created_by,
            "sale_id": sale.id,
            "sale_number": sale.number,
            "document_type": sale.document_type,
        }
        if not payments and sale.gift_total:
            lines.append(
                Line(
                    key=f"gift-{sale.id}",
                    type="sale",
                    amount=0,
                    method_type="other",
                    method_name="",
                    gift_total=sale.gift_total,
                    **common,
                )
            )
        for position, payment in enumerate(payments):
            lines.append(
                Line(
                    key=f"sale-{payment.id}",
                    type="sale",
                    amount=payment.amount,
                    method_type=payment.method_type,
                    method_name=payment.method_name,
                    gift_total=sale.gift_total if position == 0 else 0,
                    sale_payment_id=payment.id,
                    **common,
                )
            )
    voided = Sale.objects.filter(_between("voided_at", start, end)).prefetch_related(
        "payments"
    )
    for sale in voided:
        for payment in sale.payments.all():
            lines.append(
                Line(
                    key=f"void-{payment.id}",
                    session_id=None,
                    type="void",
                    amount=payment.amount,
                    method_type=payment.method_type,
                    method_name=payment.method_name,
                    created_at=sale.voided_at,
                    created_by=sale.voided_by,
                    sale_id=sale.id,
                    sale_number=sale.number,
                    document_type=sale.document_type,
                    sale_payment_id=payment.id,
                )
            )
    refunded = RefundPayment.objects.filter(
        _between("refund__created_at", start, end)
    ).select_related("refund__sale")
    for leg in refunded:
        lines.append(
            Line(
                key=f"refund-{leg.id}",
                session_id=None,
                type="refund",
                amount=leg.amount,
                method_type=leg.method_type,
                method_name=leg.method_name,
                created_at=leg.refund.created_at,
                created_by=leg.refund.created_by,
                sale_id=leg.refund.sale_id,
                sale_number=leg.refund.sale.number,
                document_type=leg.refund.sale.document_type,
                refund_payment_id=leg.id,
            )
        )
    return [line for line in lines if line.key not in _copied(lines)]


def _copied(lines: list[Line]) -> set[str]:
    """The keys of ``lines`` some session already copied, looked up by their sources (unique indexes)."""
    payments = [line.sale_payment_id for line in lines if line.sale_payment_id]
    refunds = [line.refund_payment_id for line in lines if line.refund_payment_id]
    comps = [line.sale_id for line in lines if line.key.startswith("gift-")]
    copied: set[str] = set()
    if payments:
        copied |= {
            f"{kind}-{payment}"
            for kind, payment in Movement.objects.filter(
                sale_payment_id__in=payments
            ).values_list("type", "sale_payment_id")
        }
    if refunds:
        copied |= {
            f"refund-{leg}"
            for leg in Movement.objects.filter(refund_payment_id__in=refunds).values_list(
                "refund_payment_id", flat=True
            )
        }
    if comps:
        copied |= {
            f"gift-{sale}"
            for sale in Movement.objects.filter(
                sale_id__in=comps, type="sale", sale_payment__isnull=True
            ).values_list("sale_id", flat=True)
        }
    return copied


def session_lines(session: Session, *, until: dt.datetime | None = None) -> list[Line]:
    """Every line of ``session``: its stored movements and, while it is open, sale's lines since it opened
    (up to ``until``: the cut-off of a forgotten session, which its auto-close will freeze)."""
    lines = [stored_line(movement) for movement in session.movements.all()]
    if session.is_open:
        lines += [
            replace(line, session_id=session.id)
            for line in sale_lines(session.opened_at, until)
        ]
    return lines


Window = tuple[dt.datetime, dt.datetime | None]


def open_session_now() -> Session | None:
    return (
        Session.objects.select_related("register")
        .filter(status=Session.Status.OPEN)
        .first()
    )


def unassigned_window(
    session: Session | None, settings: Settings, now: dt.datetime
) -> Window | None:
    """Where the sale lines that fell in no shift are (CASH_REGISTER-F17):

    - an open session past its daily cut-off: what came after the cut (its auto-close leaves it out);
    - an open session: the stragglers of the previous one (confirmed while it was closing);
    - the drawer closed: everything since the last closed session opened, stragglers included.

    None before the first shift ever closed (a hub's history before Cash register is no one's)."""
    if session is not None:
        cut = auto_close_due_at(session, settings, now)
        if cut is not None:
            return cut, None
        previous = (
            Session.objects.filter(
                status=Session.Status.CLOSED, opened_at__lt=session.opened_at
            )
            .order_by("-opened_at", "-id")
            .first()
        )
        return (previous.opened_at, previous.closed_at) if previous else None
    latest = (
        Session.objects.filter(status=Session.Status.CLOSED)
        .order_by("-opened_at", "-id")
        .first()
    )
    return (latest.opened_at, None) if latest else None


def unassigned_lines(settings: Settings, now: dt.datetime) -> list[Line]:
    window = unassigned_window(open_session_now(), settings, now)
    return sale_lines(*window) if window else []


def unassigned_totals(window: Window) -> tuple[int, int]:
    """How many sale lines of ``window`` no session copied, and their cash: counted in SQL, never listed."""
    start, end = window
    cash = Q(method_type=CASH)

    def tally(rows) -> tuple[int, int]:
        totals = rows.aggregate(
            n=CountOf("id"), cash=Coalesce(Sum("amount", filter=cash), 0)
        )
        return totals["n"], totals["cash"]

    def copied_as(kind: str):
        return Movement.objects.filter(sale_payment=OuterRef("pk"), type=kind)

    charged = tally(
        SalePayment.objects.filter(_between("sale__created_at", start, end)).exclude(
            Exists(copied_as("sale"))
        )
    )
    voided = tally(
        SalePayment.objects.filter(_between("sale__voided_at", start, end)).exclude(
            Exists(copied_as("void"))
        )
    )
    refunded = tally(
        RefundPayment.objects.filter(_between("refund__created_at", start, end)).exclude(
            Exists(Movement.objects.filter(refund_payment=OuterRef("pk")))
        )
    )
    comps = (
        Sale.objects.filter(_between("created_at", start, end), gift_total__gt=0)
        .exclude(Exists(SalePayment.objects.filter(sale=OuterRef("pk"))))
        .exclude(
            Exists(
                Movement.objects.filter(
                    sale=OuterRef("pk"), type="sale", sale_payment__isnull=True
                )
            )
        )
        .count()
    )
    return (
        charged[0] + voided[0] + refunded[0] + comps,
        charged[1] - voided[1] - refunded[1],
    )


def visible_lines(hidden: bool, lines: list[Line]) -> list[Line]:
    """A blind count hides the open session's sale, void and refund lines from whoever counts: only the
    lines written by hand are theirs to see (Square and Lightspeed hide the expected on a blind close)."""
    return [line for line in lines if line.type in Movement.MANUAL] if hidden else lines


def figures(session: Session, lines: list[Line], *, hidden: bool) -> dict:
    """The summary of a session (the X/Z report): totals by type and tender, expected, counted, difference.

    Hidden (a blind count, an open session, a reader without `view_expected_totals`): no total that adds
    up to the expected — only the float, and the lines written by hand counted."""
    sales = [line for line in lines if line.type == "sale"]

    def total(of: list[Line]) -> int:
        return sum(line.amount for line in of)

    if hidden:
        return {
            "movement_count": len(visible_lines(True, lines)),
            "opening_balance": session.opening_balance,
            **{
                key: None
                for key in (
                    "total_sales",
                    "cash_sales",
                    "card_sales",
                    "other_sales",
                    "total_refunds",
                    "total_cash_in",
                    "total_cash_out",
                    "total_gifts",
                    "expected_cash",
                )
            },
            "counted": session.closing_balance,
            "difference": session.difference,
        }
    expected = (
        session.expected_balance
        if not session.is_open
        else session.opening_balance + sum(line.cash for line in lines)
    )
    return {
        "movement_count": len(lines),
        "opening_balance": session.opening_balance,
        "total_sales": total(sales),
        "cash_sales": total([line for line in sales if line.method_type == CASH]),
        "card_sales": total([line for line in sales if line.method_type == "card"]),
        "other_sales": total(
            [line for line in sales if line.method_type in ("transfer", "other")]
        ),
        "total_refunds": total(
            [line for line in lines if line.type in ("refund", "void")]
        ),
        "total_cash_in": total([line for line in lines if line.type == "in"]),
        "total_cash_out": total([line for line in lines if line.type == "out"]),
        "total_gifts": sum(line.gift_total for line in sales),
        "expected_cash": expected,
        "counted": session.closing_balance,
        "difference": session.difference,
    }


def expected_now(session: Session) -> int:
    """The real expected cash of an open session (the negative-balance rule reads it, blind or not)."""
    return session.opening_balance + sum(line.cash for line in session_lines(session))


# ── Sessions ─────────────────────────────────────────────────────────────────────────────────────


def last_cut_off(now: dt.datetime, at: dt.time) -> dt.datetime:
    """The latest moment at ``at`` (business time) not after ``now``: today's, or yesterday's before it."""
    local = timezone.localtime(now)
    zone = local.tzinfo
    cut = dt.datetime.combine(local.date(), at, tzinfo=zone)
    if cut > local:
        cut = dt.datetime.combine(local.date() - dt.timedelta(days=1), at, tzinfo=zone)
    return cut


def auto_close_due_at(
    session: Session, settings: Settings, now: dt.datetime
) -> dt.datetime | None:
    """The cut-off an open session should have closed at, when the daily auto-close is due for it."""
    if not (settings.auto_close_enabled and session.is_open):
        return None
    cut = last_cut_off(now, settings.auto_close_time)
    return cut if session.opened_at < cut else None


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
            % {"number": session.number, "time": f"{timezone.localtime(cut):%H:%M}"},
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
    order = [
        F(column).desc(nulls_last=True)
        if params.dir == "desc"
        else F(column).asc(nulls_last=True)
        for column in columns
    ]
    page = sessions.order_by(*order, "-id" if params.dir == "desc" else "id")[
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
        "description": "One cash session by its id or number (S-261014-0001) with its report: who opened and closed it, its "
        "drawer, opening float, sales by payment method, refunds and voids, cash in and out, comps at cost, expected, "
        "counted, difference and notes, in cents. A blind count hides the expected of an open session from the reader."
    },
)
def get_session(ctx: OperationContext, params: SessionGetIn) -> dict:
    return session_detail(ctx, find_session(params.session_id, params.session))


# ── The close's summary (CASH_REGISTER-F08, F09) ─────────────────────────────────────────────────


#: What the shift review reads of other apps, by their operations' names (none is a requirement but Sales):
#: an app not on in the business has nothing pending; a reading refused leaves the review incomplete.
OPEN_CHECKS = ("sale.order.list", {"status": "open", "limit": 20})
KITCHEN_BOARD = ("kitchen.ticket.board", {})
PRINT_QUEUE = ("printing.job.summary", {})
#: The titles a review names of each kind: the count says how many there are.
MAX_LABELS = 20


def _reading(ctx: OperationContext, reading: tuple[str, dict]):
    """``reading``'s answer for ``ctx``'s person: ``None`` when its app is not on in this business (nothing
    pending there), ``False`` when it was refused or failed (the review is incomplete)."""
    name, data = reading
    try:
        op = operation_named(name)
    except UnknownOperation:
        return None
    try:
        return op(ctx, op.input.model_validate(data))
    except AppInactive:
        return None
    except OperationError:
        return False


def shift_review(ctx: OperationContext) -> dict:
    """What is still open as the drawer closes (CASH_REGISTER-F08; Toast's shift review), as the close window
    shows it: Sales' open checks, the kitchen tickets not served yet and the prints that did not come out."""
    checks, board, queue = (_reading(ctx, reading) for reading in (OPEN_CHECKS, KITCHEN_BOARD, PRINT_QUEUE))
    tickets = [*board.cooking, *board.ready] if board else []
    stuck = [row for row in queue.usages if row.pending + row.failed > 0] if queue else []
    return {
        "open_checks": checks.total if checks else 0,
        "open_check_labels": [row.label for row in checks.rows if row.label][:MAX_LABELS] if checks else [],
        "unserved": board.cooking_count + board.ready_count if board else 0,
        "unserved_labels": [ticket.label or f"#{ticket.short_number}" for ticket in tickets][:MAX_LABELS],
        "prints": sum(row.pending + row.failed for row in stuck),
        "print_usages": [row.usage for row in stuck],
        "incomplete": False in (checks, board, queue),
    }


@operation(
    "cash_register.session.closing_summary",
    kind="query",
    permission="cash_register.close_session",
    input=ClosingSummaryIn,
    output=ClosingSummaryOut,
    expose_api=True,
    ai={
        "description": "The summary of closing the drawer, before closing it: what closing a cash session (the open one "
        "unless its number is said) would give with the cash counted in cents: its number, the counted cash and, "
        "unless a blind count hides them from the reader, the expected cash and the difference (negative = short); and "
        "what is still pending at the close (open checks, kitchen tickets not served, prints that did not come out). "
        "Changes nothing. Read it before closing and tell the person this summary; with the count required and none "
        "said, it asks for the count."
    },
)
def closing_summary(ctx: OperationContext, params: ClosingSummaryIn) -> dict:
    session = session_to_close(params.session_id, params.session)
    settings = current_settings()
    require_count(params.closing_balance, settings)
    hidden = hides_expected(ctx, session, settings)
    expected = None if hidden else expected_now(session)
    counted = params.closing_balance
    return {
        "session_id": session.id,
        "number": session.number,
        "register_name": session.register.name if session.register_id else "",
        "opened_at": session.opened_at,
        "opened_by": session.opened_by,
        "opening_balance": session.opening_balance,
        "closing_balance": counted,
        "expected_balance": expected,
        "difference": None if expected is None or counted is None else counted - expected,
        "expected_hidden": hidden,
        "require_closing_balance": settings.require_closing_balance,
        "pending": shift_review(ctx),
    }


# ── Movements and counts ─────────────────────────────────────────────────────────────────────────


def line_row(line: Line) -> dict:
    return {
        "key": line.key,
        "session_id": line.session_id,
        "type": line.type,
        "amount": line.amount,
        "signed_amount": line.signed_amount,
        "method_type": line.method_type,
        "method_name": line.method_name,
        "description": line.description,
        "sale_id": line.sale_id,
        "sale_number": line.sale_number,
        "document_type": line.document_type,
        "gift_total": line.gift_total,
        "created_at": line.created_at,
        "created_by": line.created_by,
    }


@operation(
    "cash_register.movement.list",
    kind="query",
    permission="cash_register.view_movement",
    input=MovementListIn,
    output=MovementPage,
    expose_api=True,
    ai={
        "description": "The lines of a cash session (by its id or number), newest first: cash in and out written by hand, "
        "and the sales, voids and refunds of Sales with their payment method (a blind count shows whoever may not see "
        "the expected only the lines written by hand of an open session); or, with unassigned=true, the sale lines that "
        "fell in no shift. Search by concept or sale number; filter by type, payment method type and amount in cents."
    },
)
def list_movements(ctx: OperationContext, params: MovementListIn) -> dict:
    settings, now = current_settings(), timezone.now()
    if params.unassigned:
        lines = unassigned_lines(settings, now)
    else:
        session = find_session(params.session_id, params.session)
        lines = visible_lines(
            hides_expected(ctx, session, settings), lines_of(session, settings, now)
        )
    if params.search:
        text = params.search.strip().lower()
        lines = [
            line
            for line in lines
            if text in line.description.lower() or text in line.sale_number.lower()
        ]
    if params.type:
        lines = [line for line in lines if line.type == params.type]
    if params.method_type:
        lines = [line for line in lines if line.method_type == params.method_type]
    if params.amount_min is not None:
        lines = [line for line in lines if line.amount >= params.amount_min]
    if params.amount_max is not None:
        lines = [line for line in lines if line.amount <= params.amount_max]
    lines.sort(
        key=lambda line: (getattr(line, params.sort), line.key),
        reverse=params.dir == "desc",
    )
    page = lines[params.offset : params.offset + params.limit]
    return {
        "rows": [line_row(line) for line in page],
        "total": len(lines),
        "limit": params.limit,
        "offset": params.offset,
    }


def count_row(count: Count) -> dict:
    return {
        "id": count.id,
        "session_id": count.session_id,
        "type": count.type,
        "total": count.total,
        "denominations": count.denominations,
        "notes": count.notes,
        "counted_at": count.counted_at,
        "counted_by": count.counted_by,
    }


@operation(
    "cash_register.count.list",
    kind="query",
    permission="cash_register.view_count",
    input=CountListIn,
    output=CountPage,
    expose_api=True,
    ai={
        "description": "The counts of a cash session (by its id or number), newest first: opening or closing, the total "
        "counted in cents and its notes and coins."
    },
)
def list_counts(ctx: OperationContext, params: CountListIn) -> dict:
    session = find_session(params.session_id, params.session)
    direction = "-" if params.dir == "desc" else ""
    counts = Count.objects.filter(session=session).order_by(
        f"{direction}{params.sort}", f"{direction}id"
    )
    page = counts[params.offset : params.offset + params.limit]
    return {
        "rows": [count_row(count) for count in page],
        "total": counts.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


@operation(
    "cash_register.currency.get",
    kind="query",
    permission="cash_register.view_session",
    input=EmptyIn,
    output=CurrencyOut,
    expose_api=True,
    ai={
        "description": "The business's currency, its decimals and its notes and coins (face values in major units, largest "
        "first), which a count by notes and coins takes."
    },
)
def get_currency(ctx: OperationContext, params: EmptyIn) -> dict:
    currency = business_currency(ctx)
    table = DENOMINATIONS.get(currency, {})
    with translation.override(ctx.language):
        return {
            "currency": currency,
            "decimals": currency_decimals(currency),
            "bills": table.get("bills", []),
            "coins": table.get("coins", []),
        }
