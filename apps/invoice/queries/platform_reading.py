"""How ERPlora's own business reads an invoice erplora.com issued (INVOICE-F23). It is kept like one made by hand and not paid
yet, and it is neither: erplora.com only sends it once its customer has paid. What is kept stays as it is; this is what is
said of it.
"""

from django.db.models import Case, F, Q, Value, When

from apps.invoice.models import RECTIFYING_TYPES, Invoice

#: Where it comes from, beside the sources an invoice keeps.
PLATFORM = "platform"

_COLLECTED = Q(platform_ref__isnull=False, status=Invoice.Status.ISSUED) & ~Q(invoice_type__in=RECTIFYING_TYPES)
#: ``status_of`` in the database, to sort by.
SHOWN_STATUS = Case(When(_COLLECTED, then=Value(Invoice.Status.PAID)), default=F("status"))


def source_of(invoice: Invoice) -> str:
    return invoice.source_type if invoice.platform_ref is None else PLATFORM


def status_of(invoice: Invoice) -> str:
    """Its status; paid, if erplora.com issued it and has not credited it whole."""
    collected = invoice.platform_ref is not None and not invoice.is_rectification
    return Invoice.Status.PAID if collected and invoice.status == Invoice.Status.ISSUED else invoice.status


def with_source(source: str) -> Q:
    """The invoices whose ``source_of`` is ``source``, one of the sources an invoice keeps."""
    return Q(source_type=source, platform_ref__isnull=True)


def with_status(status: str) -> Q:
    """The invoices whose ``status_of`` is ``status``."""
    kept = Q(status=status)
    if status == Invoice.Status.PAID:
        return kept | _COLLECTED
    if status == Invoice.Status.ISSUED:
        return kept & ~_COLLECTED
    return kept
