"""The data permissions of base and the marks that apply them to a field of a schema.

A field marked ``Field(json_schema_extra=COSTS)`` reaches only whoever holds ``base.view_costs``: live gives it as null
to anyone else, on every door (``live.sensitive``), so the field admits null.
"""

import dataclasses

from live.context import OperationContext
from live.sensitive import REQUIRES

VIEW_COSTS = "base.view_costs"
VIEW_CUSTOMER_CONTACT = "base.view_customer_contact"
VIEW_TEAM_CONTACT = "base.view_team_contact"
VIEW_BUSINESS_TOTALS = "base.view_business_totals"

#: What a product or a service costs the business, and what follows from it (margin, stock value).
COSTS = {REQUIRES: VIEW_COSTS}
#: A customer's email and phone.
CUSTOMER_CONTACT = {REQUIRES: VIEW_CUSTOMER_CONTACT}
#: A colleague's email and phone.
TEAM_CONTACT = {REQUIRES: VIEW_TEAM_CONTACT}
#: The figures of the whole business, beyond one's own work.
BUSINESS_TOTALS = {REQUIRES: VIEW_BUSINESS_TOTALS}

#: Every data permission of base. An API key carries them all: only the owner and an administrator make keys, and they
#: see every data of the business, so their keys see it too.
DATA_PERMISSIONS = frozenset({VIEW_COSTS, VIEW_CUSTOMER_CONTACT, VIEW_TEAM_CONTACT, VIEW_BUSINESS_TOTALS})


def recording_costs(ctx: OperationContext) -> OperationContext:
    """``ctx`` also reading the costs, for a write that keeps what something costs in a record of its own and never
    answers it: a sale's line keeps the cost of what it sells, to value its comps, whoever sells it."""
    return dataclasses.replace(ctx, permissions=ctx.permissions | {VIEW_COSTS})
