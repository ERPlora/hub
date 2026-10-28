"""Input and output schemas of the sale app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. Money travels in
whole cents (never negative); quantities as exact decimals with at most three places; percentages with
two. What a person names aloud is accepted besides the id: a product by its SKU or name, a customer by
its name, phone or email, a sale by its number, a payment method by its name or type, a department or
a quick note by its name or text.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints, field_validator, model_validator

from apps.customer.tax_ids import InvalidCountry, normalize_country
from apps.tax.schemas import TerritoryTaxKind

T = TypeVar("T")

#: Ninety-nine billion euros in cents: far above any price, inside a bigint.
MAX_CENTS = 9_999_999_999_999
#: Lines of one check, legs of one charge, lines of one refund.
MAX_LINES = 200
MAX_PAYMENTS = 10
#: Options of Modifiers one line may carry (Modifiers' own ceiling, ``modifier.schemas.MAX_PICKS``).
MAX_OPTIONS = 100

SAY_WHICH_PRODUCT = _("Say which product: its id, or its SKU or name.")
SAY_WHICH_SERVICE = _("Say which service: its id, or its name.")
SAY_WHICH_MENU = _("Say which menu: its id, or its name.")
SAY_WHICH_DISH = _("Say which dish: the choice's id, or its product's SKU or name.")
SAY_WHICH_DEPARTMENT = _(
    "Say which section (or tax category) the open price is charged at."
)
SAY_WHICH_SALE = _("Say which sale: its id or its number.")
SAY_WHICH_METHOD = _("Say which payment method: its id, its name or its type.")
SAY_WHICH_DEPARTMENT_ROW = _("Say which section: its id or its name.")
SAY_WHICH_QUICK_NOTE = _("Say which quick note: its id or its text.")
ONE_SOURCE = _(
    "Charge an open check (order_id) or loose lines (lines, service lines or open-price lines), one of the two."
)
CHECK_DISCOUNT_ON_THE_CHECK = _(
    "The discount of an open check is set on the check itself, not at the charge."
)
COUNTRY_CODE = _("Enter the country's ISO code, e.g. ES, FR or GB.")

# How the Sales screens name the data the models do not (the assistant's card names each datum by its title).
LINE = gettext_noop("Line")
OPEN_LINES = gettext_noop("Open-price lines")
SERVICE_LINES = gettext_noop("Services")
COMBO_LINES = gettext_noop("Menus")
# A counter sale's fixed ticket discount, named as an open check's (its model's name is the sale's total, «Discounts»).
FIXED_DISCOUNT = gettext_noop("Fixed-amount discount")


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Name = _text(200, 1)
Said = _text(200, 1)
Label = _text(120)
Note = _text(255)
Reason = _text(500, 1)
Cents = Annotated[int, Field(ge=0, le=MAX_CENTS)]
PositiveCents = Annotated[int, Field(ge=1, le=MAX_CENTS)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=15, decimal_places=3)]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
AttemptKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    ),
]
DocumentType = Literal["ticket", "invoice"]
MethodType = Literal["cash", "card", "transfer", "other"]
SaleStatus = Literal["completed", "voided", "refunded"]
OrderStatus = Literal["open", "completed", "voided"]
#: AEAT's IDType of a foreign customer: 02 EU VAT, 03 passport, 04 foreign tax id, 05 residence
#: certificate, 06 other, 07 not registered; empty for a Spanish one.
IdType = Literal["", "02", "03", "04", "05", "06", "07"]
SortDir = Literal["asc", "desc"]


class PageIn(Schema):
    limit: int = Field(50, ge=1, le=100, description="Rows per page, 1 to 100.")
    offset: int = Field(0, ge=0, description="Rows to skip.")


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="Rows that match, in every page.")
    limit: int = Field(description="Rows per page asked.")
    offset: int = Field(description="Rows skipped.")


class Closed(Schema):
    """An input that refuses fields it does not know (a typo is a 422, never silently ignored)."""

    model_config = ConfigDict(extra="forbid")


class EmptyIn(Closed):
    pass


# ── Settings ──────────────────────────────────────────────────────────────────────────────────────


class SettingsFields(Schema):
    allow_cash: bool = Field(description="Cash methods may be used to charge.")
    allow_card: bool = Field(description="Card methods may be used to charge.")
    allow_transfer: bool = Field(
        description="Bank transfer methods may be used to charge."
    )
    show_products: bool = Field(description="The till offers Inventory's products.")
    show_services: bool = Field(
        description="The till offers the services of the Services app."
    )
    require_customer: bool = Field(description="Every sale needs a customer.")
    allow_discounts: bool = Field(description="Line and ticket discounts may be given.")
    max_discount_percent: int = Field(
        ge=0,
        le=100,
        description="The biggest discount (each one, in %) given without a manager; 100 = no cap.",
    )
    enable_parked_tickets: bool = Field(
        description="Checks may be parked and picked up again."
    )
    default_tax_included: bool = Field(description="Prices include VAT.")
    auto_invoice_with_tax_id: bool = Field(
        description="The charge starts as an invoice when the customer has a tax id."
    )
    default_document_type: DocumentType = Field(
        description="The document the charge starts with: ticket or invoice."
    )
    receipt_header: str = Field(
        max_length=1000,
        description="Receipt header: first line the name, the rest the address.",
    )
    receipt_footer: str = Field(max_length=1000, description="Receipt footer.")
    receipt_footer_image: str = Field(
        max_length=500,
        description="Address (URL) of an image printed under the footer.",
    )
    receipt_marketing_url: str = Field(
        max_length=500,
        description="Address the promotional QR of the receipt opens; empty = none.",
    )
    receipt_marketing_text: str = Field(
        max_length=200, description="Caption of the promotional QR."
    )


class SettingsOut(SettingsFields):
    updated_at: datetime | None = Field(
        description="When they were last saved; empty while the factory values apply."
    )


class SettingsPatchIn(Closed):
    """Only the fields sent change; the rest keep their value."""

    allow_cash: bool | None = Field(
        None, description="Cash methods may be used to charge."
    )
    allow_card: bool | None = Field(
        None, description="Card methods may be used to charge."
    )
    allow_transfer: bool | None = Field(
        None, description="Bank transfer methods may be used to charge."
    )
    show_products: bool | None = Field(
        None, description="The till offers Inventory's products."
    )
    show_services: bool | None = Field(
        None, description="The till offers the services of the Services app."
    )
    require_customer: bool | None = Field(
        None, description="Every sale needs a customer."
    )
    allow_discounts: bool | None = Field(
        None, description="Line and ticket discounts may be given."
    )
    max_discount_percent: int | None = Field(
        None,
        ge=0,
        le=100,
        description="The biggest discount (each one, in %) given without a manager; 100 = no cap.",
    )
    enable_parked_tickets: bool | None = Field(
        None, description="Checks may be parked and picked up again."
    )
    default_tax_included: bool | None = Field(None, description="Prices include VAT.")
    auto_invoice_with_tax_id: bool | None = Field(
        None,
        description="The charge starts as an invoice when the customer has a tax id.",
    )
    default_document_type: DocumentType | None = Field(
        None, description="The document the charge starts with."
    )
    receipt_header: str | None = Field(
        None,
        max_length=1000,
        description="Receipt header: first line the name, the rest the address.",
    )
    receipt_footer: str | None = Field(
        None, max_length=1000, description="Receipt footer."
    )
    receipt_footer_image: str | None = Field(
        None,
        max_length=500,
        description="Address (URL) of an image printed under the footer.",
    )
    receipt_marketing_url: str | None = Field(
        None,
        max_length=500,
        description="Address the promotional QR opens; empty = none.",
    )
    receipt_marketing_text: str | None = Field(
        None, max_length=200, description="Caption of the promotional QR."
    )


# ── Payment methods ───────────────────────────────────────────────────────────────────────────────


class PaymentMethodListIn(PageIn):
    search: str | None = Field(None, max_length=60, description="Part of the name.")


class PaymentMethodOut(Schema):
    id: UUID = Field(description="The method's id.")
    name: str = Field(description="Its name as stored.")
    display_name: str = Field(
        description="Its name in the reader's language (the factory ones are translated)."
    )
    type: MethodType = Field(description="cash, card, transfer or other.")
    sort_order: int = Field(description="Position in the charge sheet.")
    requires_change: bool = Field(
        description="Cash: asks what was handed over and gives change."
    )
    allowed: bool = Field(description="Whether the till settings let it charge today.")


PaymentMethodPage = Page[PaymentMethodOut]


class PaymentMethodIn(Closed):
    name: _text(60, 1) = Field(description="The method's name, e.g. Bizum.")
    type: MethodType = Field(
        "cash", description="cash (default), card, transfer or other."
    )
    sort_order: int = Field(
        30, ge=0, le=100_000, description="Position in the charge sheet."
    )


# ── Departments and quick notes ───────────────────────────────────────────────────────────────────


class DepartmentListIn(PageIn):
    search: str | None = Field(None, max_length=60, description="Part of the name.")
    sort: Literal["sort_order", "name"] = Field(
        "sort_order", description="Column to sort by."
    )
    dir: SortDir = Field("asc", description="Sort direction.")


class DepartmentOut(Schema):
    id: UUID = Field(description="The department's id.")
    name: str = Field(description="Its name.")
    tax_category_key: str = Field(description="Key of the tax category it charges at.")
    tax_category_name: str = Field(
        description="That category's name in the reader's language."
    )
    tax_rate_pct: Decimal | None = Field(
        description="The rate it charges today in the business's country; empty without a rule."
    )
    sort_order: int = Field(description="Position in the open-price sheet.")


DepartmentPage = Page[DepartmentOut]


class DepartmentIn(Closed):
    name: _text(60, 1) = Field(
        description="The name the cashier reads, e.g. Fruit and veg."
    )
    tax_category_key: _text(80, 1) = Field(
        description="The tax category it charges at: its key, its name or an alias."
    )
    sort_order: int = Field(
        0, ge=0, le=100_000, description="Position in the open-price sheet."
    )


class DepartmentRefIn(Closed):
    id: UUID | None = Field(None, description="The department's id.")
    department: _text(60, 1) | None = Field(
        None, description="Its name, when its id is not known."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and self.department is None:
            raise ValueError(str(SAY_WHICH_DEPARTMENT_ROW))
        return self


class DepartmentUpdateIn(DepartmentRefIn):
    name: _text(60, 1) | None = Field(None, description="New name.")
    tax_category_key: _text(80, 1) | None = Field(
        None, description="New tax category: its key, its name or an alias."
    )
    sort_order: int | None = Field(None, ge=0, le=100_000, description="New position.")


class QuickNoteListIn(PageIn):
    search: str | None = Field(None, max_length=80, description="Part of the text.")
    sort: Literal["sort_order", "text"] = Field(
        "sort_order", description="Column to sort by."
    )
    dir: SortDir = Field("asc", description="Sort direction.")


class QuickNoteOut(Schema):
    id: UUID = Field(description="The quick note's id.")
    text: str = Field(description="Its text.")
    sort_order: int = Field(description="Position among the chips.")


QuickNotePage = Page[QuickNoteOut]


class QuickNoteIn(Closed):
    text: _text(80, 1) = Field(description="The note, e.g. no salt.")
    sort_order: int = Field(
        0, ge=0, le=100_000, description="Position among the chips."
    )


class QuickNoteRefIn(Closed):
    id: UUID | None = Field(None, description="The quick note's id.")
    quick_note: _text(80, 1) | None = Field(
        None, title=gettext_noop("Quick note"), description="Its text, when its id is not known."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and self.quick_note is None:
            raise ValueError(str(SAY_WHICH_QUICK_NOTE))
        return self


class QuickNoteUpdateIn(QuickNoteRefIn):
    text: _text(80, 1) | None = Field(None, description="New text.")
    sort_order: int | None = Field(None, ge=0, le=100_000, description="New position.")


# ── Open checks ───────────────────────────────────────────────────────────────────────────────────


class LineFields(Closed):
    quantity: Quantity = Field(
        Decimal("1"),
        description="Quantity, in the product's unit (0.532 kg); 1 by default.",
    )
    notes: Note = Field(
        "", description="A note for the kitchen and the ticket, e.g. no salt."
    )
    staff_id: UUID | None = Field(
        None,
        description="Who serves this line (a member of Staff); empty = the check's.",
    )
    is_gift: bool = Field(False, description="True: a comp, charged at 0.")
    gift_reason: _text(200) = Field("", description="Why it is a comp.")


class ProductLineIn(LineFields):
    """A line of Inventory's catalog: its price, unit and tax category come from the catalog."""

    product_id: UUID | None = Field(None, description="The product's id.")
    product: Said | None = Field(
        None, title=gettext_noop("Product"), description="The product's SKU or name, when its id is not known."
    )
    option_ids: list[UUID] = Field(
        default_factory=list,
        max_length=MAX_OPTIONS,
        title=gettext_noop("Modifiers"),
        description="The options of Modifiers chosen for the product (modifier.group.for_target), in the order "
        "they were chosen; one chosen twice is named twice. Modifiers checks and values them: their price comes "
        "from it and stays frozen on the line.",
    )

    @model_validator(mode="after")
    def _named(self):
        if self.product_id is None and self.product is None:
            raise ValueError(str(SAY_WHICH_PRODUCT))
        return self


