"""The platform's reactions to Sales' events (events.py ``REACTIONS``): a voided sale, or one refunded whole, voids its
tips by themselves (TIP-F06), saying who voided or refunded the sale and why. Run as the system, each in its own
transaction; a repeated delivery finds no active tip and changes nothing."""

from uuid import UUID

from live.context import OperationContext
from live.operations import operation

from apps.tip.models import Tip
from apps.tip.queries import tips
from apps.tip.schemas import ReactionOut, SaleRefundedIn, SaleVoidedIn
from apps.tip.services.tips import void_one

#: Only the platform runs them: no role of the business is given it (a role's ``tip.*`` does not reach it).
SYSTEM = "system.tip"


def _void_all(ctx: OperationContext, sale_id: UUID, by: str, reason: str) -> int:
    locked = list(
        Tip.objects.select_for_update().filter(sale_id=sale_id, status=Tip.Status.ACTIVE).values_list("id", flat=True)
    )
    for tip in tips().filter(pk__in=locked).order_by("created_at", "id"):
        void_one(ctx, tip, by, reason)
    return len(locked)


@operation(
    "tip.sale.void",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=SYSTEM,
    input=SaleVoidedIn,
    output=ReactionOut,
    ai={
        "description": "Platform reaction to sale.sale.voided: the sale's tips are voided, and what they put in a "
        "drawer goes out of the open one.",
        "risk": "normal",
    },
)
def void_sale_tips(ctx: OperationContext, data: SaleVoidedIn) -> dict:
    return {"changed": _void_all(ctx, data.sale_id, data.voided_by, data.reason)}


@operation(
    "tip.sale.refund",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=SYSTEM,
    input=SaleRefundedIn,
    output=ReactionOut,
    ai={
        "description": "Platform reaction to sale.sale.refunded: a sale refunded whole has its tips voided; a refund "
        "of only some lines leaves them.",
        "risk": "normal",
    },
)
def refund_sale_tips(ctx: OperationContext, data: SaleRefundedIn) -> dict:
    if not data.fully_refunded:
        return {"changed": 0}
    return {"changed": _void_all(ctx, data.sale_id, data.refunded_by, data.reason)}
