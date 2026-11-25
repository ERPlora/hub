"""What a tip moves in the drawer (CASH_REGISTER-F18): Cash register's open session, asked by name, takes it as Tips'
own line, in its payment method. A closed session is never touched: what changes later goes into the open one."""

from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict

from apps.sale.models import PaymentMethod
from apps.tip.models import Tip
from base.operations import call

CASH_REGISTER_CLOSED = _("The drawer is closed: open a cash register session to record a tip in cash.")

#: Cash register's answer to «is the drawer on, and which session is open?» (CASH_REGISTER-F04).
CURRENT = "cash_register.session.current"
MOVEMENT_ADD = "cash_register.movement.add"
#: The name the drawer shows Tips' lines under (Tips in cash, Tips by card, Tips paid out).
APP = "tip"


def move(ctx: OperationContext, tip: Tip, kind: str, amount: int, *, strict: bool = False) -> UUID | None:
    """Records ``amount`` of ``tip`` coming ``in`` or going ``out`` in the open session and gives its id; ``None``
    with no session open. ``strict``: with the drawer on and closed, a tip in cash is refused (409
    ``tip.cash_register_closed``) instead of being kept out of every drawer."""
    current = call(ctx, CURRENT, {})
    if current.session is None:
        if strict and current.required and tip.method_type == PaymentMethod.Type.CASH:
            raise Conflict(str(CASH_REGISTER_CLOSED), code="tip.cash_register_closed")
        return None
    call(
        ctx,
        MOVEMENT_ADD,
        {
            "session_id": str(current.session.id),
            "type": kind,
            "amount": amount,
            "method_type": tip.method_type,
            "description": tip.sale.number if tip.sale else "",
            "app": APP,
        },
    )
    return current.session.id
