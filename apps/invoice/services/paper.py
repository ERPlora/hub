"""Paper (INVOICE-F18 → PRINTING-F08): an invoice's A4 page sent to Printing's queue, with its VeriFactu QR.
"""

import uuid

from django.db import DatabaseError
from django.utils import translation
from live.context import OperationContext
from live.errors import AppInactive, OperationError
from live.operations import UnknownOperation, atomic, operation
from live.operations import get as get_operation

from apps.invoice.models import Invoice
from apps.invoice.queries.documents import render_document
from apps.invoice.queries.platform_invoices import VERIFACTU_BY_INVOICE
from apps.invoice.queries.rows import find_invoice
from apps.invoice.schemas import DocumentIn, PaperOut
from apps.invoice.services.writes import logger

PRINT_JOB = "printing.job.create"


NOT_QUEUED = {"queued": False, "job_id": None, "printer": None}


class _Unprintable(Exception):
    """This page cannot go to the queue now: the device prints the screen's paper."""


def _queue_paper(ctx: OperationContext, request: dict) -> dict:
    """Asks Printing for one page by its operation's name (no ``requires``: nothing happens when Printing is not
    on), in a savepoint of its own. A job no printer would take (it would wait in the queue for ever) is undone.
    Never raises for Printing: off, absent, refusing, failing or without a printer, the answer is «not queued»
    and the device prints the screen's paper."""
    try:
        op = get_operation(PRINT_JOB)
    except UnknownOperation:
        return dict(NOT_QUEUED)
    try:
        with atomic():
            job = op(ctx, op.input.model_validate(request)).job
            if job is not None and job.printer_id is None:
                raise _Unprintable
    except (_Unprintable, AppInactive):
        return dict(NOT_QUEUED)
    except (OperationError, DatabaseError) as failure:
        logger.warning("invoice: Printing did not queue %s (%s); the screen prints it", request["job_key"], failure)
        return dict(NOT_QUEUED)
    if job is None:
        return dict(NOT_QUEUED)
    return {"queued": True, "job_id": job.id, "printer": job.printer_name}


def _qr_of(ctx: OperationContext, invoice: Invoice) -> dict | None:
    """VeriFactu's QR of ``invoice`` (``{"url", "svg"}``), read by name: none without VeriFactu or without a record
    (the page goes without it, as on screen). A record that cannot be read keeps the page from the queue: never a
    page without its QR (VERIFACTU-F19)."""
    try:
        op = get_operation(VERIFACTU_BY_INVOICE)
    except UnknownOperation:
        return None
    try:
        found = op(ctx, op.input.model_validate({"invoice_id": str(invoice.id)}))
    except AppInactive:
        return None
    except OperationError as refused:
        raise _Unprintable from refused
    record = found.record
    return {"url": record.qr_url, "svg": record.qr_svg} if record is not None else None


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
        "language and with its VeriFactu QR; duplicate marks it as a copy. Each call prints one. Not queued "
        "(Printing off, no system printer, its VeriFactu record not there yet): say so; the screen prints it. It "
        "issues nothing.",
        "risk": "normal",
    },
)
def print_invoice(ctx: OperationContext, data: DocumentIn) -> dict:
    invoice = find_invoice(ctx, data.invoice_id, data.number)
    try:
        qr = _qr_of(ctx, invoice)
    except _Unprintable:
        return dict(NOT_QUEUED)
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
