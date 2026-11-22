"""Schemas of the vouchers a customer could pay a line of the till with."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import model_validator

from apps.service.schemas.fields import SAY_WHICH_SERVICE, Page, PageIn, Said, _named

SAY_WHOSE_VOUCHERS = _("Say whose vouchers: the customer's id, name or phone.")

#: Why a voucher is the one the till spends first (only on the first option).
TenderReason = Literal[
    "",
    "only_option",
    "finite_before_unlimited",
    "expires_first",
    "already_started",
    "fewest_sessions_left",
    "oldest_voucher",
    "stable_order",
]


class TenderOptionsIn(PageIn):
    customer_id: UUID | None = Field(
        None, description="The customer whose vouchers pay the line, by id."
    )
    customer: Said | None = Field(
        None, description="The customer, by name or phone, when the id is not known."
    )
    service_id: UUID | None = Field(
        None, description="The service of the line to pay, by id."
    )
    service: Said | None = Field(None, description="The service, by name.")

    @model_validator(mode="after")
    def _said(self):
        _named(self.customer_id, self.customer, SAY_WHOSE_VOUCHERS)
        _named(self.service_id, self.service, SAY_WHICH_SERVICE)
        return self


class TenderOptionOut(Schema):
    grant_id: UUID = Field(description="The voucher sold (the purchase) that would pay.")
    package_id: UUID
    package_name: str
    granted_at: datetime
    max_uses: int | None = Field(description="Sessions it gives, adjustments included; null = unlimited.")
    used: int = Field(description="Sessions spent or held now.")
    remaining_before: int | None = Field(description="Sessions left now; null = unlimited.")
    remaining_after: int | None = Field(description="Sessions left after this one; null = unlimited.")
    is_unlimited: bool
    expires_at: datetime | None
    is_default: bool = Field(description="The one the till spends first.")
    default_reason: TenderReason = Field(description="Why it goes first; empty on the others.")
    candidate_count: int = Field(description="How many vouchers can pay this line.")


TenderOptionPage = Page[TenderOptionOut]
