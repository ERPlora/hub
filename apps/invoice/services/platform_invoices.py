"""ERPlora's own invoices (INVOICE-F23), issued on its platform hub as the SaaS posts them, with the SaaS's number.
"""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import operation

from apps.invoice import platform
from apps.invoice.models import Invoice, InvoiceSeries
from apps.invoice.queries import find_platform_invoice, platform_answer
from apps.invoice.schemas.platform import PlatformInvoiceIn, PlatformInvoiceOut
from apps.invoice.services.issuer import _configured_issuer, _issuer_copy
from apps.invoice.services.issuing import _issue, _settle_rectified
from apps.invoice.services.numbering import NUMBER_TAKEN
from apps.invoice.services.writes import actor

PLATFORM_ORIGINAL_UNKNOWN = _(
    "The invoice this credit note rectifies (%(number)s) was never issued here: it has to arrive first."
)


#: The SaaS's number (``ERP-2026-00123``): the platform hub's series prints the same, though it never counts one.
PLATFORM_FORMAT = "{prefix}-{year}-{seq:05d}"


PLATFORM_SERIES_TYPES = {"ERP": "F1", "ERPR": "R1"}


def _platform_series(ctx: OperationContext, code: str, year: int) -> InvoiceSeries:
    """The series ``code`` of ``year``, born on first use with the SaaS's format, and its row locked until the
    COMMIT: two deliveries of the same invoice queue here, and the second finds what the first wrote."""
    InvoiceSeries.objects.bulk_create(
        [
            InvoiceSeries(
                code=code,
                year=year,
                name="ERPlora",
                invoice_type=PLATFORM_SERIES_TYPES[code],
                prefix=code,
                format=PLATFORM_FORMAT,
                created_by=actor(ctx),
            )
        ],
        ignore_conflicts=True,
    )
    return InvoiceSeries.objects.select_for_update().get(code=code, year=year)


def _platform_refusal(refused: platform.PlatformBodyRefused) -> Exception:
    if refused.code == "invoice.platform_recipient_required":
        return Conflict(refused.message, code=refused.code)
    if refused.code == "invoice.platform_original_unknown":
        return NotFound(refused.message, code=refused.code)
    return InvalidPayload(refused.message, code=refused.code)


@operation(
    "invoice.invoice.issue_platform",
    kind="command",
    # Declared by no role: only the system context (``*``) holds it; /internal/platform/invoices calls it.
    permission="invoice.issue_platform",
    input=PlatformInvoiceIn,
    output=PlatformInvoiceOut,
    ai={
        "description": "System only: ERPlora's platform hub issues an invoice of ERPlora to a customer as the SaaS posts "
        "it (its number, date, payer, lines and tax treatment), with its VeriFactu record in the same transaction. "
        "Posting the same invoice again answers what it has.",
        "risk": "high",
    },
)
def issue_platform(ctx: OperationContext, data: PlatformInvoiceIn) -> dict:
    existing = find_platform_invoice(data.id)
    if existing is not None:
        return platform_answer(ctx, existing, already=True)
    body = data.model_dump(mode="json")
    issued_on = data.issued_on
    series = _platform_series(ctx, data.series, issued_on.year)
    # A second delivery waited for the series' lock: it answers what the first issued.
    existing = find_platform_invoice(data.id)
    if existing is not None:
        return platform_answer(ctx, existing, already=True)
    original = None
    if data.rectifies is not None:
        original = find_platform_invoice(data.rectifies.id, lock=True)
        if original is None:
            message = str(PLATFORM_ORIGINAL_UNKNOWN) % {"number": data.rectifies.number}
            raise NotFound(message, code="invoice.platform_original_unknown")
    try:
        fields = platform.to_invoice_fields(
            body,
            issuer=_issuer_copy(_configured_issuer()),
            original_type=original.invoice_type if original is not None else None,
        )
    except platform.PlatformBodyRefused as refused:
        raise _platform_refusal(refused) from None
    values = fields["invoice"]
    if Invoice.objects.filter(series_code=values["series_code"], number=values["number"]).exists():
        raise Conflict(
            str(NUMBER_TAKEN) % {"number": values["number"], "code": values["series_code"]},
            code="invoice.number_taken",
        )
    links = {"rectifies": original} if original is not None else {}
    invoice = _issue(
        ctx,
        series=series,
        invoice_type=values["invoice_type"],
        entries=values["tax_breakdown"],
        lines=fields["lines"],
        tolerance=fields["tolerance"],
        recipient={key: values[key] for key in values if key.startswith("customer_")},
        issuer={key: values[key] for key in values if key.startswith("issuer_")},
        operation_date=values["operation_date"],
        source_type=Invoice.Source.RECTIFICATION if original is not None else Invoice.Source.MANUAL,
        numbered=(values["sequence"], values["number"]),
        issue_date=values["issue_date"],
        description=values["description"],
        notes=values["notes"],
        currency=values["currency"],
        rectification_kind=values["rectification_kind"],
        platform_ref=data.id,
        language=data.language,
        **links,
    )
    if original is not None:
        _settle_rectified(ctx, original, invoice)
    return platform_answer(ctx, invoice)
