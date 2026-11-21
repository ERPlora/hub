"""The sale's paper through Printing (PRINTING-F07, F08, F09, F13; SALE-F21, F29): a sale's ticket and an open
check's bill, which the check notes as asked for (TABLE-F34)."""

import logging
import uuid

from babel.numbers import get_currency_precision
from django.db import DatabaseError
from django.utils import timezone, translation
from live.context import OperationContext
from live.errors import AppInactive, OperationError
from live.operations import AI, UnknownOperation, atomic, get, operation
from live.outbox import record_event

from apps.sale import events, paper
from apps.sale.models import FiscalStatus, Order
from apps.sale.queries.business import business_currency
from apps.sale.queries.checkout import preview
from apps.sale.queries.letterhead import business_letterhead
from apps.sale.queries.orders import find_order
from apps.sale.queries.people import person_names
from apps.sale.queries.receipt_codes import receipt_url
from apps.sale.queries.sales import find_sale, sale_detail
from apps.sale.queries.settings import current_settings
from apps.sale.schemas.checkout import PreviewIn
from apps.sale.schemas.orders import OrderRefIn
from apps.sale.schemas.sales import PaperOut, SaleOut, SalePrintIn

logger = logging.getLogger(__name__)


PRINT_JOB = "printing.job.create"
FISCAL_RECORD = "verifactu.record.by_invoice"
NOT_QUEUED = {"queued": False, "job_id": None, "printer": None}


class _Unprintable(Exception):
    """This paper cannot go to the queue now: the device prints the screen's paper, which says why."""


def _queue_paper(ctx: OperationContext, request: dict) -> dict:
    """Asks Printing for one paper by its operation's name (no ``requires``: the charge calls the queue inside its own
    transaction, and nothing happens when Printing is not on), in a savepoint of its own. A job no printer would take
    (it would wait in the queue for ever) is undone. Never raises for Printing: off, absent, refusing, failing or
    without a printer, the answer is «not queued» and the device prints the screen's paper; the write that asked goes
    on."""
    try:
        op = get(PRINT_JOB)
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
        logger.warning("sale: Printing did not queue %s (%s); the screen prints it", request["job_key"], failure)
        return dict(NOT_QUEUED)
    if job is None:
        return dict(NOT_QUEUED)
    return {"queued": True, "job_id": job.id, "printer": job.printer_name}


def _fiscal_record(ctx: OperationContext, sale: SaleOut) -> dict | None:
    """VeriFactu's record of the sale's document (its QR), read by name: none without VeriFactu or before it sealed
    it (the paper goes without a QR, as on screen). A record that cannot be read keeps the paper from the queue:
    never a paper without its QR (VERIFACTU-F19)."""
    if sale.invoice_id is None:
        return None
    try:
        op = get(FISCAL_RECORD)
    except UnknownOperation:
        return None
    try:
        found = op(ctx, op.input.model_validate({"invoice_id": str(sale.invoice_id)}))
    except AppInactive:
        return None
    except OperationError as refused:
        raise _Unprintable from refused
    return found.record.model_dump() if found.record else None


def _print_sale(ctx: OperationContext, detail: SaleOut, *, duplicate: bool, key: str, at_checkout: bool = False) -> dict:
    """The receipt (or the full invoice) of the sale ``detail`` to the receipt printer's queue, a ticket with the code
    its customer asks for the full invoice with. ``at_checkout``: the print by itself of the charge — it follows the
    printing settings, and the drawer opens only when cash came in. A fiscal document still pending never prints as if
    issued: the screen's paper says it is pending."""
    if detail.invoice_status == FiscalStatus.PENDING:
        return dict(NOT_QUEUED)
    try:
        record = _fiscal_record(ctx, detail)
    except _Unprintable:
        return dict(NOT_QUEUED)
    settings = current_settings()
    currency = detail.currency
    with translation.override(ctx.language):
        kind, document = paper.receipt(
            detail,
            letterhead=business_letterhead(ctx, detail.invoice_id),
            footer=settings.receipt_footer,
            duplicate=duplicate,
            record=record,
        )
        document.update(paper.cashier(person_names([detail.created_by]).get(detail.created_by, "")))
        if detail.receipt_code:
            document.update(paper.claim(detail.receipt_code, receipt_url(ctx, detail.receipt_code)))
    request = {
        "job_key": key,
        "document_type": kind,
        "document": document,
        "currency": currency,
        "source_app": "sale",
        "source_ref": document["receipt_id"][:64],
    }
    if at_checkout:
        request.update(automatic=True, open_drawer=any(payment.method_type == "cash" for payment in detail.payments))
    return _queue_paper(ctx, request)


