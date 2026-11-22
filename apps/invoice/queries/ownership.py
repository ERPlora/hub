"""Whose an invoice is (INVOICE-F16 to INVOICE-F20): whoever issued it, and whoever its sale is (``SALES``), so a
sale's ticket, its full invoice and its rectifying ones follow the sale. Without «See all invoices» a person lists,
opens, prints and touches only theirs."""

from django.db.models import Q

from apps.invoice.models import Invoice
from apps.sale.queries.ownership import SALES
from base.queries.ownership import Owned

INVOICES = Owned(
    Invoice,
    all_permission="invoice.view_all_invoices",
    mine=lambda person: Q(created_by=person.username) | Q(source_sale__in=SALES.theirs(person)),
)
