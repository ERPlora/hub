"""Charging an open check sends first what is still pending on it to the kitchen, as the till's «Charge» does: nobody
pays for a dish the kitchen never gets. Without Kitchen, or for a person who cannot send to it, the check is charged
as always, as their till does."""

from live.context import OperationContext
from live.errors import AppInactive, Conflict
from live.operations import UnknownOperation, get

from apps.sale.models.orders import Order
from apps.sale.models.sales import Sale
from apps.sale.queries.orders import find_order
from apps.sale.schemas.checkout import CompleteIn
from base.operations import call

SEND = "kitchen.ticket.send"
#: The answers of a send with nothing to cook (all sent, or services only): the till charges all the same.
NOTHING_TO_SEND = frozenset({"sale.nothing_to_fire", "kitchen.nothing_to_cook"})


def _chargeable(data: CompleteIn) -> Order | None:
    """The open check this charge is for, locked, as the screen read it; none for a counter sale, a retry of a charge
    already made or a check the charge refuses anyway (closed, or changed since)."""
    if data.order_id is None or Sale.objects.filter(idempotency_key=data.idempotency_key).exists():
        return None
    order = find_order(data.order_id, lock=True)
    if order.status != Order.Status.OPEN or data.order_version not in (None, order.version):
        return None
    return order


def _sends_to_kitchen(ctx: OperationContext) -> bool:
    """Whether this business has Kitchen and this person may send to it, as the till decides it shows the send."""
    try:
        send = get(SEND)
    except UnknownOperation:
        return False
    return ctx.has(send.permission)


def _send(ctx: OperationContext, order: Order) -> bool:
    """Whether the kitchen took what is pending on ``order`` as a new round. Kitchen off, or nothing to cook, sends
    nothing; any other refusal refuses the charge, as the till does not open the charge then."""
    try:
        call(ctx, SEND, {"order_id": str(order.id)})
    except AppInactive:
        return False
    except Conflict as refused:
        if refused.code not in NOTHING_TO_SEND:
            raise
        return False
    return True


def send_pending(ctx: OperationContext, data: CompleteIn) -> CompleteIn:
    """``data`` as the charge takes it once the check's pending dishes are with the kitchen. The version the screen
    read still charges: the only change since is this very send."""
    order = _chargeable(data) if _sends_to_kitchen(ctx) else None
    if order is None or not _send(ctx, order) or data.order_version is None:
        return data
    order.refresh_from_db(fields=["version"])
    return data.model_copy(update={"order_version": order.version})
