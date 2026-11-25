"""When an invoice is overdue (INVOICE-F16): issued, not paid, and its due date has passed on the business's clock. It is
said of an invoice and asked of the list, never kept: an overdue invoice stays issued until it is paid or rectified. A
ticket replaced by a full invoice is not: what is owed is the invoice that replaced it."""

from django.db.models import Q

from apps.invoice.models import Invoice
from apps.tax.queries.jurisdiction import business_today

#: What the list's status filter takes for them, beside the statuses an invoice keeps.
OVERDUE = "overdue"


def is_overdue(invoice: Invoice, *, substituted: bool) -> bool:
    return (
        invoice.due_date is not None
        and invoice.status == Invoice.Status.ISSUED
        and not substituted
        and invoice.due_date < business_today()
    )


def overdue() -> Q:
    """The overdue invoices, to filter by."""
    return Q(status=Invoice.Status.ISSUED, due_date__lt=business_today(), substitutions__isnull=True)
