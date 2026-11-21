"""Schemas of what the History of the runs forgets when a customer's card is erased (``flow.customer.erase``)."""

from uuid import UUID

from ninja import Field, Schema
from pydantic import ConfigDict


class CustomerErasedIn(Schema):
    """Customers' notice of an erased card (``customer.customer.erased``, CUSTOMER-F16), as the relay hands it over:
    what this app reads of it (the rest is ignored)."""

    model_config = ConfigDict(extra="ignore")

    id: UUID = Field(description="The customer's card whose personal data were erased.")


class ChangedOut(Schema):
    changed: int = Field(description="How many runs the reaction cancelled or made forget what their steps read.")