class ComboChoiceIn(Closed):
    """A dish picked in a menu of Menus (COMBO-F08): by the choice's id, or by its product (and course)."""

    option_id: UUID | None = Field(None, description="The choice's id (combo.combo.for_sale).")
    product: Said | None = Field(
        None, description="The SKU or name of the product picked, when the choice's id is not known."
    )
    group: Said | None = Field(
        None, description="The course it is picked in, when the product is in several."
    )
    quantity: int = Field(
        1, ge=1, le=MAX_OPTIONS, description="How many times it is picked in one menu (two coffees: 2)."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.option_id is None and self.product is None:
            raise ValueError(str(SAY_WHICH_DISH))
        return self


class ComboLineFields(LineFields):
    """A menu of Menus with the dishes picked: Menus checks it and prices it, and the line keeps its answer."""

    combo_id: UUID | None = Field(None, description="The menu's id (combo.combo.for_sale).")
    combo: Said | None = Field(None, description="The menu's name, when its id is not known.")
    choices: list[ComboChoiceIn] = Field(
        default_factory=list,
        max_length=MAX_OPTIONS,
        title=gettext_noop("Dishes"),
        description="The dishes picked, course by course. Menus checks each course (its minimum, maximum and "
        "repeats) and prices the menu: its closed price plus the supplements, frozen on the line.",
    )

    @model_validator(mode="after")
    def _named(self):
        if self.combo_id is None and self.combo is None:
            raise ValueError(str(SAY_WHICH_MENU))
        return self


class ComboLineIn(ComboLineFields):
    pass


class OpenLineFields(LineFields):
    """A line at an open price: typed amount, charged at a department's (or a tax category's) VAT."""

    unit_price: Cents = Field(description="The amount typed, in cents, per unit.")
    department_id: UUID | None = Field(
        None, description="The department it is charged at."
    )
    department: _text(60, 1) | None = Field(
        None, description="The department's name, when its id is not known."
    )
    tax_category_key: _text(80, 1) | None = Field(
        None,
        description="Without departments: the tax category (key, name or alias) it is charged at.",
    )
    name: _text(200) = Field(
        "", description="The line's name; the department's by default."
    )

    @model_validator(mode="after")
    def _charged_somewhere(self):
        if (
            self.department_id is None
            and self.department is None
            and self.tax_category_key is None
        ):
            raise ValueError(str(SAY_WHICH_DEPARTMENT))
        return self


class OpenLineIn(OpenLineFields):
    pass


class ServiceLineFields(LineFields):
    """A line of a service of the Services app: its name, price and tax category come from it."""

    service_id: UUID | None = Field(None, description="The service's id (Services).")
    service: Said | None = Field(
        None, description="The service's name, when its id is not known."
    )
    unit_price: Cents | None = Field(
        None,
        description="Only for a service without a fixed price (from, hourly, variable, free): the amount charged "
        "per unit, in cents, within its minimum and maximum.",
    )
    booked_price: Cents | None = Field(
        None,
        title=gettext_noop("Booked price"),
        description="The price the appointment of the check booked for this service, in cents, frozen on the "
        "line whatever the catalog says today. Checked against the appointment (its service at that price; "
        "lower only with the open-price right); without an appointment it is an open price.",
    )

    @model_validator(mode="after")
    def _named(self):
        if self.service_id is None and self.service is None:
            raise ValueError(str(SAY_WHICH_SERVICE))
        return self


class ServiceLineIn(ServiceLineFields):
    pass


class OrderOpenIn(Closed):
    label: Label = Field("", description="The check's title, e.g. Ana — terrace.")
    notes: _text(1000) = Field("", description="Notes of the check.")
    appointment_id: UUID | None = Field(
        None, description="The appointment (Appointments) this check charges."
    )
    lines: list[ProductLineIn] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        description="Catalog lines to start with.",
    )
    open_lines: list[OpenLineIn] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        title=OPEN_LINES,
        description="Open-price lines to start with (needs the open-price permission).",
    )
    service_lines: list[ServiceLineIn] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        title=SERVICE_LINES,
        description="Lines of services of the Services app to start with.",
    )
    combo_lines: list[ComboLineIn] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        title=COMBO_LINES,
        description="Menus of the Menus app to start with, each with its dishes.",
    )


