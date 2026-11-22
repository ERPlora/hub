"""Schemas of the packages: the vouchers of the catalog and their lines."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _, gettext_noop
from ninja import Field, Schema
from pydantic import field_validator, model_validator

from apps.service.schemas.fields import (
    A_SERVICE,
    SAY_WHICH_SERVICE,
    Cents,
    In,
    LongText,
    Name,
    Order,
    PackageRefIn,
    Page,
    PageIn,
    Said,
    _named,
)

#: Lines of one package, as the old module (255).
MAX_LINES = 255
SERVICE_REPEATED = _("A service is repeated in the lines: each service goes once.")

DiscountType = Literal["percentage", "fixed"]
PackageStatus = Literal["active", "archived", "deleted"]
PackageSort = Literal[
    "sort_order",
    "-sort_order",
    "name",
    "-name",
    "fixed_price",
    "-fixed_price",
    "item_count",
    "-item_count",
    "status",
    "-status",
]


class PackageListIn(PageIn):
    search: str | None = Field(None, max_length=200, description="Part of the name.")
    name: str | None = Field(None, max_length=200, description="Part of the name.")
    status: PackageStatus | None = Field(
        None,
        description="active, archived (not sold any more) or deleted (out of the catalog: only the ones somebody "
        "bought). Without it, active and archived.",
    )
    sort: PackageSort = Field(
        "sort_order",
        description="Order (by order, then name); a leading '-' reverses it.",
    )


class PackageLineIn(In):
    service_id: UUID | None = Field(None, description="The service, by id.", json_schema_extra=A_SERVICE)
    service: Said | None = Field(None, description="The service, by name.")
    sessions: int = Field(
        1, ge=1, le=1000, description="Sessions of this service the voucher includes."
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.service_id, self.service, SAY_WHICH_SERVICE)
        return self


class PackageIn(In):
    name: Name = Field(
        description="The voucher's name («Bono 5 cortes»); unique among the live ones."
    )
    description: LongText = Field("", description="Free description.")
    discount_type: DiscountType = Field(
        "percentage", description="percentage or fixed (an amount off)."
    )
    discount_percent_bp: int = Field(
        0,
        ge=0,
        le=10000,
        description="Percent off in basis points (1050 = 10.50 %), for a percentage discount.",
    )
    discount_amount: Cents = Field(
        0, description="Amount off in cents (minor units of the business's currency), for a fixed discount."
    )
    fixed_price: Cents | None = Field(
        None,
        description="Closed price in cents (minor units of the business's currency); none = the sum of its lines minus the discount.",
    )
    validity_days: int | None = Field(
        None,
        ge=1,
        le=36600,
        description="Days it can be spent from the purchase; none = never expires.",
    )
    max_uses: int | None = Field(
        None,
        ge=1,
        le=100000,
        description="Sessions it grants in all; none = unlimited.",
    )
    is_active: bool = Field(True, description="Whether it is sold.")
    is_featured: bool = Field(False, description="Whether it is highlighted.")
    sort_order: Order = Field(0, description="Order in the lists (lowest first).")
    items: list[PackageLineIn] = Field(
        min_length=1,
        max_length=MAX_LINES,
        title=gettext_noop("Services included"),
        description="Its lines: the services it covers, each once.",
    )

    @field_validator("items")
    @classmethod
    def _each_service_once(cls, items: list[PackageLineIn]) -> list[PackageLineIn]:
        keys = [item.service_id or (item.service or "").lower() for item in items]
        if len(set(keys)) != len(keys):
            raise ValueError(str(SERVICE_REPEATED))
        return items


class PackagePatchIn(PackageRefIn):
    """Only the fields sent change; ``null`` removes the closed price, the validity or the uses limit.
    The lines are never changed: delete the package and create a new one."""

    name: Name | None = Field(None, description="New name.")
    description: LongText | None = Field(None, description="New description.")
    discount_type: DiscountType | None = Field(None, description="New discount type.")
    discount_percent_bp: int | None = Field(
        None, ge=0, le=10000, description="New percent off, in basis points."
    )
    discount_amount: Cents | None = Field(None, description="New amount off, in cents (minor units of the business's currency).")
    fixed_price: Cents | None = Field(
        None, description="New closed price in cents (minor units of the business's currency); null removes it."
    )
    validity_days: int | None = Field(
        None, ge=1, le=36600, description="New validity in days; null = never expires."
    )
    max_uses: int | None = Field(
        None, ge=1, le=100000, description="New uses; null = unlimited."
    )
    is_active: bool | None = Field(
        None, description="Sell it (true) or stop selling it (false)."
    )
    is_featured: bool | None = Field(None, description="Whether it is highlighted.")
    sort_order: Order | None = Field(None, description="New order.")


class PackageItemOut(Schema):
    id: UUID
    service_id: UUID
    service_name: str
    service_price: int
    sessions: int
    sort_order: int


class PackageOut(Schema):
    id: UUID
    name: str
    description: str
    discount_type: DiscountType
    discount_percent_bp: int
    discount_amount: int = Field(json_schema_extra={"money": True})
    fixed_price: int | None = Field(json_schema_extra={"money": True})
    validity_days: int | None
    max_uses: int | None
    is_active: bool
    is_featured: bool
    sort_order: int
    status: PackageStatus
    item_count: int
    items: list[PackageItemOut]
    grant_count: int = Field(
        description="How many times it was sold (voided included)."
    )
    created_at: datetime
    updated_at: datetime


PackagePage = Page[PackageOut]
