"""Input and output schemas of the service app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. Money travels
in minor units of the business's currency, its country's (cents in euros, whole yen in Japan; integers,
never negative; service-business-currency), and each amount's description says «in cents»: the words the assistant
reads as money (its card paints the amount in the business's currency, its instructions ask the AI for the minor
unit; test_integration_assistant.py). A percentage discount travels in basis points (1050 = 10.50 %). A
service, a category or a package is named by its id or, as a person says it (assistant, voice), by
its name; a professional by their name; a customer by their name, phone or email. Every input refuses
a field it does not declare. An edit changes only the fields it sends; on a field that may be empty
(the category, the closed price…), sending ``null`` empties it.
"""

from datetime import datetime, timedelta
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints, field_validator, model_validator

T = TypeVar("T")

#: Just under ten trillion minor units of the business's currency (ninety-nine billion with two decimals):
#: far above any price, inside a bigint.
MAX_CENTS = 9_999_999_999_999
#: Services of one bulk create, as the old module (500).
MAX_BULK = 500
#: Lines of one package, as the old module (255).
MAX_LINES = 255
#: A service lasts at most a day; a buffer, too.
MAX_MINUTES = 1440

SAY_WHICH_SERVICE = _("Say which service: its id, or its name.")
SAY_WHICH_CATEGORY = _("Say which category: its id, or its name.")
SAY_WHICH_PACKAGE = _("Say which package: its id, or its name.")
SAY_WHICH_MEMBER = _("Say which professional: their id, or their name.")
SAY_WHICH_CUSTOMER = _(
    "Pick the customer this voucher belongs to: a voucher with no owner cannot be redeemed."
)
PRICE_RANGE_UPSIDE_DOWN = _("The minimum price cannot be above the maximum price.")
SERVICE_REPEATED = _("A service is repeated in the lines: each service goes once.")
VOID_REASON_REQUIRED = _(
    "Say why this voucher is being voided: the reason stays on its record."
)
ADJUST_REASON_REQUIRED = _(
    "Say why this voucher is being adjusted: the reason stays on its record."
)
ADJUST_EMPTY = _("Add or remove at least one session, or add at least one day.")
GRANTED_IN_THE_FUTURE = _("A voucher cannot be bought in the future.")
SAY_WHOSE_VOUCHERS = _("Say whose vouchers: the customer's id, name or phone.")
MOMENT_WITHOUT_ZONE = _("Give the moment with its time zone.")
#: How the Services screens name the data the models do not (the assistant's card names each datum by its title).
TAX_CATEGORY = gettext_noop("Tax category")
#: How far ahead of this server's clock a purchase may be dated (the till's clock may run fast).
CLOCK_SKEW = timedelta(minutes=5)

PricingType = Literal["fixed", "hourly", "from", "variable", "free"]
ServiceStatus = Literal["active", "unconfigured", "archived"]
DiscountType = Literal["percentage", "fixed"]
PackageStatus = Literal["active", "archived", "deleted"]
GrantStatus = Literal["active", "voided"]
GrantSource = Literal["manual", "sale"]
SessionStatus = Literal["held", "consumed", "released", "expired", "returned"]
MovementKind = Literal[
    "held", "consumed", "released", "expired", "returned", "adjusted", "corrected"
]
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
CategorySort = Literal[
    "sort_order",
    "-sort_order",
    "name",
    "-name",
    "parent_name",
    "-parent_name",
    "service_count",
    "-service_count",
]
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


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Name = _text(200, 1)
Said = _text(200, 1)
LongText = Annotated[str, StringConstraints(max_length=2000)]
Code = _text(64)
Note = _text(500)
Color = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^#[0-9a-fA-F]{6}$|^$")
]
Icon = _text(80)
Cents = Annotated[int, Field(ge=0, le=MAX_CENTS)]
Minutes = Annotated[int, Field(ge=1, le=MAX_MINUTES)]
Buffer = Annotated[int, Field(ge=0, le=MAX_MINUTES)]
Order = Annotated[int, Field(ge=0, le=1_000_000)]


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


# Pages: every list is paginated, limit ≤ 100.


class PageIn(In):
    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return (1 to 100)."
    )
    offset: int = Field(
        0, ge=0, description="How many rows to skip, to read the next pages."
    )


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="How many rows match, across every page.")
    limit: int = Field(description="The page size asked for.")
    offset: int = Field(description="The rows skipped before this page.")


def _named(value_id, said, message):
    if value_id is None and said is None:
        raise ValueError(str(message))


# References: by id, or as a person says it


class ServiceRefIn(In):
    id: UUID | None = Field(None, description="The service's id.")
    service: Said | None = Field(
        None,
        description="The service's name, when its id is not known (e.g. said aloud).",
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.id, self.service, SAY_WHICH_SERVICE)
        return self