class OrderRefIn(Closed):
    order_id: UUID = Field(description="The open check's id.")


class OrderAddLineIn(ProductLineIn):
    model_config = ConfigDict(extra="forbid")

    order_id: UUID = Field(description="The open check's id.")


class OrderAddOpenLineIn(OpenLineFields):
    model_config = ConfigDict(extra="forbid")

    order_id: UUID = Field(description="The open check's id.")


class OrderAddServiceLineIn(ServiceLineFields):
    model_config = ConfigDict(extra="forbid")

    order_id: UUID = Field(description="The open check's id.")


class OrderAddComboLineIn(ComboLineFields):
    model_config = ConfigDict(extra="forbid")

    order_id: UUID = Field(description="The open check's id.")


class OrderLineRefIn(Closed):
    order_id: UUID = Field(description="The open check's id.")
    line_id: UUID = Field(title=LINE, description="The line's id.")


class OrderApplyVoucherIn(OrderLineRefIn):
    grant_id: UUID = Field(
        title=gettext_noop("Voucher"),
        description="The voucher sold (Services) whose session pays the line: one of the customer's, read with "
        "service.grant.tender_options."
    )


class OrderUpdateLineIn(OrderLineRefIn):
    quantity: Quantity | None = Field(None, description="New quantity; empty keeps it.")
    is_gift: bool | None = Field(
        None, description="True: a comp; false: charged again; empty keeps it."
    )
    gift_reason: _text(200) | None = Field(None, description="Why it is a comp.")
    notes: Note | None = Field(
        None, description="New note; empty text clears it; absent keeps it."
    )


class OrderSetLineStaffIn(OrderLineRefIn):
    staff_id: UUID | None = Field(
        description="Who did it (a member of Staff); empty = the check's professional."
    )


class OrderVoidLineIn(OrderLineRefIn):
    reason: _text(255, 1) = Field(
        description="Why a line already sent to the kitchen is voided."
    )


class OrderSplitIn(Closed):
    order_id: UUID = Field(description="The check to split.")
    line_ids: list[UUID] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        title=gettext_noop("Lines to move"),
        description="Lines that move to the new check; none = a blank one.",
    )
    label: Label = Field("", description="The new check's title.")


class OrderMergeIn(Closed):
    from_order_id: UUID = Field(
        title=gettext_noop("From check"), description="The check that is absorbed (it ends voided)."
    )
    to_order_id: UUID = Field(title=gettext_noop("Into check"), description="The check that stays with every line.")


class OrderSetDiscountIn(Closed):
    order_id: UUID = Field(description="The open check's id.")
    discount_percent: Percent = Field(
        description="Ticket discount in %, 0 to 100; 0 removes it."
    )
    discount_amount: Cents | None = Field(
        None, description="Fixed ticket discount in cents; empty keeps the one it has."
    )


class OrderSetLineDiscountIn(OrderLineRefIn):
    discount_percent: Percent = Field(
        description="Line discount in %, 0 to 100; 0 removes it."
    )


class OrderSetLabelIn(Closed):
    order_id: UUID = Field(description="The open check's id.")
    label: Label = Field(description="Its title, e.g. Table 4 or Ana — terrace.")


class OrderSetAppointmentIn(Closed):
    order_id: UUID = Field(description="The open check's id.")
    appointment_id: UUID | None = Field(
        description="The appointment it charges; empty unlinks it."
    )


