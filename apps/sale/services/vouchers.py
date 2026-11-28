"""The vouchers a sale paid for and the sessions of a customer's voucher, as Services tells them."""


from django.db.models import F
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import INTERNAL, operation
from live.outbox import record_event

from apps.sale import events
from apps.sale.models.sales import SaleLine
from apps.sale.models.voucher_sessions import VoucherSession
from apps.sale.queries.business import money_text
from apps.sale.queries.figures import COUNTED
from apps.sale.queries.sales import find_sale
from apps.sale.schemas.vouchers import (
    VoucherLineOut,
    VoucherSessionIn,
    VoucherSessionOut,
    VoucherSoldIn,
    VoucherUnsoldIn,
)
from apps.tax.queries.jurisdiction import business_today

SALE_LINE_NOT_FOUND = _("That line is not in that sale.")
VOUCHER_LINE_REQUIRED = _("That sale charged several lines: say which one paid for the voucher: %(lines)s.")
VOUCHER_OVER_LINE = _("That line has %(left)s left to pay for vouchers: it cannot pay for one of %(amount)s.")
VOUCHER_SALE_VOIDED = _("That sale was voided: it paid for no voucher.")


def _line_that_sold_voucher(data: VoucherSoldIn) -> SaleLine:
    """The line ``data`` names, or the one its sale charged, locked. Never guessed: a sale that charged several says
    which one. One with no line that charged anything answers one of them: nothing fits on it."""
    lines = SaleLine.objects.select_for_update(of=("self",)).select_related("sale")
    if data.line_id is not None:
        named = lines.filter(pk=data.line_id)
        line = (named.filter(sale_id=data.sale_id) if data.sale_id else named).first()
        if line is None:
            raise NotFound(str(SALE_LINE_NOT_FOUND), code="sale.sale_line_not_found")
        return line
    sale = find_sale(data.sale_id, None)
    of_sale = list(lines.filter(sale=sale))
    charged = [line for line in of_sale if line.line_total > 0]
    if len(charged) > 1:
        raise Conflict(
            str(VOUCHER_LINE_REQUIRED)
            % {"lines": ", ".join(f"«{line.name}» {money_text(line.line_total, sale.currency)}" for line in charged)},
            code="sale.voucher_line_required",
        )
    return (charged or of_sale)[0]


@operation(
    "sale.sale.voucher_sold",
    kind="command",
    permission="sale.take_payment",
    input=VoucherSoldIn,
    output=VoucherLineOut,
    ai=INTERNAL,
)
def voucher_sold(ctx: OperationContext, data: VoucherSoldIn) -> dict:
    """Services' step when it grants a voucher saying the sale that charged it (SERVICE-F14): that much of the line is
    no production of who sold it (SALE-F28). The sale's money and documents do not move."""
    line = _line_that_sold_voucher(data)
    if line.sale.status not in COUNTED:
        raise Conflict(str(VOUCHER_SALE_VOIDED), code="sale.voucher_sale_voided")
    left = line.line_total - line.voucher_sold_amount
    if data.amount > left:
        currency = line.sale.currency
        raise Conflict(
            str(VOUCHER_OVER_LINE)
            % {"left": money_text(left, currency), "amount": money_text(data.amount, currency)},
            code="sale.voucher_over_line",
        )
    SaleLine.objects.filter(pk=line.pk).update(voucher_sold_amount=F("voucher_sold_amount") + data.amount)
    record_event(ctx, events.SALE_VOUCHER_LINE_CHANGED, {"sale_id": str(line.sale_id), "line_id": str(line.id)})
    return {"sale_id": line.sale_id, "line_id": line.id}


@operation(
    "sale.sale.voucher_unsold",
    kind="command",
    permission="sale.take_payment",
    input=VoucherUnsoldIn,
    output=VoucherLineOut,
    ai=INTERNAL,
)
def voucher_unsold(ctx: OperationContext, data: VoucherUnsoldIn) -> dict:
    """Services' step when a voucher a line paid for is voided (SERVICE-F17): the line counts for who sold it again."""
    line = SaleLine.objects.select_for_update().filter(pk=data.line_id).first()
    if line is None:
        raise NotFound(str(SALE_LINE_NOT_FOUND), code="sale.sale_line_not_found")
    SaleLine.objects.filter(pk=line.pk).update(voucher_sold_amount=max(line.voucher_sold_amount - data.amount, 0))
    record_event(ctx, events.SALE_VOUCHER_LINE_CHANGED, {"sale_id": str(line.sale_id), "line_id": str(line.id)})
    return {"sale_id": line.sale_id, "line_id": line.id}


@operation(
    "sale.voucher_session.record",
    kind="command",
    permission="sale.add_sale",
    input=VoucherSessionIn,
    output=VoucherSessionOut,
    ai=INTERNAL,
)
def record_voucher_session(ctx: OperationContext, data: VoucherSessionIn) -> dict:
    """Services' step when a session of a voucher is spent outside the till saying who did it (SERVICE-F21): no line
    carries it, so what it is worth counts in her production on today's business day (SALE-F28), the till's: the day a
    sale charged at that moment would count on. Whoever may sell may say who did a service, as on a line. The same
    session told again counts once: the first telling stays."""
    session, created = VoucherSession.objects.get_or_create(
        session_id=data.session_id,
        defaults={"staff_id": data.staff_id, "business_day": business_today(), "value": data.value},
    )
    if created:
        record_event(
            ctx,
            events.VOUCHER_SESSION_RECORDED,
            {"session_id": str(session.session_id), "staff_id": str(session.staff_id)},
        )
    return {
        "session_id": session.session_id,
        "staff_id": session.staff_id,
        "business_day": session.business_day,
        "value": session.value,
    }
