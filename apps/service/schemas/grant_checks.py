"""Schemas of asking first whether a voucher sold may be voided, adjusted or spent."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.service.schemas.fields import ByIdIn, Said


class VoidCheckOut(Schema):
    id: UUID
    voidable: bool
    reason: Literal["", "already_voided", "in_use"]
    used: int


class AdjustCheckOut(Schema):
    id: UUID
    can_add_uses: bool = Field(
        description="It has a limit of sessions to add to or take from."
    )
    can_extend: bool = Field(description="It has an expiry to extend.")
    uses_left: int | None
    expires_at: datetime | None
    reason: Literal["", "already_voided"]


class RedeemCheckIn(ByIdIn):
    service_id: UUID | None = Field(None, description="The service to perform, by id.")
    service: Said | None = Field(None, description="The service to perform, by name.")


class RedeemCheckOut(Schema):
    id: UUID
    redeemable: bool
    reason: Literal["", "voided", "expired", "no_uses_left", "does_not_cover_service"]
    remaining: int | None
