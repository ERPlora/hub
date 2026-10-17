"""Live queries of the invoice app and the events that re-run them after the COMMIT.

A document changes when one is issued, rectified (its status, what is left) or paid; a series and its next
number change when one is created, updated or numbers a document; the book and the gaps, when a document is
issued; the issuer, when it is saved or received; what a typed line starts with, when the business's territory or
a rule of Taxes changes.
"""

from live.live_registry import live

from apps.invoice import events as E
from apps.tax.events import RULE_EVENTS

live("invoice.invoice.list", on=E.INVOICE_EVENTS)
live("invoice.invoice.get", on=E.INVOICE_EVENTS)
live("invoice.invoice.by_source", on=E.INVOICE_EVENTS)
live("invoice.invoice.document", on=E.INVOICE_EVENTS)
# What a typed line starts with follows the business's territory and Taxes' rules (TAX-F11).
live("invoice.invoice.line_defaults", on=RULE_EVENTS)
live("invoice.series.list", on=E.SERIES_EVENTS)
live("invoice.series.peek_next", on=E.SERIES_EVENTS)
live("invoice.numbering.status", on=E.SERIES_EVENTS)
live("invoice.numbering.gaps", on=[E.INVOICE_ISSUED])
live("invoice.numbering.allocations", on=[E.INVOICE_ISSUED])
live("invoice.issuer.get", on=[E.ISSUER_UPDATED])
