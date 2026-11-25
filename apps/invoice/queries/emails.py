"""The emails of an invoice (INVOICE-F26): their log, the address proposed and what one of them says."""

from dataclasses import dataclass, replace

from django.template.loader import render_to_string
from django.utils import translation
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.operations import operation

from apps.invoice.models import Invoice, InvoiceEmail
from apps.invoice.queries.documents import RECORD_UNREADABLE, document_title
from apps.invoice.queries.pdf import CONTENT_TYPE, PDF_UNAVAILABLE, file_name, printed
from apps.invoice.queries.platform_reading import source_of
from apps.invoice.queries.rows import find_invoice
from apps.invoice.schemas.emails import EmailListIn, EmailListOut
from base.business import money_text
from base.operations import business_name
from base.queries.catalog_images import business_language

SUBJECT = _("%(document)s %(number)s from %(business)s")
#: The paper the till handed over was the original.
COPIES = (Invoice.Source.SALE, Invoice.Source.REFUND, Invoice.Source.VOID)

UNAVAILABLE = "invoice.email_unavailable"
NO_REPLY = "invoice.email_no_reply"
#: Why an email was not sent, by the code its log keeps.
REASONS = {
    UNAVAILABLE: _("The email could not be sent right now. Try again in a few minutes."),
    "invoice.email_refused": _("That address does not accept the email. Check it and send it again."),
    "invoice.email_unconfirmed": _(
        "We could not confirm that the email was sent. Ask the customer before sending it again."
    ),
    NO_REPLY: _(
        "The owner's account has no email to receive the customer's replies. Add one on erplora.com to send invoices."
    ),
    "invoice.pdf_unavailable": PDF_UNAVAILABLE,
    "invoice.record_unreadable": RECORD_UNREADABLE,
}


@dataclass(frozen=True)
class Message:
    """What one email of an invoice says, with the PDF it carries."""

    subject: str
    body: str
    filename: str
    content: bytes
    content_type: str = CONTENT_TYPE


def reason_of(code: str) -> str:
    """Why an email was not sent, in the active language; empty when it did not fail."""
    return str(REASONS.get(code, REASONS[UNAVAILABLE])) if code else ""


def email_row(email: InvoiceEmail) -> dict:
    """An ``InvoiceEmailOut``."""
    return {
        "id": email.id,
        "to": email.to_address,
        "status": email.status,
        "requested_at": email.requested_at,
        "sent_at": email.sent_at,
        "reason": reason_of(email.error_code),
    }


def proposed_address(invoice: Invoice) -> str:
    """The email on the customer's card; empty without one, and once the card is deleted or erased."""
    card = invoice.customer
    return card.email if card is not None and card.deleted_at is None else ""


def message_of(ctx: OperationContext, invoice_id) -> Message:
    """The email of an invoice, in its language or else the business's. It prints its PDF: never inside a command."""
    ctx = replace(ctx, language=business_language(ctx))
    invoice = Invoice.objects.get(pk=invoice_id)
    content = printed(ctx, invoice, duplicate=source_of(invoice) in COPIES)
    language = invoice.language or ctx.language
    with translation.override(language):
        document = document_title(invoice)
        payable = invoice.withholding_rate is not None
        amount = invoice.payable_amount if payable else invoice.total_amount
        business = business_name(ctx.scope) or invoice.issuer_name
        return Message(
            subject=str(SUBJECT) % {"document": document, "number": invoice.number, "business": business},
            body=render_to_string(
                "invoice/email.txt",
                {
                    "invoice": invoice,
                    "document": document,
                    "business": business,
                    "issue_date": date_format(invoice.issue_date, "SHORT_DATE_FORMAT"),
                    "due_date": date_format(invoice.due_date, "SHORT_DATE_FORMAT") if invoice.due_date else "",
                    "payable": payable,
                    "amount": money_text(amount, invoice.currency, language=language),
                },
            ),
            filename=file_name(invoice),
            content=content,
        )


@operation(
    "invoice.email.list",
    kind="query",
    permission="invoice.view_invoice",
    input=EmailListIn,
    output=EmailListOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "did FACT-2025-000317 reach Carpintería Lema by email?",
                "which address did we email FACT-2025-000317 to?",
            ),
            "es": (
                "¿le llegó por correo la FACT-2025-000317 a Carpintería Lema?",
                "¿a qué dirección de correo mandamos la FACT-2025-000317?",
            ),
        },
        "description": "The emails one invoice was sent in, the newest first: to which address, when, whether each left "
        "and, if not, why; and the email on its customer's card.",
        "risk": "normal",
    },
)
def list_emails(ctx: OperationContext, params: EmailListIn) -> dict:
    invoice = find_invoice(ctx, params.invoice_id, params.number)
    with translation.override(ctx.language):
        return {
            "customer_email": proposed_address(invoice),
            "emails": [email_row(email) for email in invoice.emails.all()],
        }
