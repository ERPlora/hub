"""What Services tells Sales of a voucher sold: the line of a sale that charged it (SERVICE-F14, SERVICE-F36).

Sales is no requirement of Services: its operations are asked by name for the caller, whose permissions apply and
whose refusals reach the caller as they are. Granting a voucher with its sale and saying its sale later make the same
call, ``sale.sale.voucher_sold``: Sales checks the line and keeps that much of it out of who sold it, on the day of
its sale. Saying it later counts from then on: the sessions already done keep the value they were given.
"""

from typing import Any
from uuid import UUID

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, Conflict
from live.operations import UnknownOperation, operation
from live.outbox import record_event

from apps.service import events
from apps.service.models import Grant
from apps.service.queries import SALES_UNAVAILABLE, balance, find_grant, load_grant, lock_grant, redeem_refusal
from apps.service.schemas import GrantOut
from apps.service.schemas.grant_sales import GrantSaleIn
from base.operations import call

VOUCHER_SOLD = "sale.sale.voucher_sold"

GRANT_ALREADY_SOLD = _("That voucher already says the sale that charged it.")
GRANT_GIVEN_AWAY = _("That voucher was given away: no sale charged it.")
#: Why a voucher with no session left to count says no sale (``queries.redeem_refusal``) → its code and its message.
NOTHING_LEFT_TO_COUNT = {
    "voided": ("service.grant_voided", _("This voucher was voided: it can no longer be used.")),
    "expired": (
        "service.grant_expired",
        _("This voucher has expired: extend it with Adjust if sessions are still to be done."),
    ),
    "no_uses_left": (
        "service.grant_no_uses_left",
        _("This voucher has no sessions left to do: what it cost still counts for whoever sold it."),
    ),
}


def tell_sales(ctx: OperationContext, name: str, data: dict) -> Any:
    """Sales' operation ``name``, asked by name for the caller: Sales is no requirement of Services (its permission
    applies and its refusals reach the caller as they are). ``None`` without Sales in the business (absent or off):
    there is no figure to keep the voucher's line out of."""
    try:
        return call(ctx, name, data)
    except (UnknownOperation, AppInactive):
        return None


def charged_on(ctx: OperationContext, sale_id: UUID | None, line_id: UUID | None, amount: int) -> Any:
    """The sale and the line that charged a voucher of ``amount``, as Sales checks them: the line is of that sale (or
    the one it charged, never guessed among several), the sale was not voided and the line has that much left to pay
    for vouchers. ``None`` without Sales."""
    return tell_sales(ctx, VOUCHER_SOLD, {"sale_id": sale_id, "line_id": line_id, "amount": amount})


def _refuse_saying_its_sale(grant: Grant) -> None:
    """Refuses a voucher that already says its sale, one given away and one with no session left to count."""
    if grant.sale_line_id is not None:
        raise Conflict(str(GRANT_ALREADY_SOLD), code="service.grant_already_sold")
    if not grant.amount:
        raise Conflict(str(GRANT_GIVEN_AWAY), code="service.grant_given_away")
    if refusal := redeem_refusal(grant, balance(grant), None):
        code, message = NOTHING_LEFT_TO_COUNT[refusal]
        raise Conflict(str(message), code=code)


@operation(
    "service.grant.link",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.adjust_grant",
    input=GrantSaleIn,
    output=GrantOut,
    expose_api=True,
    ai={
        "description": "Say which sale (and which of its lines, if it charged several) charged a voucher granted "
        "without it: from now on its sessions count for whoever does them, the ones already done stay at 0, and that "
        "much of the line stops counting for the seller, on the day of that sale. The voucher's id comes from "
        "service.grant.list (by its owner's name or phone, or its package).",
        "risk": "high",
        "asks": {
            "en": (
                "Nuria's massage voucher was paid in sale 20261014-0007",
                "say which sale paid for Rocío's laser voucher",
            ),
            "es": (
                "Nuria pagó su bono de masajes en la venta 20261014-0007",
                "di en qué venta se pagó el bono de láser de Rocío",
            ),
        },
    },
)
def link_sale(ctx: OperationContext, data: GrantSaleIn) -> dict:
    lock_grant(data.id)
    grant = find_grant(data.id)
    _refuse_saying_its_sale(grant)
    sold_on = charged_on(ctx, data.sale_id, data.sale_line_id, grant.amount)
    if sold_on is None:
        raise Conflict(str(SALES_UNAVAILABLE), code="service.sales_unavailable")
    Grant.objects.filter(pk=grant.pk).update(
        sale_id=sold_on.sale_id, sale_line_id=sold_on.line_id, updated_at=timezone.now()
    )
    record_event(
        ctx,
        events.GRANT_SALE_LINKED,
        {
            "id": str(grant.id),
            "package_id": str(grant.package_id),
            "customer_id": str(grant.customer_id),
            "sale_id": str(sold_on.sale_id),
            "sale_line_id": str(sold_on.line_id),
        },
    )
    return load_grant(ctx, grant.id)
