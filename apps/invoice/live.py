"""Live queries of the invoice app and the events that re-run them after the COMMIT.

A document changes when one is issued, rectified (its status, what is left) or paid; a series and its next
number change when one is created, updated or numbers a document; the book and the gaps, when a document is
issued; a rectification's preview, when a document is issued or rectified or a series changes; its emails, when
one is asked for or ends and when the customer's card changes; the issuer, when it is saved or received; what a typed line starts with, when the business's territory or
a rule of Taxes changes.
"""

from live.live_registry import live

from apps.customer import events as customer
from apps.invoice import events as E
from apps.tax.events import RULE_EVENTS

live("invoice.invoice.list", on=E.INVOICE_EVENTS)
live("invoice.invoice.get", on=E.INVOICE_EVENTS)
live("invoice.invoice.by_source", on=E.INVOICE_EVENTS)
live("invoice.invoice.document", on=E.INVOICE_EVENTS)
# The address proposed is the one on the customer's card.
live(
    "invoice.email.list",
    on=[
        *E.EMAIL_EVENTS,
        customer.CUSTOMER_UPDATED,
        customer.CUSTOMER_MERGED,
        customer.CUSTOMER_DELETED,
        customer.CUSTOMER_ERASED,
        customer.CUSTOMER_RESTORED,
    ],
)
# The rectification's preview: what is left of the invoice and the next number of the rectifying series (INVOICE-F08).
live(
    "invoice.invoice.rectification_preview",
    on=[E.INVOICE_ISSUED, E.INVOICE_RECTIFIED, E.SERIES_CREATED, E.SERIES_UPDATED],
)
# What a typed line starts with follows the business's territory and Taxes' rules (TAX-F11).
live("invoice.invoice.line_defaults", on=RULE_EVENTS)
live("invoice.series.list", on=E.SERIES_EVENTS)
live("invoice.series.peek_next", on=E.SERIES_EVENTS)
live("invoice.numbering.status", on=E.SERIES_EVENTS)
live("invoice.numbering.gaps", on=[E.INVOICE_ISSUED])
live("invoice.numbering.allocations", on=[E.INVOICE_ISSUED])
live("invoice.issuer.get", on=[E.ISSUER_UPDATED])
