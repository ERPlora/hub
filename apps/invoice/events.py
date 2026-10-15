"""Events of the invoice app (``invoice.<entity>.<fact>``) and its reactions to the Sales app's events.

services.py records them in the outbox, in the command's transaction; live.py names the ones that re-run
each live query. Each event carries only what the WORKBOOK's «Lo que avisa» lists. VeriFactu (which
requires invoice) registers every ``invoice.invoice.issued``.

Reactions: a charged sale is invoiced, a refund and a void are rectified, each through an operation of
this app run as the system, in its own transaction. The outbox relay (phase 2, in the worker) hands each
delivered event to ``react``; the operations are idempotent (one invoice per sale, one rectification per
refund and per void), and a refund or a void that comes before its sale's invoice is refused so that the
relay retries it (``invoice.sale_not_invoiced``).
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

INVOICE_ISSUED = "invoice.invoice.issued"
INVOICE_RECTIFIED = "invoice.invoice.rectified"
INVOICE_PAID = "invoice.invoice.paid"
SERIES_CREATED = "invoice.series.created"
SERIES_UPDATED = "invoice.series.updated"
ISSUER_UPDATED = "invoice.issuer.updated"

ALL = [
    INVOICE_ISSUED,
    INVOICE_RECTIFIED,
    INVOICE_PAID,
    SERIES_CREATED,
    SERIES_UPDATED,
    ISSUER_UPDATED,
]
#: Every event that changes what a document says (lists, detail, the sale's document).
INVOICE_EVENTS = [INVOICE_ISSUED, INVOICE_RECTIFIED, INVOICE_PAID]
#: Every event that changes a series or its counter.
SERIES_EVENTS = [SERIES_CREATED, SERIES_UPDATED, INVOICE_ISSUED]

# The Sales app's events (its WORKBOOK fixes their payload).
SALE_COMPLETED = "sale.sale.completed"
SALE_REFUNDED = "sale.sale.refunded"
SALE_VOIDED = "sale.sale.voided"

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {
    SALE_COMPLETED: "invoice.invoice.create_from_sale",
    SALE_REFUNDED: "invoice.invoice.rectify_from_refund",
    SALE_VOIDED: "invoice.invoice.rectify_from_void",
}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
