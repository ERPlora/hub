"""A count of the drawer (CASH_REGISTER-F06): notes and coins added up by the server, or a typed total."""

from live.context import OperationContext
from live.operations import operation
from live.outbox import record_event

from apps.cash_register import events
from apps.cash_register.models import Count
from apps.cash_register.queries.counts import count_row
from apps.cash_register.queries.currency import count_total, normalized_count
from apps.cash_register.queries.people import actor
from apps.cash_register.queries.sessions import session_to_close
from apps.cash_register.schemas import CountAddIn, CountOut
from apps.sale.queries.business import business_currency


@operation(
    "cash_register.count.add",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cash_register.add_count",
    input=CountAddIn,
    output=CountOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "record the opening count of the drawer",
                "I counted three 20 € notes and eight 50 cent coins",
            ),
            "es": (
                "apunta el arqueo de apertura del cajón",
                "he contado 3 billetes de 20 y 8 monedas de 50 céntimos",
            ),
        },
        "description": "Record a count of the drawer of the open session (or the one whose number is said): opening (check "
        'the float) or closing (end of the shift). Give the notes and coins as {bills: {"50": 2}, coins: {"0.50": 3}} '
        "with face values in major units of the business's currency (the server adds them up), or the total in cents, "
        "which prevails. It closes nothing by itself.",
        "risk": "high",
    },
)
def add_count(ctx: OperationContext, data: CountAddIn) -> dict:
    session = session_to_close(ctx, data.session_id, data.session, lock=True)
    currency = business_currency(ctx)
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