class OrderFireIn(Closed):
    order_id: UUID = Field(
        description="The open check whose pending lines go to the kitchen."
    )
    label: Label = Field(
        "", description="What the kitchen reads as the check's name, e.g. Table 4."
    )
    channel: Literal["dine_in", "takeaway", "delivery"] = Field(
        "dine_in", title=gettext_noop("Order type"), description="dine_in, takeaway or delivery."
    )
    priority: _text(20) = Field(
        "", title=gettext_noop("Priority"), description="Priority the kitchen shows, e.g. urgent."
    )
    waiter: _text(128) = Field(
        "",
        title=gettext_noop("Served by"),
        description="Who attends the check as the till names it («Atiende»); empty: who sends it.",
    )


class OrderListIn(PageIn):
    status: OrderStatus | None = Field(
        "open", description="Only checks of this status; open by default."
    )
    search: str | None = Field(None, max_length=120, description="Part of the title.")


class ModifierPickOut(Schema):
    option_id: UUID = Field(description="The option of Modifiers chosen.")
    group_id: UUID = Field(description="Its group.")
    group_name: str = Field(description="Its group's name, when it was ordered.")
    name: str = Field(description="Its name, as the receipt prints it.")
    kitchen_name: str = Field(description="What the kitchen reads.")
    price_delta: int = Field(description="Its supplement in cents, frozen when it was ordered.")
    tax_category_key: str | None = Field(description="Its own tax category; null = the dish's.")
    own_line: bool = Field(description="True: charged on a child line of its own (another tax category).")


class ModifierLineOut(Schema):
    option_id: UUID = Field(description="The option charged on a line of its own.")
    name: str = Field(description="Its name.")
    tax_category_key: str = Field(description="Its tax category: the child line's.")
    unit_price: int = Field(description="Its price in cents, frozen when it was ordered.")
    quantity: int = Field(description="How many per unit of the dish.")


class ComboDishOut(Schema):
    option_id: UUID = Field(description="The choice of Menus picked.")
    group_name: str = Field(description="Its course, when it was ordered.")
    product_id: UUID = Field(description="Its product (Inventory).")
    product_name: str = Field(description="Its name.")
    category_id: UUID | None = Field(description="Its product's first category (the kitchen's routing).")
    is_service: bool = Field(description="A service product never moves stock.")
    quantity: int = Field(description="Picks of it in one menu.")
    price_delta: int = Field(description="Its supplement in cents, frozen when it was ordered.")
    tax_category_key: str | None = Field(description="Its tax category when the menu is split.")
    amount: int | None = Field(description="Its part of one menu's amount, in cents, when the menu is split.")


class ComboLineOut(Schema):
    combo_id: UUID = Field(description="The menu of Menus.")
    kitchen_name: str = Field(description="What the kitchen reads as the menu's name.")
    supply_kind: str = Field(description="service (eaten in) or goods (to take away).")
    split: bool = Field(
        description="True: charged as one line per dish, each at its own tax category and part of the amount."
    )
    components: list[ComboDishOut] = Field(description="Its dishes, course by course.")


class OrderLineOut(Schema):
    id: UUID = Field(description="The line's id.")
    position: int = Field(description="Its place in the check.")
    product_id: UUID | None = Field(description="Inventory's product, if it is one.")
    department_id: UUID | None = Field(
        description="The department of an open price, if it is one."
    )
    name: str = Field(description="Name.")
    sku: str = Field(description="SKU.")
    is_service: bool = Field(description="A service never moves stock.")
    unit: str = Field(description="Unit of the quantity.")
    quantity: Decimal = Field(description="Quantity.")
    unit_price: int = Field(
        description="Frozen price in cents, per price_quantity of pricing_unit."
    )
    price_quantity: Decimal = Field(description="Quantity the price refers to.")
    pricing_unit: str = Field(description="Unit the price refers to.")
    tax_category_key: str = Field(description="Its tax category.")
    discount_percent: Decimal = Field(description="Line discount in %.")
    discount_approved: bool = Field(
        description="A manager approved a discount over the cap."
    )
    is_gift: bool = Field(description="A comp.")
    gift_reason: str = Field(description="Why it is a comp.")
    notes: str = Field(description="Note.")
    staff_id: UUID | None = Field(description="Who serves it; empty = the check's.")
    service_id: UUID | None = Field(description="Services' service, if it is one.")
    paid_by_voucher: bool = Field(
        description="A session of a customer's voucher pays it: it is charged at 0."
    )
    voucher_session_id: UUID | None = Field(
        description="The voucher session (Services) that pays it."
    )
    voucher_grant_id: UUID | None = Field(description="The voucher sold that pays it.")
    voucher_name: str = Field(description="The voucher's name, as it was applied.")
    voucher_remaining: int | None = Field(
        description="Sessions the voucher had left after this one when applied; null = unlimited."
    )
    voucher_hold_until: datetime | None = Field(
        description="Until when the session stays held for the line (one day)."
    )
    line_total: int = Field(
        description="Provisional amount in cents, before the ticket discount."
    )
    round_no: int = Field(description="Kitchen round it was sent in; 0 = pending.")
    fired_at: datetime | None = Field(description="When it was sent to the kitchen.")
    modifiers: list[ModifierPickOut] = Field(
        description="The options of Modifiers chosen, frozen when it was ordered, in the order chosen."
    )
    modifier_lines: list[ModifierLineOut] = Field(
        description="The options of another tax category: each one charged on a child line of its own."
    )
    kitchen_text: str = Field(description="What the kitchen reads under the dish (+CHEESE, -ONION).")
    combo: ComboLineOut | None = Field(
        description="A menu of Menus: its dishes and how it is charged, frozen when it was ordered."
    )


class OrderOut(Schema):
    id: UUID = Field(description="The check's id.")
    status: OrderStatus = Field(description="open, completed or voided.")
    label: str = Field(description="Title.")
    notes: str = Field(description="Notes.")
    appointment_id: UUID | None = Field(description="The appointment it charges.")
    discount_percent: Decimal = Field(description="Ticket discount in %.")
    discount_amount: int = Field(description="Fixed ticket discount in cents.")
    discount_approved: bool = Field(
        description="A manager approved a ticket discount over the cap."
    )
    provisional_total: int = Field(
        description="Σ of its lines' amounts, before the ticket discount (provisional)."
    )
    version: int = Field(
        description="Goes up with every change: a charge sent with an older one is refused."
    )
    lines_count: int = Field(description="How many lines are left to charge.")
    created_at: datetime = Field(description="When it was opened.")
    updated_at: datetime = Field(description="When it last changed.")
    lines: list[OrderLineOut] = Field(description="The lines left to charge, in order.")
    already: bool = Field(
        False,
        description="Opening a check of an appointment that already has one open answers that one: true, "
        "nothing was added to it.",
    )


class OrderRow(Schema):
    id: UUID = Field(description="The check's id.")
    status: OrderStatus = Field(description="open, completed or voided.")
    label: str = Field(description="Title.")
    provisional_total: int = Field(description="Provisional total in cents.")
    lines_count: int = Field(description="Lines left to charge.")
    appointment_id: UUID | None = Field(description="The appointment it charges.")
    created_at: datetime = Field(description="When it was opened.")
    updated_at: datetime = Field(description="When it last changed.")


OrderPage = Page[OrderRow]


class SplitLineOut(Schema):
    order: OrderOut = Field(description="The check after the split.")
    new_line_ids: list[UUID] = Field(
        description="The lines created (the one split keeps its id)."
    )


