"""Schemas of the vouchers sold: selling one, voiding, adjusting and spending it."""

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import field_validator, model_validator

from apps.service.schemas.fields import (
    AN_APPOINTMENT,
    A_CUSTOMER,
    A_GRANT,
    A_MEMBER,
    A_PACKAGE,
    A_SALE,
    A_SALE_LINE,
    A_SERVICE,
    SAY_WHICH_PACKAGE,
    VOUCHER_SOLD,
    ByIdIn,
    Cents,
    In,
    Note,
    Page,
    PageIn,
    Said,
    _named,
)

SAY_WHICH_CUSTOMER = _(
    "Pick the customer this voucher belongs to: a voucher with no owner cannot be redeemed."
)
VOID_REASON_REQUIRED = _(
    "Say why this voucher is being voided: the reason stays on its record."
)
ADJUST_REASON_REQUIRED = _(
    "Say why this voucher is being adjusted: the reason stays on its record."
)
ADJUST_EMPTY = _("Add or remove at least one session, or add at least one day.")
GRANTED_IN_THE_FUTURE = _("A voucher cannot be bought in the future.")
MOMENT_WITHOUT_ZONE = _("Give the moment with its time zone.")

#: How far ahead of this server's clock a purchase may be dated (the till's clock may run fast).
CLOCK_SKEW = timedelta(minutes=5)

GrantStatus = Literal["active", "voided"]
GrantSource = Literal["manual", "sale"]


class GrantListIn(PageIn):
    package_id: UUID | None = Field(None, description="Only the sales of this package.")
    package: str | None = Field(
        None,
        max_length=200,
        description="Only the sales of the package with this name.",
    )
    customer_id: UUID | None = Field(
        None, description="Only the vouchers of this customer."
    )
    customer: str | None = Field(
        None,
        max_length=200,
        description="Only the vouchers of the customer with this name, phone or email.",
    )
    status: GrantStatus | None = Field(
        None, description="active or voided; without it, both."
    )


class GrantIn(In):
    package_id: UUID | None = Field(None, description="The package sold, by id.", json_schema_extra=A_PACKAGE)
    package: Said | None = Field(None, description="The package sold, by name.")
    customer_id: UUID | None = Field(
        None, description="The customer who owns it (Customers), by id.", json_schema_extra=A_CUSTOMER
    )
    customer: Said | None = Field(
        None, description="The customer who owns it, by name, phone or email."
    )
    amount: Cents = Field(0, description="Amount paid for it, VAT included, in cents (minor units of the business's currency).")
    net_amount: Cents = Field(0, description="Taxable base of that amount, in cents (minor units of the business's currency).")
    tax_amount: Cents = Field(0, description="VAT of that amount, in cents (minor units of the business's currency).")
    sale_id: UUID | None = Field(
        None,
        description="The sale that charged it (Sales), if it went through the till: its line stops counting for who "
        "sold it and each session counts for who does it. A voucher with an amount that does not say it counts for "
        "nobody as its sessions are done.",
        json_schema_extra=A_SALE,
    )
    sale_line_id: UUID | None = Field(
        None,
        description="The line of that sale that charged it; only needed when the sale charged several (Sales).",
        json_schema_extra=A_SALE_LINE,
    )
    granted_at: datetime | None = Field(
        None,
        description="When it was bought, with its time zone; now by default, never ahead. Its expiry counts from "
        "it (extending a voucher is service.grant.adjust).",
    )
    note: Note = Field("", description="A free note.")

    @field_validator("granted_at")
    @classmethod
    def _not_ahead(cls, moment: datetime | None) -> datetime | None:
        if moment is None:
            return None
        if moment.tzinfo is None:
            raise ValueError(str(MOMENT_WITHOUT_ZONE))
        if moment > datetime.now(moment.tzinfo) + CLOCK_SKEW:
            raise ValueError(str(GRANTED_IN_THE_FUTURE))
        return moment

    @model_validator(mode="after")
    def _said(self):
        _named(self.package_id, self.package, SAY_WHICH_PACKAGE)
        _named(self.customer_id, self.customer, SAY_WHICH_CUSTOMER)
        return self


