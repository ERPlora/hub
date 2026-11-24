"""The till: the menus on sale, what a customer picks of one, and what the menu charges once priced."""

import json
from typing import Annotated, Any, Literal
from uuid import UUID

from ninja import Field, Schema
from pydantic import BeforeValidator, model_validator

from apps.combo.models import MAX_PICKS
from apps.combo.schemas.dish_options import MAX_DISH_OPTIONS, DishOptionIn, DishOptionOut
from apps.combo.schemas.fields import (
    MAX_GROUPS,
    MAX_OPTIONS,
    NOT_A_PICK,
    SAY_WHICH_PICK,
    Cents,
    In,
    Page,
    PageIn,
    Reference,
    Search,
    SupplyKind,
    _named,
)
from apps.combo.schemas.references import ComboRefIn


class ForSaleIn(PageIn):
    limit: int = Field(
        50, ge=1, le=50, description="How many menus to return (1 to 50)."
    )
    search: Search | None = Field(
        None, description="Text to look for in the menu's name."
    )


class ChoiceIn(In):
    option_id: UUID | None = Field(None, description="Id of the choice picked.")
    product: Reference | None = Field(
        None,
        description="SKU or name of the product picked, without the choice's id: in the person's own words, never translated.",
    )
    group: Reference | None = Field(
        None, description="The course it is picked in, when the product is in several."
    )
    quantity: int = Field(1, ge=1, le=MAX_PICKS, description="How many times it is picked (two coffees: 2).")
    options: list[DishOptionIn] = Field(
        default_factory=list,
        max_length=MAX_DISH_OPTIONS,
        description="The options of Modifiers chosen for the dish, as modifier.selection.resolve valued them: each "
        "pick of the dish carries them all, and their price adds to the menu's amount.",
    )

    @model_validator(mode="after")
    def _pick_named(self):
        _named(self.option_id, self.product, SAY_WHICH_PICK)
        return self


def _json_pick(value: Any) -> Any:
    """A pick in a query string is a JSON object per ``choices`` (``{"product": "Flan"}``)."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            raise ValueError(str(NOT_A_PICK)) from None
    return value


Pick = Annotated[ChoiceIn, BeforeValidator(_json_pick)]


class ResolveIn(ComboRefIn):
    choices: list[Pick] = Field(
        default_factory=list,
        max_length=MAX_GROUPS * MAX_OPTIONS,
        description="What the customer picked.",
    )
    amount: Cents | None = Field(
        None,
        description="The amount ordered on an open check, in cents: it is split instead of today's price, and "
        "the dishes are not asked to be on offer again.",
    )
    channel: Literal["dine_in", "takeaway", "delivery"] | None = Field(
        None,
        description="How this line is sold (Ventas' order channel): dine_in is billed as eaten in, takeaway and "
        "delivery as to take away; empty follows the menu's own setting.",
    )


class SaleOptionOut(Schema):
    id: UUID
    product_id: UUID
    product_name: str
    sku: str
    price_delta: int = Field(json_schema_extra={"money": True})


class SaleGroupOut(Schema):
    id: UUID
    name: str
    min_choices: int
    max_choices: int
    allow_repeat: bool
    options: list[SaleOptionOut]


class SaleComboOut(Schema):
    id: UUID
    name: str
    kitchen_name: str
    price: int = Field(json_schema_extra={"money": True})
    supply_kind: SupplyKind
    sort_order: int
    image: str = Field(
        description="Its image: catalog:<folder>/<name> of the shared library, file:<name> of a photo of its own, "
        "or empty."
    )
    image_url: str = Field(description="Where the Hub serves its image; empty: it has none (show its initials).")
    groups: list[SaleGroupOut]


SaleComboPage = Page[SaleComboOut]


class ComponentOut(Schema):
    option_id: UUID
    group_id: UUID
    group_name: str
    product_id: UUID
    product_name: str
    sku: str
    category_id: UUID | None = Field(description="The product's first category, for the kitchen's routing.")
    is_service: bool = Field(description="A service product never moves stock.")
    quantity: int = Field(description="Picks of it in one menu.")
    price_delta: int = Field(description="Supplement of one pick, in cents.", json_schema_extra={"money": True})
    catalog_price: int = Field(description="The product's catalogue price, in cents: the weight of the split.", json_schema_extra={"money": True})
    tax_category_key: str | None
    amount: int | None = Field(description="Its part of the menu's amount, in cents, when the menu is split.", json_schema_extra={"money": True})
    options: list[DishOptionOut] = Field(description="The options of Modifiers chosen for it, in the order chosen.")


class ResolvedOut(Schema):
    combo_id: UUID
    name: str
    kitchen_name: str
    supply_kind: SupplyKind
    price: int = Field(description="Today's closed price, in cents.", json_schema_extra={"money": True})
    supplements: int = Field(description="The supplements of the picks, in cents.", json_schema_extra={"money": True})
    amount: int = Field(
        description="What the menu charges: the amount ordered, or price plus supplements plus the dishes' options.",
        json_schema_extra={"money": True},
    )
    split: bool = Field(
        description="true: one sale line per component, each at its own tax category and amount."
    )
    tax_category_key: str | None = Field(
        description="The tax category of the single line; null when split."
    )
    components: list[ComponentOut]
