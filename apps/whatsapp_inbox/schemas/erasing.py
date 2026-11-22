"""Schemas of erasing a conversation and of asking erplora.com to forget its number."""

from uuid import UUID

from ninja import Field, Schema


class ErasedOut(Schema):
    id: UUID = Field(description="The erased conversation.")


class ClaimErasureOut(Schema):
    claimed: bool = Field(description="Whether erplora.com still has to forget it (and nobody else is asking).")
    phone: str = Field("", description="The number erplora.com has to forget.")
    wa_message_ids: list[str] = Field(default_factory=list, description="The WhatsApp ids of its messages.")


class RecordErasureIn(Schema):
    id: UUID = Field(description="The erased conversation.")
    confirmed: bool = Field(description="Whether erplora.com confirmed it forgot the number.")
