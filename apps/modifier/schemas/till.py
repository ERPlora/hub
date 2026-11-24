"""The till's reads: the groups a product carries, and the valuation of what was chosen for it."""

from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import model_validator

from apps.modifier.schemas.fields import Said, _Input
from apps.modifier.schemas.groups import _GroupFields
from base.allergens import AllergensOut

#: Picks valued at once: far beyond what a sheet holds.
MAX_PICKS = 100

SAY_WHICH_PRODUCT = _("Say which product: its id, or its SKU or name.")


class _Product(_Input):
    product_id: UUID | None = Field(None, description="The product's id.")
    product: Said | None = Field(
        None,
        description="The product's SKU or name, when its id is not known (e.g. said aloud).",
    )

    @model_validator(mode="after")
    def _product_named(self):
        if self.product_id is None and self.product is None:
            raise ValueError(str(SAY_WHICH_PRODUCT))
        return self


class TargetIn(_Product):
    pass


class ResolveIn(_Product):
    option_ids: list[UUID] = Field(
        default_factory=list,
        max_length=MAX_PICKS,
        description="The ids of the options chosen, in the order they were chosen; an option repeated is chosen "
        "that many times.",
    )


class TargetOptionOut(AllergensOut):
    id: UUID = Field(
        description="The option's id: what the till sends back when it is chosen."
    )
    name: str = Field(description="Name, as the customer reads it.")
    kitchen_name: str = Field(
        description="Name on the kitchen ticket; empty = the name."
    )
    price_delta: int = Field(
        description="Supplement in cents; negative = a discount; 0 = free.", json_schema_extra={"money": True}
    )
    tax_category_key: str | None = Field(
        description="Key of its own tax category; null = the dish's."
    )
    is_default: bool = Field(description="Comes chosen when the sheet opens.")


class TargetGroupOut(_GroupFields):
    options: list[TargetOptionOut] = Field(description="Its options, in their order.")


class TargetOut(Schema):
    product_id: UUID = Field(description="The product.")
    product_name: str = Field(description="The product's name.")
    groups: list[TargetGroupOut] = Field(
        description="The groups it carries (its own and its categories'), each once, by order and name; a group "
        "without options is left out."
    )


class PickOut(AllergensOut):
    option_id: UUID = Field(description="The option chosen.")
    group_id: UUID = Field(description="Its group.")
    group_name: str = Field(description="Its group's name.")
    name: str = Field(description="Its name, as the customer reads it (the receipt).")
    kitchen_name: str = Field(
        description="What the kitchen reads: its kitchen name, or its name."
    )
    price_delta: int = Field(description="Its supplement in cents, from the catalog.", json_schema_extra={"money": True})
    tax_category_key: str | None = Field(
        description="Key of its own tax category; null = the dish's."
    )
    own_line: bool = Field(
        description="True: it taxes differently from the product and is billed on a line of its own."
    )


class OwnLineOut(Schema):
    option_id: UUID = Field(description="The option billed on a line of its own.")
    group_id: UUID = Field(description="Its group.")
    name: str = Field(description="Its name, as the customer reads it (the receipt).")
    kitchen_name: str = Field(description="What the kitchen reads: its kitchen name, or its name.")
    tax_category_key: str = Field(description="Key of its own tax category: the line's.")
    price_delta: int = Field(description="Its unit price in cents, from the catalog (always more than zero).", json_schema_extra={"money": True})
    quantity: int = Field(
        description="How many per unit of the dish: an option chosen twice is one line of 2; Sales multiplies "
        "it by the dish line's quantity."
    )


class ResolveOut(Schema):
    product_id: UUID = Field(description="The product.")
    picks: list[PickOut] = Field(
        description="Each choice, valued, in the order it was chosen."
    )
    folded_delta: int = Field(
        description="Cents to add to the line's unit price: the picks not on a line of their own.",
        json_schema_extra={"money": True},
    )
    own_lines: list[OwnLineOut] = Field(
        description="The child lines of the dish line: one per option that taxes differently, with its quantity "
        "per unit of the dish."
    )
    kitchen_text: str = Field(
        description="What the kitchen ticket says under the dish: the kitchen names, «, »-joined."
    )
