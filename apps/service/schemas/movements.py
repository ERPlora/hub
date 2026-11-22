"""Schemas of the movements of a voucher."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Field, Schema
from pydantic import model_validator

from apps.service.schemas.fields import SAY_WHICH_PACKAGE, Page, PageIn, Said, _named

MovementKind = Literal[
    "held", "consumed", "released", "expired", "returned", "adjusted", "corrected"
]


class MovementListIn(PageIn):
    package_id: UUID | None = Field(
        None, description="The package whose movements are listed, by id."
    )
    package: Said | None = Field(None, description="The package, by name.")

    @model_validator(mode="after")
    def _said(self):
        _named(self.package_id, self.package, SAY_WHICH_PACKAGE)
        return self


class MovementOut(Schema):
    id: UUID
    kind: MovementKind = Field(
        description="held (a session reserved at the till), consumed (a session spent), released, expired, "
        "returned (given back by a refund or a void), adjusted (a courtesy) or corrected (sessions taken)."
    )
    at: datetime
    grant_id: UUID
    customer_id: UUID
    customer_name: str | None
    service_id: UUID | None
    service_name: str | None
    member_id: UUID | None = Field(
        description="The professional who did a session; null = nobody said (and on an adjustment)."
    )
    member_name: str | None
    sale_id: UUID | None
    appointment_id: UUID | None
    note: str
    actor: str
    uses_delta: int
    days_delta: int
    reason: str


MovementPage = Page[MovementOut]
