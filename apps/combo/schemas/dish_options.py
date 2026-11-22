"""The options of Modifiers chosen for a dish of a menu, as Menus takes them to price the line and gives them back."""

from uuid import UUID

from ninja import Field, Schema
from pydantic import ConfigDict

#: As many options as one dish may carry (Sales' own ceiling for a line).
MAX_DISH_OPTIONS = 100


class DishOptionIn(Schema):
    """An option of a dish as ``modifier.selection.resolve`` valued it for the dish's product: Menus adds its price and
    splits it, and does not ask Modifiers again."""

    model_config = ConfigDict(extra="forbid")

    option_id: UUID = Field(description="The option of Modifiers.")
    name: str = Field(max_length=200, description="Its name, as the ticket prints it.")
    kitchen_name: str = Field(max_length=200, description="Its name for the kitchen.")
    price_delta: int = Field(
        ge=-10_000_000,
        le=10_000_000,
        description="Its price in cents, per pick of the dish.",
        json_schema_extra={"money": True},
    )
    tax_category_key: str | None = Field(None, max_length=80, description="Its own tax category, if it has one.")
    own_line: bool = Field(False, description="True: it taxes apart from its dish (another tax category).")
    allergens: list[str] = Field(default_factory=list, max_length=20, description="The allergens it adds to the dish.")


class DishOptionOut(Schema):
    option_id: UUID
    name: str
    kitchen_name: str
    price_delta: int = Field(description="Its price in cents, per pick of the dish.")
    tax_category_key: str | None = Field(description="Its own tax category, as Modifiers gave it.")
    own_line: bool
    allergens: list[str]
    line_tax_category_key: str | None = Field(
        description="The tax category of its own line when the menu is split; null when it goes inside its dish."
    )
    amount: int | None = Field(description="Its part of one menu's amount, in cents, when it has a line of its own.")
