"""The reactions to other apps' events: what this app reads of their payloads and what a reaction answers."""

from uuid import UUID

from ninja import Field, Schema
from pydantic import ConfigDict


class Payload(Schema):
    """Another app's event payload: what this app reads of it (the rest is ignored)."""

    model_config = ConfigDict(extra="ignore")


class CustomerEventIn(Payload):
    id: UUID = Field(description="The customer's card.")


class ReactionOut(Schema):
    changed: int = Field(description="How many rows the reaction changed.")
