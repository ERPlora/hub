"""Cash brought into the drawer or taken out of it (CASH_REGISTER-F05), in the open session."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.cash_register import events
from apps.cash_register.models import Movement
from apps.cash_register.queries.figures import expected_now
from apps.cash_register.queries.lines import stored_line
from apps.cash_register.queries.movements import line_row
from apps.cash_register.queries.people import actor
from apps.cash_register.queries.sessions import session_to_close
from apps.cash_register.queries.settings import current_settings
from apps.cash_register.schemas import MovementAddIn, MovementRow

NEGATIVE_BALANCE = _(
    "This cash-out would leave the drawer below zero and a negative balance is not allowed."
)


@operation(
    "cash_register.movement.add",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cash_register.add_movement",
    input=MovementAddIn,
    output=MovementRow,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "record 20 € taken out to pay the supplier",
                "put 50 € of change from the safe in the till",
            ),
            "es": (
                "apunta una salida de 35 € de la caja",
                "mete 50 € de cambio en la caja",
            ),
        },
        "description": "Record cash brought into the drawer (type in: change from the safe) or taken out (type out: a "
        "supplier paid, money to the bank) in the open session (or the one whose number is said), with its amount in "
        "cents, always positive, and why. Cash by default; card, transfer or other do not count for the drawer. A "
        "cash-out that leaves the drawer below zero is refused unless the settings allow it.",
        "risk": "high",
    },
)
def add_movement(ctx: OperationContext, data: MovementAddIn) -> dict:
    session = session_to_close(ctx, data.session_id, data.session, lock=True)
    if (
        data.type == Movement.Type.OUT
        and data.method_type == "cash"
        and not current_settings().allow_negative_balance
        and expected_now(session) - data.amount < 0
    ):
        raise Conflict(str(NEGATIVE_BALANCE), code="cash_register.negative_balance_not_allowed")
    movement = Movement.objects.create(
        session=session,
        type=data.type,
        amount=data.amount,
        method_type=data.method_type,
        description=data.description,
        app=data.app or "",
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
            "app": movement.app,
        },
    )
    return line_row(stored_line(movement))