def _note_bill_requested(ctx: OperationContext, order: Order) -> None:
    """The check keeps its bill's first print, with its own event. Printing it again changes nothing, and never its
    version: the screen still charges the check with the version it showed."""
    if order.bill_printed_at is not None:
        return
    order.bill_printed_at = timezone.now()
    order.save(update_fields=["bill_printed_at", "updated_at"])
    record_event(ctx, events.ORDER_CHANGED, {"order_id": str(order.id)})


@operation(
    "sale.sale.print",
    kind="command",
    permission="sale.view_sale",
    input=SalePrintIn,
    output=PaperOut,
    expose_api=True,
    ai=AI(
        description="Print a sale's receipt (or its full invoice) again on the receipt printer, marked «DUPLICATE», by "
        "the sale's id or number. Not queued (Printing off, no receipt printer, its fiscal document still pending): "
        "say so; the screen prints it. It creates no sale nor fiscal document.",
        risk="normal",
        asks={
            "en": (
                "print the last ticket again",
                "reprint the receipt of sale 7",
                "print her a copy of the invoice of sale 7",
            ),
            "es": (
                "imprime otra vez el último ticket",
                "sácame una copia del tique de la venta 7",
                "vuelve a imprimir la factura de esa venta",
            ),
        },
    ),
)
def print_sale(ctx: OperationContext, data: SalePrintIn) -> dict:
    sale = find_sale(data.sale_id, data.sale)
    with translation.override(ctx.language):
        detail = SaleOut.model_validate(sale_detail(sale))
    return _print_sale(ctx, detail, duplicate=data.duplicate, key=f"sale-{sale.id}-print-{uuid.uuid7()}")


@operation(
    "sale.order.print_bill",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.view_sale",
    input=OrderRefIn,
    output=PaperOut,
    expose_api=True,
    ai=AI(
        description="Print the bill of an open check for the table (not an invoice: no number, no payment) on the "
        "receipt printer. Each call prints one. Not queued (Printing off, no receipt printer): say so; the screen "
        "prints it. Either way its table shows «Bill requested» on the floor plan until the check is charged in full.",
        risk="normal",
        asks={
            "en": (
                "print the bill for table 4",
                "bring them the check on paper",
            ),
            "es": (
                "imprime la cuenta de la mesa 4",
                "sácame la precuenta de la terraza",
                "tráeles la cuenta en papel",
            ),
        },
    ),
)
def print_bill(ctx: OperationContext, data: OrderRefIn) -> dict:
    order = find_order(data.order_id, lock=True)
    valued = preview(ctx, PreviewIn(order_id=data.order_id))
    currency = business_currency(ctx)
    with translation.override(ctx.language):
        document = paper.bill(
            valued, label=order.label, letterhead=business_letterhead(ctx), decimals=get_currency_precision(currency)
        )
    _note_bill_requested(ctx, order)
    return _queue_paper(
        ctx,
        {
            "job_key": f"sale-order-{order.id}-bill-{uuid.uuid7()}",
            "document_type": "prebill",
            "document": document,
            "currency": currency,
            "source_app": "sale",
            "source_ref": order.label[:64],
        },
    )
