"""The ticket's public page (INVOICE-F04): what the ticket's code opens, read by whoever holds the code, without a
session (``invoice.public``, the page ``/p/<slug>/invoice/<code>`` of base's public door).

The code is Sales' (``apps.sale.queries.receipt_codes``). Every code that opens nothing counts against the caller's
connection, and past ten within an hour the connection waits for the hour's end whatever it sends. What the page shows
of the full invoice is Invoicing's own ``invoice.invoice.get`` and VeriFactu's QR, asked by name with only what the
page needs."""

from dataclasses import replace

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, Conflict, NotFound, OperationError
from live.operations import INTERNAL, UnknownOperation, get, operation

from apps.invoice.models import Invoice
from apps.invoice.schemas.public import PublicCodeIn, PublicTicketOut
from apps.sale.queries.receipt_codes import expired, sale_of_code
from base.throttle import AttemptLimit, RateLimited, client_key

PUBLIC = "invoice.public"
#: Who the documents asked for from the page say issued them.
PUBLIC_ACTOR = "ticket code"
#: What the page needs of Invoicing and VeriFactu to issue and show the full invoice, and nothing else.
DELEGATED = frozenset({"invoice.add_invoice", "invoice.view_invoice", "verifactu.add_record", "verifactu.view_record"})
CODE_ATTEMPTS = AttemptLimit("invoice-code", attempts=10, window=3600)
FISCAL_RECORD = "verifactu.record.by_invoice"

CODE_NOT_FOUND = _("This code opens no ticket. Check it or ask for the invoice at the business.")
CODE_EXPIRED = _("This code has expired: ask for the invoice at the business.")
TICKET_PENDING = _("Your ticket is still being registered. Try again in a few minutes.")


def delegated(ctx: OperationContext) -> OperationContext:
    return replace(ctx, actor=ctx.actor or PUBLIC_ACTOR, permissions=ctx.permissions | DELEGATED)


def _caller(ctx: OperationContext) -> tuple[str, str]:
    who = client_key(ctx.request) if ctx.request is not None else f"actor:{ctx.actor}"
    return ctx.scope.key, who


def ticket_of_code(ctx: OperationContext, code: str) -> Invoice:
    """The ticket (F2) of the sale whose code is ``code``: 429 while the caller waits, 404 for a code that opens
    nothing (counted), 410 once it expired, 409 while the sale's ticket is still to be issued."""
    caller = _caller(ctx)
    if CODE_ATTEMPTS.wait(*caller):
        raise RateLimited()
    sale = sale_of_code(code)
    if sale is None:
        CODE_ATTEMPTS.failed(*caller)
        raise NotFound(str(CODE_NOT_FOUND), code="invoice.code_not_found")
    if expired(sale, timezone.now()):
        raise OperationError(str(CODE_EXPIRED), code="invoice.code_expired", status=410)
    ticket = Invoice.objects.filter(
        source_sale=sale, source_type=Invoice.Source.SALE, invoice_type="F2"
    ).first()
    if ticket is None:
        raise Conflict(str(TICKET_PENDING), code="invoice.ticket_pending")
    return ticket


def fiscal_record(ctx: OperationContext, invoice_id) -> dict | None:
    """VeriFactu's QR of a document, for its A4; none without VeriFactu or before it sealed it."""
    try:
        record_of = get(FISCAL_RECORD)
        found = record_of(delegated(ctx), record_of.input.model_validate({"invoice_id": str(invoice_id)}))
    except (UnknownOperation, AppInactive):
        return None
    record = found.record
    return {"qr_svg": record.qr_svg, "qr_url": record.qr_url} if record else None


@operation(
    "invoice.public.ticket",
    kind="query",
    permission=PUBLIC,
    input=PublicCodeIn,
    output=PublicTicketOut,
    ai=INTERNAL,
)
def public_ticket(ctx: OperationContext, data: PublicCodeIn) -> dict:
    ticket = ticket_of_code(ctx, data.code)
    full = Invoice.objects.filter(substitutes=ticket).first()
    invoice = record = None
    if full is not None:
        show = get("invoice.invoice.get")
        invoice = show(delegated(ctx), show.input.model_validate({"invoice_id": str(full.id)}))
        record = fiscal_record(ctx, full.id)
    return {
        "ticket": {
            "number": ticket.number,
            "issue_date": ticket.issue_date,
            "total_amount": ticket.total_amount,
            "currency": ticket.currency,
            "issuer_name": ticket.issuer_name,
        },
        "invoice": invoice,
        "record": record,
    }
