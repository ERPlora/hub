"""A full invoice for a ticket (INVOICE-F05): an F3 that replaces the ticket, with the customer's details and the
ticket's very figures.
"""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation

from apps.invoice import fiscal
from apps.invoice.models import Invoice
from apps.invoice.queries.rows import find_invoice
from apps.invoice.queries.series import FULL
from apps.invoice.schemas import IssueOut, SubstituteIn
from apps.invoice.services.issuer import _configured_issuer, _issuer_of
from apps.invoice.services.issuing import VERBATIM, _issue
from apps.invoice.services.numbering import series_of_year
from apps.invoice.services.recipient import _chosen_card, _recipient
from apps.invoice.services.writes import _result, _today

NOT_A_TICKET = _(
    "Only a ticket (simplified invoice) can be replaced by a full invoice."
)


TICKET_CANCELLED = _(
    "This ticket is cancelled: it can no longer be replaced by a full invoice."
)


TICKET_RECTIFIED = _(
    "This ticket already has rectifying invoices: it can no longer be replaced by a full invoice."
)


@operation(
    "invoice.invoice.substitute",
    kind="command",
    permission="invoice.add_invoice",
    input=SubstituteIn,
    output=IssueOut,
    ai={
        "asks": {
            "en": (
                "turn the ticket of sale 20261103-0012 into a full invoice for Carpintería Lema",
                "give the customer a full invoice with their details for their ticket",
                "turn the simplified one of sale 20261103-0012 into a full one",
            ),
            "es": (
                "pasa el tique de la venta 20261103-0012 a factura completa a nombre de Carpintería Lema",
                "el cliente pide su tique en factura con sus datos",
            ),
        },
        "description": "The customer asks for the full invoice of their ticket: issue a full invoice (F3) that replaces "
        "the ticket (by its number), with the customer's name, tax ID and address (or their card) and the ticket's "
        "very figures. The ticket is not touched. A ticket has one; asking again answers it without issuing another.",
        "risk": "high",
    },
)
def substitute(ctx: OperationContext, data: SubstituteIn) -> dict:
    card = _chosen_card(ctx, data)
    ticket = find_invoice(ctx, data.invoice_id, data.number, lock=True)
    if ticket.invoice_type != "F2":
        raise Conflict(str(NOT_A_TICKET), code="invoice.not_a_ticket")
    existing = Invoice.objects.filter(substitutes=ticket).first()
    if existing is not None:
        return _result(ctx, existing, issued=False, already=True)
    if ticket.status == Invoice.Status.CANCELLED:
        raise Conflict(str(TICKET_CANCELLED), code="invoice.already_cancelled")
    if ticket.rectifications.exists():
        raise Conflict(str(TICKET_RECTIFIED), code="invoice.ticket_rectified")
    recipient = _recipient(ctx, data, full=True, card=card)
    _configured_issuer()
    series = series_of_year(FULL, _today().year, ctx)
    invoice = _issue(
        ctx,
        series=series,
        invoice_type="F3",
        entries=list(ticket.tax_breakdown),
        lines=[
            {
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "discount_amount": line.discount_amount,
                "tax_rate": line.tax_rate,
                "surcharge_rate": line.surcharge_rate,
                "tax_category_key": line.tax_category_key,
                "base_amount": line.base_amount,
                "tax_amount": line.tax_amount,
                "total_amount": line.total_amount,
                "product_id": line.product_id,
                "sale_line_id": line.sale_line_id,
            }
            for line in ticket.lines.order_by("position", "id")
        ],
        tolerance={fiscal.key_of(item): VERBATIM for item in ticket.tax_breakdown},
        recipient=recipient,
        issuer=_issuer_of(ticket),
        operation_date=ticket.operation_date,
        source_type=Invoice.Source.SUBSTITUTION,
        source_sale=ticket.source_sale,
        substitutes=ticket,
        status=ticket.status,
        paid_at=ticket.paid_at,
        currency=ticket.currency,
        description=ticket.description,
    )
    return _result(ctx, invoice, issued=True)
