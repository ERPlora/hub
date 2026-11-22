"""Schemas of the open checks (``sale.order.*``): opening one, its lines, splitting and joining, discounts and
sending it to the kitchen."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.sale.schemas.fields import (
    A_BOOKING,
    A_CHECK,
    A_CHECK_LINE,
    A_MEMBER,
    A_VOUCHER,
    COMBO_LINES,
    LINE,
    MAX_LINES,
    OPEN_LINES,
    SERVICE_LINES,
    Cents,
    CheckLineId,
    Closed,
    Label,
    Note,
    OrderStatus,
    Page,
    PageIn,
    Percent,
    TypedQuantity,
    _text,
)
from apps.sale.schemas.lines import (
    ComboLineFields,
    ComboLineIn,
    OpenLineFields,
    OpenLineIn,
    ProductLineIn,
    ServiceLineFields,
    ServiceLineIn,
)
from base.allergens import AllergyInDishOut, AllergyOut

SERVED_BY = (
    "Who serves the check (a member of Staff): the kitchen ticket names them and its sales are theirs; empty = whoever "
    "holds the session."
)


class OrderOpenIn(Closed):
    label: Label = Field("", description="The check's title, e.g. Ana — terrace.")
    notes: _text(1000) = Field("", description="Notes of the check.")
    appointment_id: UUID | None = Field(
        None, description="The appointment (Appointments) this check charges.", json_schema_extra=A_BOOKING
    )
    staff_id: UUID | None = Field(None, description=SERVED_BY, json_schema_extra=A_MEMBER)
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
    order_id: UUID = Field(description="The open check's id.", json_schema_extra=A_CHECK)


class OrderAddLineIn(ProductLineIn):
    order_id: UUID = Field(description="The open check's id.", json_schema_extra=A_CHECK)


class OrderAddOpenLineIn(OpenLineFields):
    order_id: UUID = Field(description="The open check's id.", json_schema_extra=A_CHECK)


class OrderAddServiceLineIn(ServiceLineFields):
    order_id: UUID = Field(description="The open check's id.", json_schema_extra=A_CHECK)


class OrderAddComboLineIn(ComboLineFields):
    order_id: UUID = Field(description="The open check's id.", json_schema_extra=A_CHECK)


class OrderLineRefIn(Closed):
    order_id: UUID = Field(description="The open check's id.", json_schema_extra=A_CHECK)
    line_id: UUID = Field(title=LINE, description="The line's id.", json_schema_extra=A_CHECK_LINE)


class OrderApplyVoucherIn(OrderLineRefIn):
    grant_id: UUID = Field(
        title=gettext_noop("Voucher"),
        description="The voucher sold (Services) whose session pays the line: one of the customer's, read with "
        "service.grant.tender_options.",
        json_schema_extra=A_VOUCHER,
    )


class OrderUpdateLineIn(OrderLineRefIn):
    quantity: TypedQuantity | None = Field(None, description="New quantity; empty keeps it.")
    is_gift: bool | None = Field(
        None, description="True: a comp; false: charged again; empty keeps it."
    )
    gift_reason: _text(200) | None = Field(None, description="Why it is a comp.")
    notes: Note | None = Field(
        None, description="New note; empty text clears it; absent keeps it."
    )


class OrderSetLineStaffIn(OrderLineRefIn):
    staff_id: UUID | None = Field(
        description="Who did it (a member of Staff); empty = the check's professional.", json_schema_extra=A_MEMBER
    )


class OrderVoidLineIn(OrderLineRefIn):
    reason: _text(255, 1) = Field(
        description="Why a line already sent to the kitchen is voided."
    )


class OrderSplitIn(Closed):
    order_id: UUID = Field(description="The check to split.", json_schema_extra=A_CHECK)
    line_ids: list[CheckLineId] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        title=gettext_noop("Lines to move"),
        description="Lines that move to the new check; none = a blank one.",
    )
    label: Label = Field("", description="The new check's title.")


class OrderMergeIn(Closed):
    from_order_id: UUID = Field(
        title=gettext_noop("From check"),
        description="The check that is absorbed (it ends voided).",
        json_schema_extra=A_CHECK,
    )
    to_order_id: UUID = Field(
        title=gettext_noop("Into check"),
        description="The check that stays with every line.",
        json_schema_extra=A_CHECK,
    )


class OrderSetDiscountIn(Closed):
    order_id: UUID = Field(description="The open check's id.", json_schema_extra=A_CHECK)
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
    order_id: UUID = Field(description="The open check's id.", json_schema_extra=A_CHECK)
    label: Label = Field(description="Its title, e.g. Table 4 or Ana — terrace.")


class OrderSetStaffIn(Closed):
    order_id: UUID = Field(description="The open check's id.", json_schema_extra=A_CHECK)
    staff_id: UUID | None = Field(description=SERVED_BY, json_schema_extra=A_MEMBER)


class OrderSetAppointmentIn(Closed):
    order_id: UUID = Field(description="The open check's id.", json_schema_extra=A_CHECK)
    appointment_id: UUID | None = Field(
        description="The appointment it charges; empty unlinks it.", json_schema_extra=A_BOOKING
    )


class OrderFireIn(Closed):
    order_id: UUID = Field(
        description="The open check whose pending lines go to the kitchen.", json_schema_extra=A_CHECK
    )
    label: Label = Field(
        "", description="What the kitchen reads as the check's name, e.g. Table 4."
    )
    # The kitchen's own words: it requires Sales and the mark only reads its models' metadata, no data of it.
    channel: Literal["dine_in", "takeaway", "delivery"] = Field(
        "dine_in",
        title=gettext_noop("Order type"),
        description="dine_in, takeaway or delivery.",
        json_schema_extra={"choices_of": "kitchen.order_type"},
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


class ComboDishOut(AllergyInDishOut):
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


class OrderLineOut(AllergyOut):
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
    staff_id: UUID | None = Field(None, description=SERVED_BY)
    staff_name: str = Field("", description="Their name, as Staff said it when they were chosen; empty for «me».")
    discount_percent: Decimal = Field(description="Ticket discount in %.")
    discount_amount: int = Field(description="Fixed ticket discount in cents.", json_schema_extra={"money": True})
    discount_approved: bool = Field(
        description="A manager approved a ticket discount over the cap."
    )
    provisional_total: int = Field(
        description="Σ of its lines' amounts, before the ticket discount (provisional).",
        json_schema_extra={"money": True},
    )
    version: int = Field(
        description="Goes up with every change: a charge sent with an older one is refused."
    )
    lines_count: int = Field(description="How many lines are left to charge.")
    created_at: datetime = Field(description="When it was opened.")
    updated_at: datetime = Field(description="When it last changed.")
    lines: list[OrderLineOut] = Field(description="The lines left to charge, in order.")
    merged_into_id: UUID | None = Field(
        None,
        description="A check joined with another (sale.order.merge) ends voided and names here the check that stays; "
        "null otherwise.",
    )
    already: bool = Field(
        False,
        description="Opening a check of an appointment that already has one open answers that one: true, "
        "nothing was added to it.",
    )


class OrderRow(Schema):
    id: UUID = Field(description="The check's id.")
    status: OrderStatus = Field(description="open, completed or voided.")
    label: str = Field(description="Title.")
    provisional_total: int = Field(description="Provisional total in cents.", json_schema_extra={"money": True})
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
