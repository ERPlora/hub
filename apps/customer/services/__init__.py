"""Write operations of the customer app: one operation = one transaction, with its event in the outbox.

Writes on a card lock its row first, so two writes on the same card never interleave. Every write of
a phone goes through ``apps.customer.phones`` (E.164 or a refusal); consent is only written by its two
commands; events carry ids only.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    cards as cards,
    importing as importing,
    memberships as memberships,
    deleting as deleting,
    recovery as recovery,
    merging as merging,
    erasing as erasing,
    activity as activity,
    consent as consent,
    health as health,
    orders as orders,
    purchases as purchases,
    groups as groups,
    tags as tags,
    fields as fields,
    writes as writes,
    field_values as field_values,
    assistant_cards as assistant_cards,
)
