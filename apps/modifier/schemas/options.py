"""The options of a group: how one is named, what one is made, recovered or changed with, and how one reads back."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field
from pydantic import model_validator

from apps.modifier.schemas.fields import (
    A_GROUP,
    A_GROUP_BY_NAME,
    AN_OPTION,
    AN_OPTION_BY_NAME,
    KITCHEN_TICKET_NAME,
    OPTION,
    OWN_TAX_CATEGORY,
    SAY_WHICH_GROUP,
    Delta,
    KitchenName,
    Name,
    Order,
    PageIn,
    Said,
    Search,
    TaxKey,
    _Input,
)
from apps.tax.schemas import A_TAX_CATEGORY
from base.allergens import AllergensIn, AllergensOut, AllergensPatchIn
from base.recovery import RecoveredOut
from base.schemas.assistant import unless_given

SAY_WHICH_OPTION = _("Say which option: its id, or its name.")

OptionSort = Literal[
    "sort_order", "-sort_order", "name", "-name", "price_delta", "-price_delta"
]


class _OwningGroup(_Input):
    """The group an option belongs to or a link hangs: by ``group_id`` or by its name (``group``)."""

    group_id: UUID | None = Field(None, description="The group's id.", json_schema_extra=A_GROUP)
    group: Said | None = Field(
        None,
        description="The group's name, when its id is not known (e.g. «Extras»).",
        json_schema_extra=unless_given(A_GROUP_BY_NAME, "group_id"),
    )

    @model_validator(mode="after")
    def _group_named(self):
        if self.group_id is None and self.group is None:
            raise ValueError(str(SAY_WHICH_GROUP))
        return self


class OptionListIn(PageIn):
    group_id: UUID | None = Field(None, description="Only the options of this group.")
    group: Said | None = Field(
        None, description="Only the options of the group with this name."
    )
    search: Search | None = Field(
        None, description="Part of the name or of the kitchen name."
    )
    sort: OptionSort = Field(
        "sort_order",
        description="Order (by order then name by default); a leading '-' reverses it.",
    )


class OptionRefIn(_Input):
    id: UUID | None = Field(None, title=OPTION, description="The option's id.", json_schema_extra=AN_OPTION)
    option: Said | None = Field(
        None,
        title=OPTION,
        description="The option's name, when its id is not known (e.g. «No onion»).",
        json_schema_extra=unless_given(AN_OPTION_BY_NAME, "id"),
    )
    group_id: UUID | None = Field(
        None,
        description="Its group's id, when two groups have an option with that name.",
        json_schema_extra=A_GROUP,
    )
    group: Said | None = Field(
        None,
        description="Its group's name, when two groups have an option with that name.",
        json_schema_extra=unless_given(A_GROUP_BY_NAME, "group_id"),
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and self.option is None:
            raise ValueError(str(SAY_WHICH_OPTION))
        return self


class _OptionFields(_Input):
    """What an option is, its group aside."""

    name: Name = Field(
        description="The option's name, unique in its group (e.g. «Cheese»)."
    )
    kitchen_name: KitchenName = Field(
        "",
        title=KITCHEN_TICKET_NAME,
        description="Its name on the kitchen ticket (e.g. «+CHEESE»); empty = the name.",
    )
    price_delta: Delta = Field(
        description="Its supplement in cents: positive charges more, negative is a discount, 0 is free.",
    )
    tax_category_key: TaxKey = Field(
        "",
        title=OWN_TAX_CATEGORY, json_schema_extra=A_TAX_CATEGORY,
        description="Only when it taxes differently from the dish: the key (e.g. product.generic) or the name of "
        "its own tax category, billed on a line of its own; empty = the dish's.",
    )
    is_default: bool = Field(
        False, description="True: it comes chosen when the till opens the group."
    )
    sort_order: Order = Field(
        0, description="Where the option shows in its group: lower first."
    )


# Bases in this order keep the group's fields first in the schema, as they have always come, and the allergens last.
class OptionIn(AllergensIn, _OptionFields, _OwningGroup):
    pass


class OptionOfCopyIn(AllergensIn, _OptionFields):
    """An option of a group of a separate copy, as ``modifier.option.create`` takes it but its group."""


class OptionPatchIn(AllergensPatchIn, OptionRefIn):
    """Only the fields sent are changed; ``null`` leaves one as it is; ``tax_category_key: ""`` clears it."""

    name: Name | None = Field(None, description="New name.")
    kitchen_name: KitchenName | None = Field(
        None, title=KITCHEN_TICKET_NAME, description="New kitchen name; empty = the name."
    )
    price_delta: Delta | None = Field(
        None, description="New supplement in cents (negative = a discount)."
    )
    tax_category_key: TaxKey | None = Field(
        None, title=OWN_TAX_CATEGORY, json_schema_extra=A_TAX_CATEGORY,
        description="New own tax category (key or name); empty = back to the dish's.",
    )
    is_default: bool | None = Field(
        None, description="Whether it comes chosen when the till opens the group."
    )
    sort_order: Order | None = Field(None, description="New order.")


class OptionOut(AllergensOut):
    id: UUID = Field(description="The option's id.")
    group_id: UUID = Field(description="Its group.")
    group_name: str = Field(description="Its group's name.")
    name: str = Field(description="Name, as the customer reads it.")
    kitchen_name: str = Field(
        description="Name on the kitchen ticket; empty = the name."
    )
    price_delta: int = Field(
        description="Supplement in cents; negative = a discount.",
        json_schema_extra={"money": True},
    )
    tax_category_key: str | None = Field(
        description="Key of its own tax category; null = the dish's."
    )
    tax_category_name: str | None = Field(
        description="Its own tax category's name, in the reader's language."
    )
    is_default: bool = Field(description="Comes chosen when the till opens the group.")
    sort_order: int = Field(description="Order in its group.")
    created_at: datetime = Field(description="When it was created.")
    updated_at: datetime = Field(description="When it was last changed.")


class OptionRecoveredOut(OptionOut, RecoveredOut):
    """An option added again from a separate copy, and why it came back without being chosen by default."""


class OptionDetailOut(OptionOut):
    label: str = Field(description="How a person tells it apart: its name and its group, «Large (Drinks)».")
