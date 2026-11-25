"""The PDF of an invoice (INVOICE-F25): its A4 page printed as a file, for the person who downloads it and for whatever
sends it."""

import base64
import re
from dataclasses import replace

from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import OperationError
from live.operations import operation

from apps.invoice.models import Invoice
from apps.invoice.queries.documents import qr_of, render_document
from apps.invoice.queries.rows import find_invoice
from apps.invoice.schemas.invoices import DocumentIn
from apps.invoice.schemas.pdf import InvoicePdfOut
from base import pdf

CONTENT_TYPE = "application/pdf"
PDF_UNAVAILABLE = _("The PDF cannot be made right now. Try again later.")
#: Whoever may see an invoice gets its QR with it, as its paper carries it.
QR_PERMISSION = "verifactu.view_record"
#: What some computer refuses in a file's name.
_REFUSED = re.compile(r'[<>:"/\\|?*]+')


def printed(ctx: OperationContext, invoice: Invoice, *, duplicate: bool = False) -> bytes:
    """The PDF of ``invoice``'s A4, with its VeriFactu QR, in its own language or else in the language of ``ctx``."""
    qr = qr_of(replace(ctx, permissions=ctx.permissions | {QR_PERMISSION}), invoice)
    with translation.override(invoice.language or ctx.language):
        page = render_document(invoice, duplicate=duplicate, qr=qr)
    try:
        return pdf.render_pdf(page)
    except OSError as missing:
        # WeasyPrint's libraries are missing on this server (the image installs them).
        with translation.override(ctx.language):
            raise OperationError(str(PDF_UNAVAILABLE), code="invoice.pdf_unavailable", status=503) from missing


def file_name(invoice: Invoice) -> str:
    """The invoice's number, with a dash for what no file can be called."""
    return f"{_REFUSED.sub('-', invoice.number).strip('-. ')}.pdf"


@operation(
    "invoice.invoice.pdf",
    kind="query",
    permission="invoice.view_invoice",
    input=DocumentIn,
    output=InvoicePdfOut,
    expose_api=True,
    ai={
        # A file with the customer's name and tax ID for a person to download: no automation runs it alone.
        "risk": "high",
        "asks": {
            "en": (
                "download FACT-2025-000317 as a PDF",
                "give me the PDF of Carpintería Lema's invoice",
            ),
            "es": (
                "descárgame el PDF de la FACT-2025-000317",
                "dame en PDF la factura de Carpintería Lema",
            ),
        },
        "description": "Writes the PDF file of one invoice (by its id or number) for the person to download: its A4 "
        "page with its VeriFactu QR. duplicate marks it as a copy.",
    },
)
def invoice_pdf(ctx: OperationContext, params: DocumentIn) -> dict:
    invoice = find_invoice(ctx, params.invoice_id, params.number)
    content = printed(ctx, invoice, duplicate=params.duplicate)
    return {
        "filename": file_name(invoice),
        "content_type": CONTENT_TYPE,
        "content_base64": base64.b64encode(content).decode("ascii"),
    }
