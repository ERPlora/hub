"""ERPlora's own invoices on its platform hub (INVOICE-F23): how each one stands, its A4 document and whether the
platform hub can issue them now.
"""

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, NotFound
from live.operations import UnknownOperation, operation
from live.operations import get as get_operation

from apps.invoice.models import Invoice, Issuer
from apps.invoice.queries.documents import VERIFACTU_BY_INVOICE, render_document
from apps.invoice.schemas.platform import (
    PlatformDocumentOut,
    PlatformHealthIn,
    PlatformHealthOut,
    PlatformInvoiceOut,
    PlatformRefIn,
)

PLATFORM_UNKNOWN = _("This ERPlora invoice was never issued here.")
PLATFORM_ISSUER_MISSING = _("The platform hub has no issuer: run create_platform_hub.")
PLATFORM_VERIFACTU_MISSING = _("VeriFactu does not answer in the platform hub.")
PLATFORM_REAL_FILING_CLOSED = _(
    "Real filing with the AEAT is closed on this server: ERPlora's invoices would not reach it."
)
VERIFACTU_RECORD = "verifactu.record.get"
VERIFACTU_CONFIG = "verifactu.config.get"
#: The record's statuses the SaaS reads as «issued»: sealed, on its way to the AEAT.
ON_ITS_WAY = ("pending", "sent")
#: What the AEAT registered: only then does the document print the QR, as the old SaaS did.
IN_THE_AEAT = ("accepted", "accepted_with_errors")


def find_platform_invoice(platform_ref, *, lock: bool = False) -> Invoice | None:
    """ERPlora's invoice the SaaS keys by ``platform_ref``, or ``None``."""
    queryset = Invoice.objects.select_for_update() if lock else Invoice.objects
    return queryset.filter(platform_ref=platform_ref).first()


def _platform_invoice(platform_ref) -> Invoice:
    invoice = find_platform_invoice(platform_ref)
    if invoice is None:
        raise NotFound(str(PLATFORM_UNKNOWN), code="invoice.platform_unknown")
    return invoice


def _ask_verifactu(ctx: OperationContext, name: str, data: dict):
    """VeriFactu's answer to ``name`` (asked by name: Invoicing never imports it), or ``None`` without VeriFactu."""
    try:
        op = get_operation(name)
        return op(ctx, op.input.model_validate(data))
    except (UnknownOperation, AppInactive):
        return None


def record_of(ctx: OperationContext, invoice: Invoice):
    answer = _ask_verifactu(ctx, VERIFACTU_BY_INVOICE, {"invoice_id": str(invoice.id)})
    return answer.record if answer is not None else None


def platform_answer(ctx: OperationContext, invoice: Invoice, *, already: bool = False) -> dict:
    """What the SaaS hears of one of its invoices: ``issuing`` without a record yet, ``issued`` while its record is
    on its way to the AEAT, else the AEAT's answer (with its code and message when it found a flaw); its QR link."""
    record = record_of(ctx, invoice)
    if record is None:
        return {"status": "issuing", "qr": "", "error": None, "already": already}
    status = "issued" if record.status in ON_ITS_WAY else record.status
    error = None
    if status in ("rejected", "accepted_with_errors"):
        full = _ask_verifactu(ctx, VERIFACTU_RECORD, {"record_id": str(record.id)})
        error = {"code": full.aeat_code, "message": full.aeat_message}
    return {"status": status, "qr": record.qr_url, "error": error, "already": already}


@operation(
    "invoice.invoice.platform_status",
    kind="query",
    permission="invoice.issue_platform",
    input=PlatformRefIn,
    output=PlatformInvoiceOut,
    ai={
        "description": "System only: how an invoice of ERPlora stands in its platform hub (by the SaaS's id): issuing, "
        "issued, or what the AEAT answered, with its QR link."
    },
)
def platform_status(ctx: OperationContext, data: PlatformRefIn) -> dict:
    return platform_answer(ctx, _platform_invoice(data.id))


@operation(
    "invoice.invoice.platform_document",
    kind="query",
    permission="invoice.issue_platform",
    input=PlatformRefIn,
    output=PlatformDocumentOut,
    ai={
        "description": "System only: the A4 document of an invoice of ERPlora (by the SaaS's id), in its own language, "
        "with VeriFactu's QR once the AEAT registered it."
    },
)
def platform_document(ctx: OperationContext, data: PlatformRefIn) -> dict:
    invoice = _platform_invoice(data.id)
    record = record_of(ctx, invoice)
    qr = (
        {"url": record.qr_url, "svg": record.qr_svg}
        if record is not None and record.status in IN_THE_AEAT
        else None
    )
    with translation.override(invoice.language or ctx.language):
        html = render_document(invoice, qr=qr)
    return {"invoice_id": invoice.id, "number": invoice.number, "html": html}


@operation(
    "invoice.invoice.platform_health",
    kind="query",
    permission="invoice.issue_platform",
    input=PlatformHealthIn,
    output=PlatformHealthOut,
    ai={
        "description": "System only: whether the platform hub can issue ERPlora's invoices now (its issuer is set, "
        "VeriFactu answers and, in prod, real filing with the AEAT is open); what is missing otherwise."
    },
)
def platform_health(ctx: OperationContext, data: PlatformHealthIn) -> dict:
    issuer = Issuer.objects.first()
    if issuer is None or not issuer.configured:
        return {"ready": False, "detail": str(PLATFORM_ISSUER_MISSING)}
    verifactu = _ask_verifactu(ctx, VERIFACTU_CONFIG, {})
    if verifactu is None:
        return {"ready": False, "detail": str(PLATFORM_VERIFACTU_MISSING)}
    # The SaaS charges real money only while this answers ready: in prod, its invoice has to reach the AEAT for real.
    if settings.ERPLORA_ENVIRONMENT == "prod" and not verifactu.production_open:
        return {"ready": False, "detail": str(PLATFORM_REAL_FILING_CLOSED)}
    return {"ready": True, "detail": ""}
