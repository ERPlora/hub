"""The sale's paper through Printing (PRINTING-F07, F08, F09, F13; SALE-F21, F29): a sale's ticket and an open
check's bill, which the check notes as asked for (TABLE-F34). The charge's own ticket never fails for its paper; a
reprint or a bill no printer takes is not printed and fails with why: the screen prints its own paper instead (and
notes the bill, ``sale.order.note_bill``), and the assistant's receipt says it was not done (BASE-F99)."""

import logging
import uuid

from babel.numbers import get_currency_precision
from django.db import DatabaseError
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, Conflict, OperationError
from live.operations import AI, INTERNAL, UnknownOperation, atomic, get, operation
from live.outbox import record_event

from apps.sale import events, paper
from apps.sale.models import FiscalStatus, Order
from apps.sale.queries.business import business_currency
from apps.sale.queries.checkout import preview
from apps.sale.queries.letterhead import business_letterhead
from apps.sale.queries.orders import find_order
from apps.sale.queries.people import cashier_name
from apps.sale.queries.receipt_codes import receipt_url
from apps.sale.queries.sales import sale_detail, visible_sale
from apps.sale.queries.settings import current_settings
from apps.sale.schemas.checkout import PreviewIn
from apps.sale.schemas.orders import BillNoteOut, OrderRefIn
from apps.sale.schemas.sales import PaperOut, SaleOut, SalePrintIn
from apps.sale.services.orders import _still_open

logger = logging.getLogger(__name__)


PRINT_JOB = "printing.job.create"
FISCAL_RECORD = "verifactu.record.by_invoice"
NOT_QUEUED = {"queued": False, "job_id": None, "printer": None, "waits_for_device": False}

NO_PRINTER_FOR_THE_SALE = _("No receipt printer takes this sale's paper: open the sale to print it on this device.")
NO_PRINTER_FOR_THE_BILL = _("No receipt printer takes this bill: open it in Sales to print it on this device.")
DOCUMENT_PENDING = _("Its fiscal document is still pending: open the sale to issue it.")
RECORD_UNREADABLE = _("Its VeriFactu record could not be read, and its paper never prints without its QR.")


class _Unprintable(Exception):
    """This paper does not go to the queue now; ``code`` and ``message`` say why. The device prints the screen's
    paper, which says it too."""

    def __init__(self, code: str, message) -> None:
        super().__init__(code)
        self.code, self.message = code, message

    def refusal(self, ctx: OperationContext) -> Conflict:
        """Said in the language of who asked, whatever the request's: the assistant's receipt shows it as it is."""
        with translation.override(ctx.language):
            return Conflict(str(self.message), code=self.code)


class _NoPrinter(Exception):
    """No printer takes this job: it would wait in the queue for ever."""


def _queue_paper(ctx: OperationContext, request: dict) -> dict:
    """Asks Printing for one paper by its operation's name (no ``requires``: the charge calls the queue inside its own
    transaction, and nothing happens when Printing is not on), in a savepoint of its own. A job no printer would take
    (it would wait in the queue for ever) is undone. Never raises for Printing: off, absent, refusing, failing or
    without a printer, the answer is «not queued»; the write that asked goes on."""
    try:
        op = get(PRINT_JOB)
    except UnknownOperation:
        return dict(NOT_QUEUED)
    try:
        with atomic():
            answer = op(ctx, op.input.model_validate(request))
            job = answer.job
            if job is not None and job.printer_id is None:
                raise _NoPrinter
    except (_NoPrinter, AppInactive):
        return dict(NOT_QUEUED)
    except (OperationError, DatabaseError) as failure:
        logger.warning("sale: Printing did not queue %s (%s); the screen prints it", request["job_key"], failure)
        return dict(NOT_QUEUED)
    if job is None:
        return dict(NOT_QUEUED)
    return {"queued": True, "job_id": job.id, "printer": job.printer_name, "waits_for_device": answer.waits_for_device}


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
        raise _Unprintable("sale.record_unreadable", RECORD_UNREADABLE) from refused
    return found.record.model_dump() if found.record else None


def _sale_paper(ctx: OperationContext, detail: SaleOut, *, duplicate: bool, key: str, at_checkout: bool) -> dict:
    """The receipt (or the full invoice) of the sale ``detail`` to the receipt printer's queue, a ticket with the code
    its customer asks for the full invoice with. ``at_checkout``: the print by itself of the charge — it follows the
    printing settings, and the drawer opens only when cash came in. A fiscal document still pending never prints as if
    issued: the screen's paper says it is pending. ``_Unprintable`` when it is not queued."""
    if detail.invoice_status == FiscalStatus.PENDING:
        raise _Unprintable("sale.document_pending", DOCUMENT_PENDING)
    record = _fiscal_record(ctx, detail)
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
        document.update(paper.cashier(cashier_name(detail.created_by)))
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
    printed = _queue_paper(ctx, request)
    if not printed["queued"]:
        raise _Unprintable("sale.no_printer", NO_PRINTER_FOR_THE_SALE)
    return printed


def _print_sale(ctx: OperationContext, detail: SaleOut, *, duplicate: bool, key: str, at_checkout: bool = False) -> dict:
    """``_sale_paper`` for the charge, which its paper never stops: not queued, the device prints the screen's paper."""
    try:
        return _sale_paper(ctx, detail, duplicate=duplicate, key=key, at_checkout=at_checkout)
    except _Unprintable:
        return dict(NOT_QUEUED)


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
        "the sale's id or number. With no receipt printer for it, its fiscal document still pending or its VeriFactu "
        "record unreadable, it fails and says why: nothing was printed. When the answer says no device that prints "
        "that printer is on, say it stays in that printer's queue until a device set up in Printing › Devices prints "
        "it, never that it was printed. It creates no sale nor fiscal document.",
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
    sale = visible_sale(ctx, data.sale_id, data.sale)
    with translation.override(ctx.language):
        detail = SaleOut.model_validate(sale_detail(sale))
    key = f"sale-{sale.id}-print-{uuid.uuid7()}"
    try:
        return _sale_paper(ctx, detail, duplicate=data.duplicate, key=key, at_checkout=False)
    except _Unprintable as unprintable:
        raise unprintable.refusal(ctx) from None


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
        "receipt printer. Each call prints one. With no receipt printer for it, it fails and says why: nothing was "
        "printed. When the answer says no device that prints that printer is on, say it stays in that printer's queue "
        "until a device set up in Printing › Devices prints it, never that it was printed. Once queued, its table shows "
        "«Bill requested» on the floor plan until the check is charged in full.",
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
    printed = _queue_paper(
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
    if not printed["queued"]:
        raise _Unprintable("sale.no_printer", NO_PRINTER_FOR_THE_BILL).refusal(ctx)
    return printed


@operation(
    "sale.order.note_bill",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.view_sale",
    input=OrderRefIn,
    output=BillNoteOut,
    expose_api=True,
    ai=INTERNAL,
)
def note_bill(ctx: OperationContext, data: OrderRefIn) -> dict:
    """The screen printed an open check's bill on the device, as no receipt printer took it: the check notes it as the
    printer's bill does (TABLE-F34). The assistant prints nothing by itself, so it is not one of its tools."""
    order = _still_open(data.order_id)
    _note_bill_requested(ctx, order)
    return {"order_id": order.id, "bill_printed_at": order.bill_printed_at}
