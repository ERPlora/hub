"""The close's summary: what closing the drawer would give, and what is still pending as it closes."""

from live.context import OperationContext
from live.errors import AppInactive, OperationError
from live.operations import UnknownOperation, operation
from live.operations import get as operation_named

from apps.cash_register.queries.figures import expected_now
from apps.cash_register.queries.sessions import (
    hides_expected,
    require_count,
    session_to_close,
)
from apps.cash_register.queries.settings import current_settings
from apps.cash_register.schemas import ClosingSummaryIn, ClosingSummaryOut


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
        "asks": {
            "en": (
                "what difference would 200 € counted give at the close?",
                "before closing, is anything still pending?",
            ),
            "es": (
                "¿qué diferencia saldría con 200 € contados en el cajón?",
                "antes de cerrar, ¿hay algo pendiente?",
            ),
        },
        "description": "The summary of closing the drawer, before closing it: what closing a cash session (the open one "
        "unless its number is said) would give with the cash counted in cents: its number, the counted cash and, "
        "unless a blind count hides them from the reader, the expected cash and the difference (negative = short); and "
        "what is still pending at the close (open checks, kitchen tickets not served, prints that did not come out). "
        "Changes nothing. To close, read it with the count said and, in the same answer where you tell the person this "
        "summary, call cash_register.session.close: its card is the confirmation. With the count required and none said, "
        "it asks for the count."
    },
)
def closing_summary(ctx: OperationContext, params: ClosingSummaryIn) -> dict:
    session = session_to_close(ctx, params.session_id, params.session)
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
