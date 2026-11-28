"""Refunds of the Sales app, as an invoice names them."""

from babel.numbers import get_currency_precision
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.invoice.schemas.refunds import RefundGetIn, RefundOut
from apps.sale.models.refunds import Refund
from base.business import money_text

REFUND_NOT_FOUND = _("That refund does not exist.")


@operation(
    "invoice.refund.get",
    kind="query",
    permission="invoice.view_invoice",
    input=RefundGetIn,
    output=RefundOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which rectifying invoice does the refund of sale 20261103-0012 have?",
                "what was given back in the refund of sale 20261103-0012?",
                "which rectifying invoice came from the reimbursement of sale 20261103-0012?",
            ),
            "es": (
                "¿qué rectificativa tiene la devolución de la venta 20261103-0012?",
                "¿qué se devolvió en la venta 20261103-0012 y con qué factura?",
                "¿qué rectificativa salió del reintegro de la venta 20261103-0012?",
            ),
        },
        "description": "Name a refund of the Sales app by its id: the sale it gives back, what it gave back and the "
        "number of its rectifying invoice, if issued."
    },
)
def get_refund(ctx: OperationContext, params: RefundGetIn) -> dict:
    refund = Refund.objects.select_related("sale").filter(pk=params.refund_id).first()
    if refund is None:
        raise NotFound(str(REFUND_NOT_FOUND), code="invoice.refund_not_found")
    sale = refund.sale
    with translation.override(ctx.language):
        given_back = money_text(refund.total, sale.currency)
    return {
        "id": refund.id,
        "sale_id": sale.id,
        "sale_number": sale.number,
        "total": refund.total,
        "currency": sale.currency,
        "currency_decimals": get_currency_precision(sale.currency),
        "invoice_number": refund.invoice_number,
        "label": f"{sale.number} · {given_back}",
    }
