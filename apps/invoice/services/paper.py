"""Paper (INVOICE-F18 → PRINTING-F08): an invoice's A4 page sent to Printing's queue, with its VeriFactu QR. A page
no printer takes is not printed, and the print fails with why: the invoice's screen prints its own paper instead, and
the assistant's receipt says it was not done (BASE-F99).
"""

import uuid

from django.db import DatabaseError
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, Conflict, OperationError
from live.operations import UnknownOperation, atomic, operation
from live.operations import get as get_operation

from apps.invoice.queries.documents import qr_of, render_document
from apps.invoice.queries.rows import find_invoice
from apps.invoice.schemas.invoices import DocumentIn, PaperOut
from apps.invoice.services.writes import logger

PRINT_JOB = "printing.job.create"

NO_PRINTER = _("No system printer takes this invoice: open it to print it or save it as PDF.")


class _Unprintable(Exception):
    """No printer takes this page now."""


def _not_printed(ctx: OperationContext, message, code: str) -> Conflict:
    with translation.override(ctx.language):
        return Conflict(str(message), code=code)


def _queue_paper(ctx: OperationContext, request: dict) -> dict:
    answer = _queued_job(ctx, request)
    if answer is None:
        raise _not_printed(ctx, NO_PRINTER, "invoice.no_printer")
    job = answer.job
    return {"job_id": job.id, "printer": job.printer_name, "waits_for_device": answer.waits_for_device}


def _queued_job(ctx: OperationContext, request: dict):
    """Asks Printing for one page by its operation's name (no ``requires``: Printing may not be on), in a savepoint
    of its own, and gives its answer. A job no printer would take (it would wait in the queue for ever) is undone.
    ``None`` when no printer takes the page: Printing off, absent, refusing, failing or without a printer for it."""
    try:
        op = get_operation(PRINT_JOB)
    except UnknownOperation:
        return None
    try:
        with atomic():
            answer = op(ctx, op.input.model_validate(request))
            if answer.job is None or answer.job.printer_id is None:
                raise _Unprintable
    except (_Unprintable, AppInactive):
        return None
    except (OperationError, DatabaseError) as failure:
        logger.warning("invoice: Printing did not queue %s (%s)", request["job_key"], failure)
        return None
    return answer


@operation(
    "invoice.invoice.print",
    kind="command",
    permission="invoice.view_invoice",
    input=DocumentIn,
    output=PaperOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "print FACT-2025-000317",
                "print a duplicate of FACT-2025-000317",
            ),
            "es": (
                "imprime la FACT-2025-000317",
                "imprímeme un duplicado de la FACT-2025-000317",
            ),
        },
        "description": "Print an invoice's A4 page (by its id or number) on the system printer, in the reader's "
        "language and with its VeriFactu QR; duplicate marks it as a copy. Each call prints one. With no system "
        "printer for it (or its VeriFactu record unreadable) it fails and says why: nothing was printed. Queued with "
        "waits_for_device, nothing has come out yet: say it waits in that printer's queue and prints once a device set "
        "up in Printing › Devices prints it, never that it was printed. It issues nothing.",
        "risk": "normal",
    },
)
def print_invoice(ctx: OperationContext, data: DocumentIn) -> dict:
    invoice = find_invoice(ctx, data.invoice_id, data.number)
    qr = qr_of(ctx, invoice)
    with translation.override(ctx.language):
        html = render_document(invoice, duplicate=data.duplicate, qr=qr)
    return _queue_paper(
        ctx,
        {
            "job_key": f"invoice-{invoice.id}-print-{uuid.uuid7()}",
            "document_type": "invoice",
            "format": "a4",
            "html": html,
            "source_app": "invoice",
            "source_ref": invoice.number[:64],
        },
    )
