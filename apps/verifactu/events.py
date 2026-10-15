"""Events of the verifactu app (``verifactu.<entity>.<fact>``) and its reaction to Invoicing's.

services.py records them in the outbox, in the command's transaction; live.py names the ones that re-run each
live query. A rejection or an acceptance with errors carries no amounts.

Reaction: an issued invoice (``invoice.invoice.issued``, Invoicing's notice of every F1, F2, F3 and R1–R5) is
sealed as a registration record by ``verifactu.record.create``, run as the system in its own transaction when
the outbox relay (phase 2, in the worker) delivers it. It is the backup: Invoicing asks by name inside its own
transaction (WORKBOOK «Contrato con Facturación»), and the operation is idempotent (one registration per invoice
and environment).
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

RECORD_CREATED = "verifactu.record.created"
RECORD_TRANSMITTED = "verifactu.record.transmitted"
RECORD_REJECTED = "verifactu.record.rejected"
RECORD_ACCEPTED_WITH_ERRORS = "verifactu.record.accepted_with_errors"
CONTINGENCY_PROCESSED = "verifactu.contingency.processed"
CONTINGENCY_RETRIED = "verifactu.contingency.retried"
RECORD_RECONCILED = "verifactu.record.reconciled"
CHAIN_VALIDATED = "verifactu.chain.validated"
CHAIN_RECOVERED = "verifactu.chain.recovered"
AEAT_QUERIED = "verifactu.aeat.queried"
DIAGNOSTIC_RUN = "verifactu.diagnostic.run"
CONFIG_CHANGED = "verifactu.config.changed"

ALL = [
    RECORD_CREATED,
    RECORD_TRANSMITTED,
    RECORD_REJECTED,
    RECORD_ACCEPTED_WITH_ERRORS,
    CONTINGENCY_PROCESSED,
    CONTINGENCY_RETRIED,
    RECORD_RECONCILED,
    CHAIN_VALIDATED,
    CHAIN_RECOVERED,
    AEAT_QUERIED,
    DIAGNOSTIC_RUN,
    CONFIG_CHANGED,
]
#: Every event that changes a record or the queue.
RECORD_EVENTS = [
    RECORD_CREATED,
    RECORD_TRANSMITTED,
    RECORD_REJECTED,
    RECORD_ACCEPTED_WITH_ERRORS,
    CONTINGENCY_PROCESSED,
    CONTINGENCY_RETRIED,
    RECORD_RECONCILED,
]

# Invoicing's notice (its WORKBOOK fixes the payload: invoice_id, number, series, invoice_type…).
INVOICE_ISSUED = "invoice.invoice.issued"

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {INVOICE_ISSUED: "verifactu.record.create"}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
