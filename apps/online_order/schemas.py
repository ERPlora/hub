"""Input and output schemas of Online orders' operations (OpenAPI, live params, 422 per field).

A table is said as Tables says it (``apps.table.schemas.tables.TableRefIn``: its id, or its number and, if the number
repeats, its zone), so the assistant's card names it as the floor plan does. The table's page names it by the code its
QR carries, and reads only what a customer may see of the menu: never a cost, a stock, a tax or what the kitchen reads."""

from datetime import datetime
from uuid import UUID

from ninja import Field, Schema
from pydantic import ConfigDict

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
    name: str = Field(description="The dish one picks.")
    price_delta: int = Field(description="What picking it adds to the menu's price.", json_schema_extra=MONEY)


class MenuCourseOut(Schema):
    name: str = Field(description="The course («Starters»).")
    min_choices: int = Field(description="Dishes to pick at least.")
    max_choices: int = Field(description="Dishes to pick at most.")
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
    name: str = Field(description="The option («Aioli»).")
    price_delta: int = Field(description="What it adds to the dish's price.", json_schema_extra=MONEY)


class OptionGroupOut(Schema):
    name: str = Field(description="The group («Sauces»).")
    min_choices: int = Field(description="Options to choose at least; 1 or more = required.")
    max_choices: int = Field(description="Options to choose at most; 0 = no ceiling.")
    options: list[OptionOut] = Field(description="Its options, in their order.")


class PublicOptionsOut(Schema):
    product_id: UUID = Field(description="The dish.")
    groups: list[OptionGroupOut] = Field(description="Its modifier groups; none while Modifiers is off.")
