"""Input and output schemas of Online orders' operations (OpenAPI, live params, 422 per field).

A table is said as Tables says it (``apps.table.schemas.TableRefIn``: its id, or its number and, if the number
repeats, its zone), so the assistant's card names it as the floor plan does. The table's page names it by the code its
QR carries, and reads only what a customer may see of the menu: never a cost, a stock, a tax or what the kitchen reads."""

from datetime import datetime
from uuid import UUID

from ninja import Field, Schema
from pydantic import ConfigDict, model_validator

from base.allergens import AllergensOut

#: A price in the currency's minor unit, which the page writes in the business's money.
MONEY = {"money": True}


class TableCodeListIn(Schema):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(50, ge=1, le=100, description="How many tables to return (1 to 100).")
    offset: int = Field(0, ge=0, description="How many tables to skip, to read the next pages.")


class TableCodeOut(Schema):
    table_id: UUID = Field(description="The table's id, in Tables.")
    table: str = Field(description="The table as the floor plan names it: its number with its zone («5 (Terrace)»).")
    number: str = Field(description="The table's number.")
    zone_name: str | None = Field(description="The table's zone, if it has one.")
    code: str | None = Field(description="The code its QR carries; none until its QR is generated the first time.")
    url: str | None = Field(description="The address of the table's page, which its QR opens; none without a code.")
    issued_at: datetime | None = Field(description="When its code was generated; none without a code.")


class TableCodePage(Schema):
    rows: list[TableCodeOut] = Field(description="The tables of this page, in the floor plan's order.")
    total: int = Field(description="How many tables there are, across every page.")
    limit: int = Field(description="The page size asked for.")
    offset: int = Field(description="The tables skipped before this page.")


class PublicCodeIn(Schema):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=32, description="The code the table's QR carries.")


class PublicOptionsIn(PublicCodeIn):
    product_id: UUID = Field(description="A dish of the menu.")


class MenuItemOut(AllergensOut):
    id: UUID = Field(description="The dish, a product of Inventory.")
    name: str = Field(description="Its name.")
    description: str = Field(description="What it is, under its name; empty: nothing said.")
    price: int = Field(description="Its price.", json_schema_extra=MONEY)
    image_url: str = Field(description="Where its photo is served; empty: it has none.")


class MenuGroupOut(Schema):
    name: str = Field(description="The category's name; empty for the dishes in none.")
    items: list[MenuItemOut] = Field(description="Its dishes, by name.")


class MenuChoiceOut(AllergensOut):
    id: UUID = Field(description="The dish as the set menu offers it: what the order names when it is picked.")
    name: str = Field(description="The dish one picks.")
    price_delta: int = Field(description="What picking it adds to the menu's price.", json_schema_extra=MONEY)


class MenuCourseOut(Schema):
    id: UUID = Field(description="The course.")
    name: str = Field(description="The course («Starters»).")
    min_choices: int = Field(description="Dishes to pick at least.")
    max_choices: int = Field(description="Dishes to pick at most.")
    allow_repeat: bool = Field(description="Whether one dish may be picked more than once.")
    choices: list[MenuChoiceOut] = Field(description="The dishes on offer, those sold out left out.")


class MenuComboOut(Schema):
    id: UUID = Field(description="The menu, of Menus and combos.")
    name: str = Field(description="Its name.")
    price: int = Field(description="Its closed price.", json_schema_extra=MONEY)
    image_url: str = Field(description="Where its photo is served; empty: it has none.")
    courses: list[MenuCourseOut] = Field(description="Its courses, in their order.")


class PublicMenuOut(Schema):
    business_name: str = Field(description="The business's name, as erplora.com registered it; empty in a demo.")
    table_number: str = Field(description="The table's number.")
    zone_name: str | None = Field(description="The table's zone, if it has one.")
    groups: list[MenuGroupOut] = Field(description="The dishes on sale shown on the menu, by category in their order.")
    combos: list[MenuComboOut] = Field(description="The menus on sale; none while Menus and combos is off.")


class OptionOut(AllergensOut):
    id: UUID = Field(description="The option: what the order names when it is chosen.")
    name: str = Field(description="The option («Aioli»).")
    price_delta: int = Field(description="What it adds to the dish's price.", json_schema_extra=MONEY)


class OptionGroupOut(Schema):
    id: UUID = Field(description="The group.")
    name: str = Field(description="The group («Sauces»).")
    min_choices: int = Field(description="Options to choose at least; 1 or more = required.")
    max_choices: int = Field(description="Options to choose at most; 0 = no ceiling.")
    allow_repeat: bool = Field(description="Whether one option may be chosen more than once.")
    options: list[OptionOut] = Field(description="Its options, in their order.")


class PublicOptionsOut(Schema):
    product_id: UUID = Field(description="The dish.")
    groups: list[OptionGroupOut] = Field(description="Its modifier groups; none while Modifiers is off.")


#: The most lines an order sends, and the most options or set-menu dishes a line names.
MAX_LINES = 50
MAX_PICKS = 20
#: The most units of one line.
MAX_QUANTITY = 20
ONE_THING = "A line is a dish (product_id, with its option_ids) or a set menu (combo_id, with its choices)."


class SendChoiceIn(Schema):
    model_config = ConfigDict(extra="forbid")

    option_id: UUID = Field(description="A dish of a set menu's course, as the menu names it.")
    quantity: int = Field(1, ge=1, le=MAX_QUANTITY, description="How many times it is picked in one set menu.")


class SendLineIn(Schema):
    """A dish or a set menu as the customer picked it: by ids only, never a price."""

    model_config = ConfigDict(extra="forbid")

    product_id: UUID | None = Field(None, description="A dish of the menu.")
    option_ids: list[UUID] = Field(
        default_factory=list, max_length=MAX_PICKS, description="The dish's options chosen, in the order chosen."
    )
    combo_id: UUID | None = Field(None, description="A set menu of the menu.")
    choices: list[SendChoiceIn] = Field(
        default_factory=list, max_length=MAX_PICKS, description="The set menu's dishes picked, course by course."
    )
    quantity: int = Field(1, ge=1, le=MAX_QUANTITY, description="How many of it.")
    notes: str = Field("", max_length=200, description="A note for the kitchen («no salt»).")

    @model_validator(mode="after")
    def _one_thing(self):
        dish = self.product_id is not None and not self.choices
        set_menu = self.combo_id is not None and not self.option_ids
        if (self.product_id is None) == (self.combo_id is None) or not (dish or set_menu):
            raise ValueError(ONE_THING)
        return self


class PublicSendIn(PublicCodeIn):
    lines: list[SendLineIn] = Field(min_length=1, max_length=MAX_LINES, description="What the table orders.")


class PublicSentOut(Schema):
    id: UUID = Field(description="The order.")
    status: str = Field(description="pending: it waits for the staff to confirm it.")
    total: int = Field(description="What it comes to, as the server priced it.", json_schema_extra=MONEY)