class CategoryRefIn(In):
    id: UUID | None = Field(None, description="The category's id.")
    category: Said | None = Field(
        None, description="The category's name, when its id is not known."
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.id, self.category, SAY_WHICH_CATEGORY)
        return self


class PackageRefIn(In):
    id: UUID | None = Field(None, description="The package's id.")
    package: Said | None = Field(
        None, description="The package's name, when its id is not known."
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.id, self.package, SAY_WHICH_PACKAGE)
        return self


class ByIdIn(In):
    id: UUID = Field(description="The id of the record.")


class NoIn(In):
    pass


# ── Services ──────────────────────────────────────────────────────────────────────────────────


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
    cost: Cents = Field(0, description="Internal cost in cents (minor units of the business's currency).")
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
    category_id: UUID | None = Field(None, description="Its service category, by id.")
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
        None, title=TAX_CATEGORY, description="Key of the new tax category; it cannot be emptied."
    )
    pricing_type: PricingType | None = Field(None, description="New pricing.")
    price: Cents | None = Field(None, description="New price in cents (minor units of the business's currency).")
    min_price: Cents | None = Field(
        None, description="New lowest price in cents (minor units of the business's currency); null removes it."
    )
    max_price: Cents | None = Field(
        None, description="New highest price in cents (minor units of the business's currency); null removes it."
    )
    cost: Cents | None = Field(None, description="New cost in cents (minor units of the business's currency).")
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
        None, description="New category by id; null leaves it without a category."
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
    price: int
    min_price: int | None
    max_price: int | None
    cost: int
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
    created_at: datetime
    updated_at: datetime


class ServiceSaleOut(Schema):
    """What the till, the diary and WhatsApp read of an offered service."""

    id: UUID
    name: str
    pricing_type: PricingType
    price: int
    min_price: int | None
    max_price: int | None
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


# ── Categories ────────────────────────────────────────────────────────────────────────────────


class CategoryListIn(PageIn):
    search: str | None = Field(None, max_length=200, description="Part of the name.")
    parent_id: UUID | None = Field(
        None, description="Only the categories inside this one."
    )
    sort: CategorySort = Field(
        "sort_order",
        description="Order (by order, then name); a leading '-' reverses it.",
    )


class CategoryIn(In):
    name: Name = Field(
        description="The category's name; unique among the live ones, ignoring case."
    )
    description: LongText = Field("", description="Free description.")
    parent_id: UUID | None = Field(
        None, description="The category it goes inside, by id; none = a root category."
    )
    parent: Said | None = Field(
        None, description="The category it goes inside, by name."
    )
    icon: Icon = Field(
        "", description="An Iconify icon name (ion:cut-outline), or empty."
    )
    color: Color = Field("", description="A colour #rrggbb, or empty.")
    sort_order: Order = Field(0, description="Order in the lists (lowest first).")


class CategoryPatchIn(CategoryRefIn):
    """Only the fields sent change; ``parent_id: null`` makes it a root category."""

    name: Name | None = Field(None, description="New name.")
    description: LongText | None = Field(None, description="New description.")
    parent_id: UUID | None = Field(
        None, description="New parent by id; null makes it a root category."
    )
    parent: Said | None = Field(None, description="New parent by name.")
    icon: Icon | None = Field(None, description="New icon.")
    color: Color | None = Field(None, description="New colour.")
    sort_order: Order | None = Field(None, description="New order.")


class CategoryOut(Schema):
    id: UUID
    name: str
    description: str
    parent_id: UUID | None
    parent_name: str | None
    icon: str
    color: str
    sort_order: int
    service_count: int = Field(description="Offered services in it.")
    created_at: datetime
    updated_at: datetime


class DeletedOut(Schema):
    id: UUID


CategoryPage = Page[CategoryOut]


# ── Settings ──────────────────────────────────────────────────────────────────────────────────


class SettingsIn(In):
    """Only the fields sent change."""

    default_duration: Minutes | None = Field(
        None, description="Duration a new service takes, in minutes."
    )
    default_buffer_time: Buffer | None = Field(
        None, description="Buffer before and after a new service, in minutes."
    )
    default_tax_category_key: Code | None = Field(
        None,
        title=gettext_noop("Default tax category"),
        description="Key of the tax category a new service takes; null or empty removes it.",
    )
    show_prices: bool | None = Field(
        None, description="Whether the public booking page shows prices."
    )
    show_duration: bool | None = Field(
        None, description="Whether the public booking page shows durations."
    )
    allow_online_booking: bool | None = Field(
        None, description="Whether a new service may be booked online."
    )