class OrderSplitOut(Schema):
    order: OrderOut = Field(description="The check split.")
    new_order: OrderOut = Field(description="The new check with the lines that moved.")


class OrderFireOut(Schema):
    order: OrderOut = Field(description="The check after sending.")
    round_no: int = Field(description="The kitchen round just sent.")
    lines_count: int = Field(description="Lines sent.")


# ── Charging ──────────────────────────────────────────────────────────────────────────────────────


class ChargeLinesIn(Schema):
    """What is charged: an open check (all its lines, or some) or loose lines (a counter sale)."""

    order_id: UUID | None = Field(None, description="The open check to charge.")
    line_ids: list[UUID] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        title=gettext_noop("Lines to charge"),
        description="Only these lines of the check (a partial charge); none = all.",
    )
    lines: list[ProductLineIn] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        description="Loose catalog lines (a counter sale).",
    )
    open_lines: list[OpenLineIn] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        title=OPEN_LINES,
        description="Loose open-price lines (a counter sale).",
    )
    service_lines: list[ServiceLineIn] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        title=SERVICE_LINES,
        description="Loose lines of services of the Services app (a counter sale).",
    )
    combo_lines: list[ComboLineIn] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        title=COMBO_LINES,
        description="Loose menus of the Menus app, each with its dishes (a counter sale).",
    )
    discount_percent: Percent = Field(
        Decimal("0"), description="Counter sale only: ticket discount in %."
    )
    discount_amount: Cents = Field(
        0, title=FIXED_DISCOUNT, description="Counter sale only: fixed ticket discount in cents."
    )

    @model_validator(mode="after")
    def _one_source(self):
        loose = bool(self.lines or self.open_lines or self.service_lines or self.combo_lines)
        if (self.order_id is None) == (not loose) or (
            self.order_id is not None and loose
        ):
            raise ValueError(str(ONE_SOURCE))
        # A check's discount lives in the check (set_discount): the charge takes none, so a figure here would be said by
        # «An approval is needed» (approval_figures) and ignored by the charge.
        if self.order_id is not None and (self.discount_percent > 0 or self.discount_amount > 0):
            raise ValueError(str(CHECK_DISCOUNT_ON_THE_CHECK))
        return self


class PreviewIn(ChargeLinesIn):
    model_config = ConfigDict(extra="forbid")


