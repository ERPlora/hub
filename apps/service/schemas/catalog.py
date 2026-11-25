"""Schemas of the services of the catalog: their lists, writing one or several, and what the till reads."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import model_validator

from apps.service.schemas.fields import (
    A_CATEGORY,
    TAX_CATEGORY,
    Buffer,
    Cents,
    Code,
    In,
    LongText,
    Minutes,
    Name,
    Order,
    Page,
    PageIn,
    Said,
    ServiceRefIn,
)
from apps.tax.schemas.references import A_TAX_CATEGORY
from base.sensitive import COSTS

#: Services of one bulk create, as the old module (500).
MAX_BULK = 500
PRICE_RANGE_UPSIDE_DOWN = _("The minimum price cannot be above the maximum price.")

PricingType = Literal["fixed", "hourly", "from", "variable", "free"]
ServiceStatus = Literal["active", "unconfigured", "archived"]
ServiceSort = Literal[
    "name",
    "-name",
    "category_name",
    "-category_name",
    "pricing_type",
    "-pricing_type",
    "price",
    "-price",
    "duration_minutes",
    "-duration_minutes",
    "status",
    "-status",
    "created_at",
    "-created_at",
]


class ServiceListIn(PageIn):
    search: str | None = Field(
        None, max_length=200, description="Part of the name, the category or the SKU."
    )
    name: str | None = Field(None, max_length=200, description="Part of the name.")
    category_id: UUID | None = Field(
        None, description="Only the services of this category."
    )
    category: str | None = Field(
        None,
        max_length=200,
        description="Only the services of the category with this name.",
    )
    pricing_type: PricingType | None = Field(
        None, description="Only this pricing: fixed, hourly, from, variable or free."
    )
    price_min: Cents | None = Field(None, description="Lowest price, in cents (minor units of the business's currency).")
    price_max: Cents | None = Field(None, description="Highest price, in cents (minor units of the business's currency).")
    duration_min: int | None = Field(
        None, ge=0, description="Shortest duration, in minutes."
    )
    duration_max: int | None = Field(
        None, ge=0, description="Longest duration, in minutes."
    )
    status: ServiceStatus | None = Field(
        None,
        description="active (offered, with a tax category), unconfigured (offered, no tax category: cannot be "
        "charged) or archived (no longer offered). Without it, every offered service.",
    )
    sort: ServiceSort = Field("name", description="Order; a leading '-' reverses it.")


class ServiceForSaleIn(PageIn):
    search: str | None = Field(None, max_length=200, description="Part of the name.")
    category_id: UUID | None = Field(
        None, description="Only the services of this category."
    )


class ServiceIn(In):
    """A new service; what it does not say takes the settings (duration, buffers, online booking, tax category)."""

    name: Name = Field(
        description="The service's name, as the diary, the till and the ticket show it."
    )
    tax_category_key: Code | None = Field(
        None,
        title=TAX_CATEGORY,
        description="Key of the tax category (Taxes app) the service is charged with; without it, the settings' "
        "default tax category. Without either, the service is created but cannot be charged.",
        json_schema_extra=A_TAX_CATEGORY,
    )
    pricing_type: PricingType = Field(
        "fixed",
        description="fixed (its price), hourly, from or variable (the till asks the amount, the price is a "
        "suggestion) or free.",
    )
    price: Cents = Field(0, description="Price in cents (minor units of the business's currency).")
    min_price: Cents | None = Field(
        None, description="Lowest price of a 'from' or 'variable' service, in cents (minor units of the business's currency)."
    )
    max_price: Cents | None = Field(
        None, description="Highest price of a 'from' or 'variable' service, in cents (minor units of the business's currency)."
    )
    cost: Cents = Field(0, description="Internal cost in cents (minor units of the business's currency).", json_schema_extra=COSTS)
    duration_minutes: Minutes | None = Field(
        None, description="Duration in minutes; without it, the settings' default."
    )
    buffer_before: Buffer | None = Field(
        None, description="Minutes blocked before it; without it, the settings' buffer."
    )
    buffer_after: Buffer | None = Field(
        None, description="Minutes blocked after it; without it, the settings' buffer."
    )
    max_capacity: int = Field(
        1, ge=1, le=1000, description="How many customers one slot serves."
    )
    category_id: UUID | None = Field(None, description="Its service category, by id.", json_schema_extra=A_CATEGORY)
    category: Said | None = Field(None, description="Its service category, by name.")
    description: LongText = Field("", description="Free description.")
    short_description: LongText = Field("", description="A one-line description.")
    is_bookable: bool = Field(True, description="Whether the diary may book it.")
    requires_confirmation: bool = Field(
        False, description="Whether a booking of it waits for confirmation."
    )
    allow_online_booking: bool | None = Field(
        None,
        description="Whether it may be booked online; without it, the settings' default.",
    )
    sort_order: Order = Field(0, description="Order in the lists (lowest first).")
    is_featured: bool = Field(False, description="Whether it is highlighted.")
    sku: Code = Field("", description="Its own code, if it has one.")
    barcode: Code = Field("", description="Its barcode, if it has one.")
    notes: LongText = Field("", description="Internal notes.")

    @model_validator(mode="after")
    def _range(self):
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError(str(PRICE_RANGE_UPSIDE_DOWN))
        return self


class ServicePatchIn(ServiceRefIn):
    """Only the fields sent change. ``null`` empties the category and the minimum and maximum prices.

    Archiving and restoring are their own operations: ``is_active`` is not a field.
    """

    name: Name | None = Field(None, description="New name.")
    tax_category_key: Code | None = Field(
        None, title=TAX_CATEGORY, description="Key of the new tax category; it cannot be emptied.", json_schema_extra=A_TAX_CATEGORY
    )
    pricing_type: PricingType | None = Field(None, description="New pricing.")
    price: Cents | None = Field(None, description="New price in cents (minor units of the business's currency).")
    min_price: Cents | None = Field(
        None, description="New lowest price in cents (minor units of the business's currency); null removes it."
    )
    max_price: Cents | None = Field(
        None, description="New highest price in cents (minor units of the business's currency); null removes it."
    )
    cost: Cents | None = Field(None, description="New cost in cents (minor units of the business's currency).", json_schema_extra=COSTS)
    duration_minutes: Minutes | None = Field(
        None, description="New duration in minutes."
    )
    buffer_before: Buffer | None = Field(
        None, description="New buffer before, in minutes."
    )
    buffer_after: Buffer | None = Field(
        None, description="New buffer after, in minutes."
    )
    max_capacity: int | None = Field(None, ge=1, le=1000, description="New capacity.")
    category_id: UUID | None = Field(
        None, description="New category by id; null leaves it without a category.", json_schema_extra=A_CATEGORY
    )
    category: Said | None = Field(None, description="New category by name.")
    description: LongText | None = Field(None, description="New description.")
    short_description: LongText | None = Field(
        None, description="New one-line description."
    )
    is_bookable: bool | None = Field(None, description="Whether the diary may book it.")
    requires_confirmation: bool | None = Field(
        None, description="Whether a booking waits for confirmation."
    )
    allow_online_booking: bool | None = Field(
        None, description="Whether it may be booked online."
    )
    sort_order: Order | None = Field(None, description="New order.")
    is_featured: bool | None = Field(None, description="Whether it is highlighted.")
    sku: Code | None = Field(None, description="New code.")
    barcode: Code | None = Field(None, description="New barcode.")
    notes: LongText | None = Field(None, description="New internal notes.")


class ServiceBulkIn(In):
    services: list[ServiceIn] = Field(
        min_length=1,
        max_length=MAX_BULK,
        description="The services to create (up to 500): all of them or none, each one as service.create takes it.",
    )


class ServiceOut(Schema):
    id: UUID
    name: str
    description: str
    short_description: str
    category_id: UUID | None
    category_name: str | None
    pricing_type: PricingType
    price: int = Field(json_schema_extra={"money": True})
    min_price: int | None = Field(json_schema_extra={"money": True})
    max_price: int | None = Field(json_schema_extra={"money": True})
    cost: int | None = Field(description="Internal cost in cents; null for whoever does not see the costs.", json_schema_extra={"money": True, **COSTS})
    duration_minutes: int
    buffer_before: int
    buffer_after: int
    max_capacity: int
    is_bookable: bool
    requires_confirmation: bool
    allow_online_booking: bool
    sort_order: int
    is_featured: bool
    sku: str
    barcode: str
    notes: str
    tax_category_id: UUID | None
    tax_category_key: str | None
    tax_category_name: str | None
    needs_tax_setup: bool = Field(
        description="No live tax category: it cannot be charged until it has one."
    )
    status: ServiceStatus
    is_active: bool
    archived_at: datetime | None
    image: str = Field(
        description="Its image: catalog:<folder>/<name> of the shared library, file:<name> of a photo of its own, "
        "or empty."
    )
    image_url: str = Field(description="Where the Hub serves its image; empty: it has none (show its initials).")
    created_at: datetime
    updated_at: datetime


class ServiceSaleOut(Schema):
    """What the till, the diary and WhatsApp read of an offered service."""

    id: UUID
    name: str
    pricing_type: PricingType
    price: int = Field(json_schema_extra={"money": True})
    min_price: int | None = Field(json_schema_extra={"money": True})
    max_price: int | None = Field(json_schema_extra={"money": True})
    duration_minutes: int
    buffer_before: int
    buffer_after: int
    is_bookable: bool
    allow_online_booking: bool
    category_id: UUID | None
    category_name: str | None
    tax_category_id: UUID | None
    tax_category_key: str | None
    needs_tax_setup: bool
    image: str = Field(
        description="Its image: catalog:<folder>/<name> of the shared library, file:<name> of a photo of its own, "
        "or empty."
    )
    image_url: str = Field(description="Where the Hub serves its image; empty: it has none (show its initials).")


class ServicesOut(Schema):
    created: int = Field(description="How many services were created.")
    ids: list[UUID] = Field(description="Their ids, in the order they were sent.")


class CatalogStatusOut(Schema):
    services: int = Field(description="Offered services.")
    sellable_services: int = Field(
        description="Offered services with a live tax category: the ones that can be charged."
    )
    needs_tax_setup: int = Field(
        description="Offered services without a live tax category."
    )


ServicePage = Page[ServiceOut]
ServiceSalePage = Page[ServiceSaleOut]