class SettingsOut(Schema):
    default_duration: int
    default_buffer_time: int
    default_tax_category_id: UUID | None
    default_tax_category_key: str | None
    default_tax_category_name: str | None
    show_prices: bool
    show_duration: bool
    allow_online_booking: bool
    updated_at: datetime | None


# ── Who performs each service ─────────────────────────────────────────────────────────────────


class AssignmentListIn(PageIn):
    service_id: UUID | None = Field(
        None, description="Only the professionals of this service."
    )
    service: str | None = Field(
        None,
        max_length=200,
        description="Only the professionals of the service with this name.",
    )
    member_id: UUID | None = Field(
        None, description="Only the services of this professional."
    )
    member: str | None = Field(
        None,
        max_length=200,
        description="Only the services of the professional with this name.",
    )


class EligibleIn(PageIn):
    service_id: UUID | None = Field(None, description="The service, by id.")
    service: Said | None = Field(None, description="The service, by name.")

    @model_validator(mode="after")
    def _said(self):
        _named(self.service_id, self.service, SAY_WHICH_SERVICE)
        return self


class AssignIn(In):
    """Assigning someone who already has the service changes their own duration and price."""

    service_id: UUID | None = Field(None, description="The service, by id.")
    service: Said | None = Field(None, description="The service, by name.")
    member_id: UUID | None = Field(None, description="The professional (Staff), by id.")
    member: Said | None = Field(None, description="The professional (Staff), by name.")
    custom_duration: Minutes | None = Field(
        None, description="Their own duration in minutes; none = the service's."
    )
    custom_price: Cents | None = Field(
        None, description="Their own price in cents (minor units of the business's currency); none = the service's."
    )
    is_primary: bool = Field(
        False, description="Whether it is their main service (one per professional); assigning again without it keeps it."
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.service_id, self.service, SAY_WHICH_SERVICE)
        _named(self.member_id, self.member, SAY_WHICH_MEMBER)
        return self


class AssignmentPatchIn(ByIdIn):
    """Only the fields sent change; ``null`` removes an own duration or price."""

    custom_duration: Minutes | None = Field(
        None, description="Own duration in minutes; null = the service's."
    )
    custom_price: Cents | None = Field(
        None, description="Own price in cents (minor units of the business's currency); null = the service's."
    )
    is_primary: bool | None = Field(
        None, description="Make it (true) or stop it being (false) their main service."
    )
    is_active: bool | None = Field(
        None, description="Switch the assignment on (true) or off (false)."
    )


class MemberReleaseIn(In):
    """The payload of ``staff.member.terminated``."""

    id: UUID = Field(description="The professional who left.")


class AssignmentOut(Schema):
    id: UUID
    service_id: UUID
    service_name: str
    member_id: UUID
    member_name: str
    custom_duration: int | None
    custom_price: int | None
    is_primary: bool
    is_active: bool
    duration: int = Field(
        description="What it lasts with this professional: their own duration or the service's."
    )
    price: int = Field(
        description="What it costs with this professional: their own price or the service's."
    )


class EligibleOut(Schema):
    member_id: UUID
    full_name: str
    color: str
    booking_buffer: int
    custom_duration: int | None
    custom_price: int | None
    is_primary: bool
    duration: int
    price: int


class ReleasedOut(Schema):
    removed: int = Field(description="How many assignments were removed.")


AssignmentPage = Page[AssignmentOut]
EligiblePage = Page[EligibleOut]


# ── Packages (the vouchers of the catalog) ────────────────────────────────────────────────────


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
    service_id: UUID | None = Field(None, description="The service, by id.")
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
    discount_amount: int
    fixed_price: int | None
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


