"""Each invoice as it was handed over, for the fiscal archive of a business that left (``fiscal_archive_documents`` on
this app's config, which ``base.tenancy.fiscal_archive`` asks): the PDF of its A4, in its own language or else the
business's, never marked as a copy, and with the QR of its VeriFactu record whenever it has one, whatever the AEAT
answered: the paper the business handed its customer carried it from the moment the record was there. Each PDF is made
only when the archive asks for it: one already up from an earlier attempt is never printed again."""

from collections.abc import Callable, Iterator
from functools import partial

from django.utils import translation
from live.context import OperationContext

from apps.invoice import pdf
from apps.invoice.models import Invoice
from apps.invoice.queries import fiscal_archive, record_of, render_document


def documents(ctx: OperationContext) -> Iterator[tuple[str, str, Callable[[], bytes]]]:
    """Each invoice of the active hub by the name of its file (``<id>.pdf``), its number and how to print it; ``ctx`` is
    the platform's, in the business's language."""
    for invoice in fiscal_archive.invoices():
        yield f"{invoice.id}.pdf", invoice.number, partial(printed, ctx, invoice)


def printed(ctx: OperationContext, invoice: Invoice) -> bytes:
    """The PDF of ``invoice``'s A4 as it was handed over."""
    record = record_of(ctx, invoice)
    qr = {"url": record.qr_url, "svg": record.qr_svg} if record is not None else None
    with translation.override(invoice.language or ctx.language):
        return pdf.render_pdf(render_document(invoice, qr=qr))
