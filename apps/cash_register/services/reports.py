"""The X and Z reports (CASH_REGISTER-F16): a session's report, put in Printing's queue by its operation's
name."""

import uuid
from decimal import Decimal

from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.context import OperationContext
from live.errors import AppInactive, Conflict
from live.operations import UnknownOperation, operation
from live.operations import get as operation_named

from apps.cash_register.models import Session
from apps.cash_register.queries.currency import currency_decimals
from apps.cash_register.queries.sessions import find_session, hides_expected, session_detail
from apps.cash_register.queries.settings import current_settings
from apps.cash_register.schemas.sessions import SessionGetIn, SessionPrintOut
from apps.sale.queries.business import business_currency
from base.business import paper_date

REPORT_HIDDEN = _(
    "With the blind count on, the report of an open session is printed by whoever may see the expected cash."
)
NO_PRINTER = _("No receipt printer takes this report: open the session to print it on this device.")
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


def _units(cents: int, scale: Decimal, sign: int = 1) -> float:
    """Minor units as the paper's money (12.50): Printing takes amounts in units."""
    return float(Decimal(sign * cents) / scale)


def _report(ctx: OperationContext, session: Session, report: str) -> dict:
    """The ``cash_session_report`` the receipt printer paints: the session, its close (or now), who, the float and the
    expected cash then, and the detail's figures as its lines (the tips just before the expected), in the language of who prints."""
    scale = Decimal(10) ** currency_decimals(business_currency(ctx))
    with translation.override(ctx.language):
        figures = session_detail(ctx, session)["summary"]
        lines = [
            {"label": str(label), "amount": _units(figures[key], scale, sign)}
            for key, label, sign in REPORT_LINES
            if figures[key] is not None and (key != "other_sales" or figures[key])
        ]
        lines[-1:-1] = [{"label": row["label"], "amount": _units(row["amount"], scale)} for row in figures["app_lines"] or ()]
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
        "date": paper_date(session.closed_at or timezone.now()),
        "cashier": cashier,
        "opening_balance": _units(session.opening_balance, scale),
        "closing_balance": _units(figures["expected_cash"], scale),
        "transactions": lines,
    }


@operation(
    "cash_register.session.print",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cash_register.view_session",
    input=SessionGetIn,
    output=SessionPrintOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "print the X report of the till",
                "print the Z of last night's close",
            ),
            "es": (
                "saca el informe X de cómo va la caja",
                "imprime la Z del cierre de anoche",
            ),
        },
        "description": "Print the report of a cash session (by its id or number) on the receipt printer: the partial "
        "report (X) while it is open, the closing (Z) once closed, with its float, sales by payment method, refunds, cash "
        "in and out, tips, comps, expected, counted and difference. Without an active receipt printer it fails and "
        "says why: nothing printed. A blind count keeps an open session's report from whoever may not see the "
        "expected cash.",
        "risk": "normal",
    },
)
def print_session(ctx: OperationContext, data: SessionGetIn) -> dict:
    session = find_session(ctx, data.session_id, data.session)
    if hides_expected(ctx, session, current_settings()):
        raise Conflict(str(REPORT_HIDDEN), code="cash_register.report_hidden")
    report = "x" if session.is_open else "z"
    with translation.override(ctx.language):
        nothing = Conflict(str(NO_PRINTER), code="cash_register.no_printer")
    request = {
        "job_key": f"cash-session-{session.id}-{report}-{uuid.uuid7()}",
        "document_type": "cash_session_report",
        "document": _report(ctx, session, report),
        "usage": "receipt",
        "currency": business_currency(ctx),
        "source_app": "cash_register",
        "source_ref": session.number,
    }
    try:
        summary = operation_named("printing.job.summary")
        create = operation_named("printing.job.create")
        printing = summary(ctx, summary.input.model_validate({}))
        # Without an active receipt printer the paper would wait in the queue for ever: the screen prints it.
        receipt = any(row.usage == "receipt" and row.printers for row in printing.usages)
        job = create(ctx, create.input.model_validate(request)).job if receipt else None
    except (UnknownOperation, AppInactive):
        job = None
    if job is None:
        raise nothing
    return {"report": report, "job_id": job.id, "printer": job.printer_name}
