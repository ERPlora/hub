"""Events of the tips app (``tip.<entity>.<fact>``) and its reactions to the events of Sales.

services/ records them in the outbox, in the command's transaction; live.py names the ones that re-run each live query.

Reactions (WORKBOOK «A qué reacciona»): a voided sale (``sale.sale.voided``) and a sale refunded whole
(``sale.sale.refunded`` with ``fully_refunded``) void their tips, since the customer gets back what they paid, tip
included; each through an operation of this app run as the system, in its own transaction. The worker's outbox relay
hands each delivered event to ``react``; a repeated delivery changes nothing.
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

SETTINGS_UPDATED = "tip.settings.updated"
TIP_ADDED = "tip.tip.added"
TIP_ADJUSTED = "tip.tip.adjusted"
TIP_VOIDED = "tip.tip.voided"

ALL = [SETTINGS_UPDATED, TIP_ADDED, TIP_ADJUSTED, TIP_VOIDED]
TIP_EVENTS = [TIP_ADDED, TIP_ADJUSTED, TIP_VOIDED]

#: The amounts its events bring, in cents of the business's currency: an automation says them as money.
AMOUNTS = frozenset({"amount", "before.amount", "after.amount"})

SALE_VOIDED = "sale.sale.voided"
SALE_REFUNDED = "sale.sale.refunded"
# Sales' payment methods are the ones a tip suggestion is set for.
PAYMENT_METHOD_CREATED = "sale.payment_method.created"
SALE_SETTINGS_UPDATED = "sale.settings.updated"

#: Time clock's working days, which the report by shift follows (no reaction: it only reads them again).
SHIFT_EVENTS = ["attendance.record.clocked_in", "attendance.record.clocked_out", "attendance.record.corrected"]

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {SALE_VOIDED: "tip.sale.void", SALE_REFUNDED: "tip.sale.refund"}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