class PaymentIn(Closed):
    method_id: UUID | None = Field(None, description="The payment method's id.")
    method: _text(60, 1) | None = Field(
        None,
        description="Its name or its type (cash, card…), when its id is not known.",
    )
    amount: PositiveCents | None = Field(
        None, description="What this leg pays, in cents; empty = what is left to pay."
    )
    tendered: Cents | None = Field(
        None, description="Cash: what was handed over (the change comes out of it)."
    )
    reference: _text(128) = Field(
        "", description="A free reference of the leg, e.g. the card's authorisation."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.method_id is None and self.method is None:
            raise ValueError(str(SAY_WHICH_METHOD))
        return self


class CompleteIn(ChargeLinesIn):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: AttemptKey = Field(
        description="The attempt's key: born when the charge sheet opens and reused on every retry, so a retry never charges twice."
    )
    order_version: int | None = Field(
        None,
        ge=1,
        title=gettext_noop("Check version"),
        description="The check's version the screen charged; a newer one refuses the charge.",
    )
    payments: list[PaymentIn] = Field(
        default_factory=list,
        max_length=MAX_PAYMENTS,
        description="The tenders; none = all in cash, exact amount.",
    )
    document_type: DocumentType | None = Field(
        None, description="ticket or invoice; the settings' default when empty."
    )
    customer_id: UUID | None = Field(None, description="The customer's card.")
    customer: _text(200, 1) | None = Field(
        None,
        description="The customer's name, phone or email, when the id is not known.",
    )
    customer_name: _text(200) = Field(
        "", description="Invoice: name or company name (the card's by default)."
    )
    customer_tax_id: _text(32) = Field(
        "", description="Invoice: tax id (the card's by default)."
    )
    customer_address: _text(500) = Field(
        "", description="Invoice: address (the card's by default)."
    )
    customer_country: str = Field(
        "",
        description="Invoice: ISO country code of the customer; empty = the business's.",
    )
    customer_id_type: IdType = Field(
        "",
        description="Invoice abroad: 02 EU VAT, 03 passport, 04 foreign tax id, 05 residence certificate, 06 other, 07 not registered.",
    )
    staff_id: UUID | None = Field(
        None, description="Who served the sale (a member of Staff)."
    )
    appointment_id: UUID | None = Field(
        None, description="Counter sale: the appointment it charges."
    )
    notes: _text(1000) = Field("", description="Notes of the sale.")

    @field_validator("customer_country")
    @classmethod
    def _country(cls, value: str) -> str:
        # The same ISO 3166-1 list Invoicing's recipient reads: what Sales accepts, Invoicing accepts.
        try:
            return normalize_country(value)
        except InvalidCountry:
            raise ValueError(str(COUNTRY_CODE)) from None


#: What Invoicing answered for the fiscal document of a write (models.FiscalStatus); empty on a sale
#: charged before Sales asked for it.
FiscalStatus = Literal["", "issued", "pending", "unavailable", "none"]


class BreakdownOut(Schema):
    """One entry per fiscal key (tax, regime, qualification, exemption cause, rates) and component: the
    shape Invoicing declares. A sale charged before the key was kept reads as subject VAT."""

    rate_pct: Decimal = Field(description="The rate.")
    label: str = Field(description="vat, or the component's name (surcharge…).")
    tax_type: str = Field("vat", description="The component's tax: vat, surcharge, igic, ipsi…")
    regime: str = Field("01", description="The VAT regime key of the rule (01 = general).")
    qualification: str = Field(
        "subject",
        description="subject, subject_reverse, exempt, not_subject or not_subject_location.",
    )
    exempt_reason: str = Field("", description="The exemption cause (E1–E8) of an exempt key.")
    base: int = Field(description="Taxable base of the key, in cents.")
    tax: int = Field(description="Tax of this component of the key, in cents.")


class PreviewLineOut(Schema):
    order_line_id: UUID | None = Field(description="The check's line.")
    name: str = Field(description="Name.")
    quantity: Decimal = Field(description="Quantity.")
    unit: str = Field(description="Unit.")
    unit_price: int = Field(description="Frozen price in cents.")
    discount_percent: Decimal = Field(description="Line discount in %.")
    is_gift: bool = Field(description="A comp.")
    service_id: UUID | None = Field(description="Services' service, if it is one.")
    paid_by_voucher: bool = Field(description="A voucher session pays it (at 0).")
    voucher_name: str = Field(description="The voucher that pays it.")
    voucher_remaining: int | None = Field(
        description="Sessions the voucher had left after this one when applied; null = unlimited."
    )
    tax_category_key: str = Field(description="Tax category.")
    tax_rate: Decimal = Field(description="Rate applied.")
    net_amount: int = Field(description="Base in cents.")
    tax_amount: int = Field(description="Tax in cents.")
    line_total: int = Field(description="Total in cents.")
    modifiers: list[str] = Field(description="The options charged inside the line.")
    is_child: bool = Field(
        description="An option of another tax category, charged on a line of its own under its dish."
    )
    combo_name: str = Field(
        description="The menu this line charges, or a dish of (a menu split per dish); empty otherwise."
    )
    components: list[str] = Field(description="The dishes of a menu charged in one line.")


class PreviewOut(Schema):
    order_id: UUID | None = Field(description="The check valued.")
    order_version: int | None = Field(
        description="Its version: send it with the charge."
    )
    lines_count: int = Field(description="Lines valued.")
    tax_included: bool = Field(description="Prices include VAT.")
    subtotal: int = Field(description="Taxable base in cents.")
    tax_total: int = Field(description="Tax in cents.")
    discount_amount: int = Field(description="Every discount given, in cents.")
    discount_percent: Decimal = Field(description="Ticket discount in %.")
    ticket_discount_amount: int = Field(
        description="Fixed ticket discount in cents applied to this charge."
    )
    gift_total: int = Field(description="Comps at cost, in cents.")
    total: int = Field(description="What would be charged, in cents.")
    breakdown: list[BreakdownOut] = Field(description="Base and tax by fiscal key.")
    lines: list[PreviewLineOut] = Field(description="Each line valued.")
    operation_total: int = Field(
        description="The whole operation the cash limit looks at, in cents: on a check charged in parts, what "
        "it already charged plus all it has left (this charge included); otherwise the total."
    )
    cash_limit: int | None = Field(
        description="From this operation total on, no cash at all (Spain: 100000); empty = no limit."
    )
    ticket_limit: int | None = Field(
        description="Above this total, only an invoice (Spain: 300000); empty = no limit."
    )


class SaleDishOut(Schema):
    product_id: UUID = Field(description="The dish's product (Inventory).")
    product_name: str = Field(description="Its name.")
    quantity: int = Field(description="How many in one menu.")


class SaleLineOut(Schema):
    id: UUID = Field(description="The line's id.")
    position: int = Field(description="Its place.")
    order_line_id: UUID | None = Field(description="The check's line it came from.")
    product_id: UUID | None = Field(description="Inventory's product.")
    department_id: UUID | None = Field(description="The open price's department.")
    name: str = Field(description="Name.")
    sku: str = Field(description="SKU.")
    is_service: bool = Field(description="A service.")
    unit: str = Field(description="Unit.")
    quantity: Decimal = Field(description="Quantity.")
    unit_price: int = Field(
        description="Price in cents, per price_quantity of pricing_unit."
    )
    price_quantity: Decimal = Field(description="Quantity the price refers to.")
    pricing_unit: str = Field(description="Unit the price refers to.")
    discount_percent: Decimal = Field(description="Line discount in %.")
    is_gift: bool = Field(description="A comp.")
    gift_reason: str = Field(description="Why.")
    notes: str = Field(description="Note.")
    staff_id: UUID | None = Field(description="Who served it.")
    service_id: UUID | None = Field(description="Services' service, if it is one.")
    paid_by_voucher: bool = Field(description="A voucher session paid it (at 0).")
    voucher_name: str = Field(description="The voucher that paid it.")
    tax_category_key: str = Field(description="Tax category.")
    tax_rate: Decimal = Field(description="Rate.")
    tax_country_code: str = Field(description="Country of the rule.")
    tax_region_code: str = Field(
        description="Region of the rule; empty = the whole country."
    )
    tax_rule_id: UUID | None = Field(description="Tax's rule.")
    net_amount: int = Field(description="Base in cents.")
    tax_amount: int = Field(description="Tax in cents.")
    line_total: int = Field(description="Total in cents.")
    returned_quantity: Decimal = Field(description="Units that came back with refunds.")
    modifiers: list[str] = Field(
        description="The options charged inside the line, as the receipt prints them under it."
    )
    parent_line_id: UUID | None = Field(
        description="The line of the dish an option of another tax category hangs from."
    )
    combo_id: UUID | None = Field(description="The menu of Menus this line charges, or a dish of.")
    combo_name: str = Field(description="That menu's name: the receipt's header of its dishes.")
    components: list[SaleDishOut] = Field(description="The dishes of the menu charged in this line.")


class SalePaymentOut(Schema):
    id: UUID = Field(description="The leg's id.")
    position: int = Field(description="Order taken.")
    method_id: UUID = Field(description="Payment method.")
    method_name: str = Field(
        description="Its name as charged (translated if it is a factory one)."
    )
    method_type: MethodType = Field(description="cash, card, transfer or other.")
    amount: int = Field(description="Amount in cents.")
    tendered: int = Field(description="Handed over, in cents.")
    change: int = Field(description="Change given, in cents.")
    reference: str = Field(description="Reference.")


class PaperOut(Schema):
    queued: bool = Field(
        description="True: Printing queued it for its printer. False: Printing is not on, no printer takes it, its "
        "fiscal document is still pending or Printing refused it — the device prints the screen's paper."
    )
    job_id: UUID | None = Field(description="Its job in the printing queue.")
    printer: str | None = Field(description="The printer it went to.")


class SaleOut(Schema):
    id: UUID = Field(description="The sale's id.")
    number: str = Field(description="Its number, AAAAMMDD-NNNN.")
    business_day: date = Field(description="Its business day.")
    status: SaleStatus = Field(description="completed, voided or refunded.")
    document_type: DocumentType = Field(description="ticket or invoice.")
    order_id: UUID | None = Field(description="The check it came from.")
    customer_id: UUID | None = Field(description="The customer's card.")
    customer_name: str = Field(description="The customer's name as printed.")
    staff_id: UUID | None = Field(description="Who served it.")
    appointment_id: UUID | None = Field(description="The appointment it charged.")
    tax_included: bool = Field(description="Prices include VAT.")
    currency: str = Field(description="ISO 4217 currency it was charged in: the business's then, never rewritten.")
    currency_decimals: int = Field(description="The decimals of its currency as the server counts them (0 in JPY).")
    subtotal: int = Field(description="Taxable base in cents.")
    tax_total: int = Field(description="Tax in cents.")
    discount_percent: Decimal = Field(description="Ticket discount in %.")
    discount_amount: int = Field(description="Every discount given, in cents.")
    gift_total: int = Field(description="Comps at cost, in cents.")
    total: int = Field(description="Total charged, in cents.")
    tendered_total: int = Field(description="Handed over, in cents.")
    change_total: int = Field(description="Change given, in cents.")
    refunded_total: int = Field(description="Refunded so far, in cents.")
    refundable_total: int = Field(description="What can still be refunded, in cents.")
    sessions_to_return: int = Field(
        description="Lines paid with a voucher whose session has not come back yet."
    )
    payment_method_name: str = Field(description="The main tender's method.")
    breakdown: list[BreakdownOut] = Field(description="Base and tax by fiscal key.")
    notes: str = Field(description="Notes.")
    voided_at: datetime | None = Field(description="When it was voided.")
    voided_by: str = Field(description="Who voided it.")
    void_reason: str = Field(description="Why.")
    created_at: datetime = Field(description="When it was charged.")
    created_by: str = Field(description="Who charged it.")
    lines: list[SaleLineOut] = Field(description="Its lines.")
    payments: list[SalePaymentOut] = Field(description="Its tenders.")
    invoice_status: FiscalStatus = Field(
        description="Its fiscal document, issued by Invoicing in the same charge: issued; pending (Invoicing "
        "refused now, e.g. no issuer yet, and issues it later on its own); unavailable (no Invoicing: a "
        "ticket without fiscal document)."
    )
    invoice_id: UUID | None = Field(description="Its fiscal document in Invoicing.")
    invoice_number: str = Field(
        description="The number of its fiscal document in its series (TICKET-2026-000001, FACT-2026-000001); "
        "empty while it has none. The paper prints it."
    )
    invoice_type: str = Field(description="F2 (ticket) or F1 (invoice); empty while it has none.")
    void_invoice_status: FiscalStatus = Field(
        description="The rectifying invoice of its void, as Invoicing answered; empty if not voided."
    )
    void_invoice_number: str = Field(description="The number of the rectifying invoice of its void.")
    documents_pending: bool = Field(
        description="A fiscal document of it waits (its own, its void's or a refund's): «Issue now» issues it."
    )
    already: bool = Field(
        False,
        description="True: this attempt had already been charged; nothing new was recorded.",
    )
    printed: PaperOut | None = Field(
        None,
        description="The charge only: whether its receipt (or the drawer's order) went to the printing queue, to "
        "which printer; not queued, the device prints the screen's paper.",
    )


class SaleRefIn(Closed):
    sale_id: UUID | None = Field(None, description="The sale's id.")
    sale: _text(24, 1) | None = Field(
        None, description="Its number, e.g. 20261014-0007, when the id is not known."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.sale_id is None and self.sale is None:
            raise ValueError(str(SAY_WHICH_SALE))
        return self


class SalePrintIn(SaleRefIn):
    duplicate: bool = Field(
        True,
        title=gettext_noop("Print as duplicate"),
        description="Print it marked «DUPLICATE»: every print from Sales is a copy; only the till's first paper right "
        "after charging, when nothing printed it at checkout, is the original.",
    )


class SaleByKeyIn(Closed):
    idempotency_key: AttemptKey = Field(
        description="The attempt's key the charge was sent with."
    )


class SaleByKeyOut(Schema):
    found: bool = Field(description="Whether a sale was charged with that key.")
    sale: SaleOut | None = Field(description="That sale.")


class SaleListIn(PageIn):
    search: str | None = Field(
        None,
        max_length=200,
        description="Part of the number or of the customer's name.",
    )
    status: SaleStatus | None = Field(None, description="Only sales of this status.")
    payment_method_name: str | None = Field(
        None, max_length=60, description="Only sales whose main tender is this method."
    )
    customer_name: str | None = Field(
        None, max_length=200, description="Part of the customer's name."
    )
    customer_id: UUID | None = Field(None, description="Only this customer's sales.")
    staff_id: UUID | None = Field(
        None, description="Only sales served by this member of Staff."
    )
    number: str | None = Field(None, max_length=24, description="Part of the number.")
    date_from: date | None = Field(
        None, description="From this business day (inclusive)."
    )
    date_to: date | None = Field(
        None, description="Up to this business day (inclusive)."
    )
    total_min: Cents | None = Field(None, description="Total at least, in cents.")
    total_max: Cents | None = Field(None, description="Total at most, in cents.")
    sort: Literal[
        "created_at",
        "number",
        "total",
        "customer_name",
        "status",
        "payment_method_name",
    ] = Field("created_at", description="Column to sort by.")
    dir: SortDir = Field("desc", description="Sort direction.")


class SaleRow(Schema):
    id: UUID = Field(description="The sale's id.")
    number: str = Field(description="Number.")
    business_day: date = Field(description="Business day.")
    created_at: datetime = Field(description="When it was charged.")
    status: SaleStatus = Field(description="completed, voided or refunded.")
    document_type: DocumentType = Field(description="ticket or invoice.")
    customer_id: UUID | None = Field(description="Customer's card.")
    customer_name: str = Field(description="Customer's name.")
    payment_method_name: str = Field(description="Main tender's method.")
    staff_id: UUID | None = Field(description="Who served it.")
    currency: str = Field(description="ISO 4217 currency it was charged in.")
    currency_decimals: int = Field(description="The decimals of its currency as the server counts them (0 in JPY).")
    total: int = Field(description="Total in cents.")
    tax_total: int = Field(description="Tax in cents.")
    refunded_total: int = Field(description="Refunded in cents.")
    refundable_total: int = Field(description="Still refundable, in cents.")
    sessions_to_return: int = Field(
        description="Lines paid with a voucher whose session has not come back yet."
    )
    has_refunds: bool = Field(
        description="It has a refund, also one of no money (a voucher's session): it is refunded, never voided."
    )
    invoice_status: FiscalStatus = Field(
        description="Its fiscal document: issued, pending, unavailable or none; empty before Sales asked for it."
    )
    documents_pending: bool = Field(
        description="A fiscal document of it waits (its own, its void's or a refund's): «Issue now» issues it."
    )


SalePage = Page[SaleRow]


class PeriodIn(Schema):
    date_from: date | None = Field(
        None, description="From this business day (inclusive); empty = since always."
    )
    date_to: date | None = Field(
        None, description="Up to this business day (inclusive); empty = up to today."
    )


class StatsOut(Schema):
    count: int = Field(description="Tickets charged (voided ones aside).")
    total_revenue: int = Field(description="Revenue in cents, refunds taken off.")
    avg_ticket: int = Field(description="Average ticket in cents.")
    net_total: int = Field(description="Taxable base in cents.")
    tax_total: int = Field(description="Tax in cents.")
    discount_total: int = Field(description="Discounts given, in cents.")
    refunded_total: int = Field(description="Refunded in cents.")
    voided_count: int = Field(description="Sales voided.")
    tax_kind: TerritoryTaxKind | None = Field(
        description="The tax the period's sales were declared with, what its tax figure is named by: vat, igic "
        "or ipsi when they all declared it; empty when they declared more than one (or another tax). Without "
        "sales, the business territory's."
    )


class TodayOut(Schema):
    day: date = Field(description="Today's business day.")
    total: int = Field(description="Sold today, in cents.")
    tickets: int = Field(description="Tickets today.")


class DayTotal(Schema):
    day: date = Field(description="Business day.")
    total: int = Field(description="Sold that day, in cents.")


class LastDaysOut(Schema):
    rows: list[DayTotal] = Field(
        description="Seven days, oldest first, 0 on a day without sales."
    )


class StaffTotal(Schema):
    staff_id: UUID = Field(description="The member of Staff.")
    sales_count: int = Field(description="Sales where they served at least one line.")
    gross_total: int = Field(description="What their lines charged, in cents.")
    net_total: int = Field(description="Base of their lines, in cents.")
    tax_total: int = Field(description="Tax of their lines, in cents.")
    refunded_total: int = Field(
        description="What the refunds of those sales gave back on their lines, in cents."
    )
    total_revenue: int = Field(
        description="What their lines charged, refunds taken off, in cents: what their commission is on."
    )


class ByStaffOut(Schema):
    rows: list[StaffTotal] = Field(
        description="One row per professional, the one who sold most (refunds taken off) first."
    )


class BusinessDayOut(Schema):
    today: date = Field(description="Today in the business's time zone.")


# ── Voids and refunds ─────────────────────────────────────────────────────────────────────────────


class VoidIn(SaleRefIn):
    reason: Reason = Field(description="Why the sale is voided (mandatory).")


class AllocationIn(Closed):
    payment_id: UUID = Field(description="The tender of the sale the money comes off.")
    amount: PositiveCents = Field(description="What goes back on it, in cents.")
    to_method_id: UUID | None = Field(
        None,
        description="Another payment method to give it back by; empty = the tender's own.",
    )


class RefundLineIn(Closed):
    line_id: UUID = Field(description="A line of the sale that comes back.")
    quantity: Quantity | None = Field(
        None, description="How many units come back; empty = all that is left."
    )


class RefundIn(SaleRefIn):
    reason: Reason = Field(description="Why the money goes back (mandatory).")
    note: _text(500) = Field("", description="A note of the refund.")
    idempotency_key: AttemptKey | None = Field(
        None, description="The attempt's key: a retry with it never refunds twice."
    )
    allocations: list[AllocationIn] = Field(
        default_factory=list,
        max_length=MAX_PAYMENTS,
        title=gettext_noop("Refund amount"),
        description="How much goes back on each tender; none = no money (only the session of a voucher).",
    )
    lines: list[RefundLineIn] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        description="The lines that come back; none = only money. A line paid with a voucher gives its session back.",
    )


class RefundOut(Schema):
    already: bool = Field(description="True: this attempt had already been recorded.")
    refund_id: UUID = Field(description="The refund's id.")
    sale_id: UUID = Field(description="The sale.")
    total: int = Field(description="Refunded in cents.")
    fully_refunded: bool = Field(
        description="Whether the sale is now refunded in full."
    )
    invoice_status: FiscalStatus = Field(
        description="Its rectifying invoice, issued by Invoicing in the same refund: issued; none (no money "
        "back, nothing to rectify); pending (Invoicing refused now and issues it later); unavailable."
    )
    invoice_number: str = Field(description="The number of its rectifying invoice (RECT-2026-000001).")
    invoice_type: str = Field(description="R5 (of a ticket) or R1 (of an invoice); empty while none.")


class TenderOption(Schema):
    payment_id: UUID = Field(description="The tender.")
    position: int = Field(description="Order taken.")
    method_id: UUID = Field(description="Its method.")
    method_name: str = Field(description="Its method's name.")
    method_type: MethodType = Field(description="Its method's type.")
    charged: int = Field(description="Charged in cents.")
    refunded: int = Field(description="Already refunded on it, in cents.")
    remaining: int = Field(description="Still refundable on it, in cents.")
    refundable: bool = Field(
        description="Whether it can go back through its own method."
    )
    reason: Literal["", "already_refunded", "method_unavailable"] = Field(
        description="Why not, if it cannot."
    )


class LineOption(Schema):
    line_id: UUID = Field(description="The line.")
    name: str = Field(description="Its name.")
    unit: str = Field(description="Its unit.")
    quantity: Decimal = Field(description="Units sold.")
    returned: Decimal = Field(description="Units already back.")
    left: Decimal = Field(description="Units that can still come back.")
    line_total: int = Field(description="What the line charged, in cents.")
    is_gift: bool = Field(description="A comp.")
    paid_by_voucher: bool = Field(
        description="A voucher session paid it: returning it gives the session back."
    )
    voucher_name: str = Field(description="The voucher that paid it.")


class RefundOptionsOut(Schema):
    sale_id: UUID = Field(description="The sale.")
    number: str = Field(description="Its number.")
    status: SaleStatus = Field(description="Its status.")
    currency: str = Field(description="ISO 4217 currency it was charged in: what goes back goes in it.")
    currency_decimals: int = Field(description="The decimals of its currency as the server counts them (0 in JPY).")
    total: int = Field(description="Its total.")
    refunded_total: int = Field(description="Refunded so far.")
    refundable_total: int = Field(description="Still refundable.")
    tenders: list[TenderOption] = Field(description="One row per tender, always.")
    lines: list[LineOption] = Field(description="Its lines and what is left of each.")


class RefundRow(Schema):
    id: UUID = Field(description="The refund's id.")
    sale_id: UUID = Field(description="The sale.")
    total: int = Field(description="Refunded in cents.")
    reason: str = Field(description="Why.")
    note: str = Field(description="Note.")
    created_at: datetime = Field(description="When.")
    created_by: str = Field(description="Who.")
    invoice_status: FiscalStatus = Field(
        description="Its rectifying invoice: issued, pending (waits: «Issue now»), unavailable or none."
    )
    invoice_number: str = Field(description="The number of its rectifying invoice; empty while it has none.")
    invoice_type: str = Field(description="R5 (of a ticket) or R1 (of an invoice); empty while none.")


class RefundListOut(Schema):
    rows: list[RefundRow] = Field(description="The sale's refunds, newest first.")


class RefundByKeyIn(Closed):
    idempotency_key: AttemptKey = Field(description="The refund attempt's key.")


class RefundByKeyOut(Schema):
    found: bool = Field(description="Whether a refund was recorded with that key.")
    refund: RefundRow | None = Field(description="That refund.")


# ── Reactions ─────────────────────────────────────────────────────────────────────────────────────


class CustomerMergedIn(Schema):
    id: UUID = Field(description="The customer card that stays.")
    absorbed_id: UUID = Field(description="The card merged into it.")


class CustomerReassignOut(Schema):
    customer_id: UUID = Field(description="The card that stays.")
    moved: int = Field(description="Sales moved to it.")


class InvoiceSourceIn(Schema):
    """Where a document of Invoicing comes from (its WORKBOOK «Contrato del origen con Ventas»)."""

    model_config = ConfigDict(extra="ignore")

    type: str = Field(max_length=20, description="sale, manual, substitution, rectification, refund or void.")
    sale_id: UUID | None = Field(None, description="The sale it comes from (also its F3 and its rectifications).")
    refund_id: UUID | None = Field(None, description="The refund a rectifying invoice of a refund corrects.")
    void: bool = Field(False, description="True on the rectifying invoice of a void.")


class InvoiceIssuedIn(Schema):
    """Invoicing's notice of a document issued (``invoice.invoice.issued``; its other keys are ignored)."""

    model_config = ConfigDict(extra="ignore")

    invoice_id: UUID = Field(description="The document in Invoicing.")
    number: str = Field(max_length=60, description="Its number in its series.")
    invoice_type: str = Field(max_length=2, description="F1, F2, F3 or R1–R5.")
    source: InvoiceSourceIn | None = Field(
        None, description="Which charge, refund or void of Sales it comes from; none = not from Sales."
    )


class InvoiceRecordedOut(Schema):
    sale_id: UUID | None = Field(description="The sale that now knows its document.")
    recorded: bool = Field(description="Something was written now; false on a repeat or another document.")
