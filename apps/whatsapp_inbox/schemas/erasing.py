"""Schemas of erasing a conversation and of asking erplora.com to forget its number."""

from uuid import UUID

from ninja import Field, Schema

from base.sensitive import CUSTOMER_CONTACT


class ErasedOut(Schema):
    id: UUID = Field(description="The erased conversation.")


class ClaimErasureOut(Schema):
    claimed: bool = Field(description="Whether erplora.com still has to forget it (and nobody else is asking).")
    phone: str | None = Field(None, description="The number erplora.com has to forget.", json_schema_extra=CUSTOMER_CONTACT)
    wa_message_ids: list[str] = Field(default_factory=list, description="The WhatsApp ids of its messages.")


class RecordErasureIn(Schema):
    id: UUID = Field(description="The erased conversation.")
    confirmed: bool = Field(description="Whether erplora.com confirmed it forgot the number.")