class GrantOut(Schema):
    id: UUID
    package_id: UUID
    package_name: str
    customer_id: UUID
    customer_name: str | None = Field(
        description="The customer's name; null when the card is gone or may not be read."
    )
    customer_deleted_at: datetime | None = Field(
        description="When the customer's card was deleted or erased."
    )
    granted_at: datetime
    source: GrantSource
    sale_id: UUID | None
    amount: int = Field(json_schema_extra={"money": True})
    net_amount: int = Field(json_schema_extra={"money": True})
    tax_amount: int = Field(json_schema_extra={"money": True})
    note: str
    max_uses: int | None = Field(
        description="Sessions in all: the ones sold plus the adjustments; null = unlimited."
    )
    uses_added: int = Field(description="Sessions given afterwards.")
    uses_removed: int = Field(
        description="Sessions taken afterwards to correct the balance."
    )
    days_added: int = Field(description="Days its expiry was extended.")
    used: int = Field(description="Sessions spent.")
    remaining: int | None = Field(description="Sessions left; null = unlimited.")
    expires_at: datetime | None = Field(description="When it expires; null = never.")
    is_expired: bool
    status: GrantStatus
    voided_at: datetime | None
    voided_by: str
    void_reason: str
    can_void: bool = Field(description="Live and never used: it can be voided.")
    can_adjust: bool = Field(
        description="Live, with a limit of sessions or an expiry: it can be adjusted."
    )


class GrantDetailOut(GrantOut):
    label: str = Field(
        description="How a person tells it apart: the package, its owner if the reader may see customers and the day "
        "it was sold, «5 haircuts · Lucía Pérez · Oct 3, 2026»."
    )


class OrphanOut(Schema):
    id: UUID
    package_id: UUID
    package_name: str
    customer_id: UUID
    customer_deleted_at: datetime
    granted_at: datetime
    amount: int = Field(json_schema_extra={"money": True})
    remaining: int | None
    is_expired: bool


class GrantCreatedOut(GrantOut):
    pass


class GrantRefIn(ByIdIn):
    id: UUID = Field(title=VOUCHER_SOLD, description="The id of the record.", json_schema_extra=A_GRANT)


class VoidIn(GrantRefIn):
    reason: Note = Field(
        description="Why it is voided, in the operator's words; it stays on its record."
    )

    @field_validator("reason")
    @classmethod
    def _said(cls, reason: str) -> str:
        if not reason:
            raise ValueError(str(VOID_REASON_REQUIRED))
        return reason


class AdjustIn(GrantRefIn):
    uses_delta: int = Field(
        0,
        ge=-100,
        le=100,
        description="Sessions added (positive) or taken away (negative); never more than are left.",
    )
    days_delta: int = Field(0, ge=0, le=366, description="Days its expiry moves later.")
    reason: Note = Field(
        description="Why, in the operator's words; it stays in the voucher's movements."
    )

    @field_validator("reason")
    @classmethod
    def _said(cls, reason: str) -> str:
        if not reason:
            raise ValueError(str(ADJUST_REASON_REQUIRED))
        return reason

    @model_validator(mode="after")
    def _moves(self):
        if self.uses_delta == 0 and self.days_delta == 0:
            raise ValueError(str(ADJUST_EMPTY))
        return self


class RedeemIn(GrantRefIn):
    service_id: UUID | None = Field(
        None, description="The service performed, by id; the voucher must cover it.", json_schema_extra=A_SERVICE
    )
    service: Said | None = Field(None, description="The service performed, by name.")
    member_id: UUID | None = Field(
        None,
        description="The professional (Staff) who did it, by id: its value counts in their production.",
        json_schema_extra=A_MEMBER,
    )
    member: Said | None = Field(None, description="The professional (Staff) who did it, by name.")
    appointment_id: UUID | None = Field(
        None, description="The appointment it is spent on (Appointments), if any.", json_schema_extra=AN_APPOINTMENT
    )
    sale_id: UUID | None = Field(
        None, description="The sale it is spent on (Sales), if any.", json_schema_extra=A_SALE
    )
    note: Note = Field("", description="A free note.")


class RedemptionOut(Schema):
    id: UUID
    grant_id: UUID
    service_id: UUID | None
    service_name: str | None
    member_id: UUID | None = Field(description="The professional who did it; null = nobody said.")
    member_name: str | None
    redeemed_at: datetime
    remaining: int | None = Field(
        description="Sessions left after this one; null = unlimited."
    )


GrantPage = Page[GrantOut]
OrphanPage = Page[OrphanOut]
