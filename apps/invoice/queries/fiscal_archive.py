"""Each invoice as it was handed over, for the fiscal archive of a business that left (``fiscal_archive_documents`` on
this app's config, which ``base.tenancy.fiscal_archive`` asks): the PDF of its A4, in its own language or else the
business's, never marked as a copy, and with VeriFactu's QR once the AEAT registered it, as
``invoice.invoice.platform_document`` prints it.

Every invoice, whatever its status, a page at a time by its key (UUIDv7: in the order they were issued). Each PDF is made
only when the archive asks for it: one already up from an earlier attempt is never printed again.

This module holds no operation, so the package's ``__init__`` does not import it: the app's config does, when asked.
"""

from collections.abc import Callable, Iterator
from functools import partial

from django.utils import translation
from live.context import OperationContext

from apps.invoice import pdf
from apps.invoice.models import Invoice
from apps.invoice.queries import IN_THE_AEAT, _record_of, render_document

#: How many invoices are read at once.
PAGE_ROWS = 500


def documents(ctx: OperationContext) -> Iterator[tuple[str, str, Callable[[], bytes]]]:
    """Each invoice by the name of its file (``<id>.pdf``), its number and how to print it, read in the database of
    the active hub; ``ctx`` is the platform's, in the business's language."""
    last = None
    while True:
        page = Invoice._base_manager.order_by("pk")
        if last is not None:
            page = page.filter(pk__gt=last)
        found = list(page[:PAGE_ROWS])
        if not found:
            return
        for invoice in found:
            yield f"{invoice.id}.pdf", invoice.number, partial(printed, ctx, invoice)
        last = found[-1].pk


def printed(ctx: OperationContext, invoice: Invoice) -> bytes:
    """The PDF of ``invoice``'s A4 as it was handed over."""
    record = _record_of(ctx, invoice)
    qr = {"url": record.qr_url, "svg": record.qr_svg} if record is not None and record.status in IN_THE_AEAT else None
    with translation.override(invoice.language or ctx.language):
        return pdf.render_pdf(render_document(invoice, qr=qr))