# ── Vouchers sold ─────────────────────────────────────────────────────────────────────────────


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
    package_id: UUID | None = Field(None, description="The package sold, by id.")
    package: Said | None = Field(None, description="The package sold, by name.")
    customer_id: UUID | None = Field(
        None, description="The customer who owns it (Customers), by id."
    )
    customer: Said | None = Field(
        None, description="The customer who owns it, by name, phone or email."
    )
    amount: Cents = Field(0, description="Amount paid for it, VAT included, in cents (minor units of the business's currency).")
    net_amount: Cents = Field(0, description="Taxable base of that amount, in cents (minor units of the business's currency).")
    tax_amount: Cents = Field(0, description="VAT of that amount, in cents (minor units of the business's currency).")
    sale_id: UUID | None = Field(
        None, description="The sale that paid it (Sales), if any."
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
    amount: int
    net_amount: int
    tax_amount: int
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


class OrphanOut(Schema):
    id: UUID
    package_id: UUID
    package_name: str
    customer_id: UUID
    customer_deleted_at: datetime
    granted_at: datetime
    amount: int
    remaining: int | None
    is_expired: bool


class GrantCreatedOut(GrantOut):
    pass


class VoidIn(ByIdIn):
    reason: Note = Field(
        description="Why it is voided, in the operator's words; it stays on its record."
    )

    @field_validator("reason")
    @classmethod
    def _said(cls, reason: str) -> str:
        if not reason:
            raise ValueError(str(VOID_REASON_REQUIRED))
        return reason


class VoidCheckOut(Schema):
    id: UUID
    voidable: bool
    reason: Literal["", "already_voided", "in_use"]
    used: int


class AdjustIn(ByIdIn):
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


class AdjustCheckOut(Schema):
    id: UUID
    can_add_uses: bool = Field(
        description="It has a limit of sessions to add to or take from."
    )
    can_extend: bool = Field(description="It has an expiry to extend.")
    uses_left: int | None
    expires_at: datetime | None
    reason: Literal["", "already_voided"]


class RedeemIn(ByIdIn):
    service_id: UUID | None = Field(
        None, description="The service performed, by id; the voucher must cover it."
    )
    service: Said | None = Field(None, description="The service performed, by name.")
    appointment_id: UUID | None = Field(
        None, description="The appointment it is spent on (Appointments), if any."
    )
    sale_id: UUID | None = Field(
        None, description="The sale it is spent on (Sales), if any."
    )
    note: Note = Field("", description="A free note.")


class RedeemCheckIn(ByIdIn):
    service_id: UUID | None = Field(None, description="The service to perform, by id.")
    service: Said | None = Field(None, description="The service to perform, by name.")


class RedeemCheckOut(Schema):
    id: UUID
    redeemable: bool
    reason: Literal["", "voided", "expired", "no_uses_left", "does_not_cover_service"]
    remaining: int | None


class RedemptionOut(Schema):
    id: UUID
    grant_id: UUID
    service_id: UUID | None
    service_name: str | None
    redeemed_at: datetime
    remaining: int | None = Field(
        description="Sessions left after this one; null = unlimited."
    )


class ReassignIn(In):
    """The payload of ``customer.customer.merged``."""

    id: UUID = Field(description="The customer's card that stays.")
    absorbed_id: UUID = Field(
        title=gettext_noop("Duplicate customer"), description="The card merged into it."
    )


class ReassignedOut(Schema):
    moved: int = Field(description="How many vouchers moved to the card that stays.")


class ForgetCustomerIn(In):
    """The payload of ``customer.customer.erased``."""

    id: UUID = Field(description="The customer's card whose personal data was erased.")


class ForgottenOut(Schema):
    erased: int = Field(description="How many vouchers of the card had a free text emptied.")


GrantPage = Page[GrantOut]
OrphanPage = Page[OrphanOut]


# ── Movements of a voucher ────────────────────────────────────────────────────────────────────


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
    sale_id: UUID | None
    appointment_id: UUID | None
    note: str
    actor: str
    uses_delta: int
    days_delta: int
    reason: str


MovementPage = Page[MovementOut]


# ── Sessions of the till (SERVICE-F22–F27) ────────────────────────────────────────────────────


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


class HoldIn(In):
    grant_id: UUID = Field(description="The voucher sold whose session pays the line.")
    service_id: UUID = Field(
        description="The service of the line; the voucher must cover it."
    )
    order_line_id: UUID = Field(
        description="The line of the open check (Sales) the session pays: one session per line."
    )


class SessionRefIn(In):
    id: UUID = Field(description="The session of the voucher.")


class SettleIn(In):
    ids: list[UUID] = Field(
        min_length=1,
        max_length=100,
        description="The sessions held for the lines the sale charges.",
    )
    sale_id: UUID = Field(description="The sale charged (Sales).")
    customer_id: UUID | None = Field(
        description="The sale's customer: it must own the vouchers."
    )


class ReturnIn(In):
    ids: list[UUID] = Field(
        min_length=1,
        max_length=100,
        description="The sessions spent in the sale that come back.",
    )
    reference: UUID = Field(
        title=gettext_noop("Refund or void"),
        description="The refund, or the sale voided, that gives them back (Sales).",
    )
    reason: Note = Field("", description="Why, as the refund or the void says it.")


class SessionOut(Schema):
    id: UUID
    grant_id: UUID
    package_id: UUID
    package_name: str
    customer_id: UUID
    service_id: UUID | None
    status: SessionStatus
    order_line_id: UUID | None
    hold_until: datetime | None
    sale_id: UUID | None
    remaining: int | None = Field(
        description="Sessions the voucher has left now; null = unlimited."
    )
    voucher_expired: bool = Field(description="The voucher is past its expiry.")


class SessionsOut(Schema):
    rows: list[SessionOut]


class ExpiredOut(Schema):
    expired: int = Field(description="How many holds past their deadline were marked.")
