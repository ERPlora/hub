"""Schemas of the inbox's reactions to Customers' events."""

from uuid import UUID

from ninja import Field, Schema


class CustomerEventIn(Schema):
    id: UUID = Field(description="The customer card the event is about.")


class MergedEventIn(Schema):
    id: UUID = Field(description="The card that stays.")
    absorbed_id: UUID = Field(description="The duplicate merged into it.")


class ReactionOut(Schema):
    count: int = Field(description="How many conversations changed.")
