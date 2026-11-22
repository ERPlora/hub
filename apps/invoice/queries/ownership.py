"""Whose an invoice is (INVOICE-F16 to INVOICE-F20): whoever issued it and whoever its sale is (``SALES``), and a document
follows its original, as Odoo's rectifying invoice keeps its original's salesperson: the full invoice that replaced a
ticket of theirs and what rectifies either are theirs, whoever issued them. Without «See all invoices» a person lists,
opens, prints and touches only theirs.

Each step reads the one before by a subquery, never through a relation: a lookup through a link that may be empty joins
it, and the lookups that lock a document (mark paid, replace, rectify) cannot lock the empty side of a join."""

from django.db.models import Q

from apps.invoice.models import Invoice
from apps.sale.queries.ownership import SALES
from base.queries.ownership import Owned

ALL_INVOICES = "invoice.view_all_invoices"

#: Where a person's documents start: the ones they issued, and the ones of their sales.
_ISSUED = Owned(
    Invoice,
    all_permission=ALL_INVOICES,
    mine=lambda person: Q(created_by=person.username) | Q(source_sale__in=SALES.theirs(person)),
)
#: Those, and the full invoice that replaced a ticket of theirs.
_REPLACED = Owned(
    Invoice,
    all_permission=ALL_INVOICES,
    mine=lambda person: _ISSUED.mine(person) | Q(substitutes__in=_ISSUED.theirs(person)),
)

INVOICES = Owned(
    Invoice,
    all_permission=ALL_INVOICES,
    mine=lambda person: _REPLACED.mine(person) | Q(rectifies__in=_REPLACED.theirs(person)),
)
