"""Input and output schemas of the modifier app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. Supplements
travel in cents (integers, negative = a discount). A group is named by its id or its name («Sauces»),
an option by its id or its name and, when two groups have one with that name, its group; a product by
its id, SKU or name and a category by its id or name, as Inventory reads them. Inputs refuse a field
they do not have (an unknown filter is a 422); only a reaction takes Inventory's payload as it comes.
"""

from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import (
    ConfigDict,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

from apps.modifier.models import MAX_CHOICES, MAX_DELTA, NAME_MAX_LENGTH
from base.schemas import names, unless_given

T = TypeVar("T")

#: Picks valued at once: far beyond what a sheet holds.
MAX_PICKS = 100

SAY_WHICH_GROUP = _("Say which group: its id, or its name.")
SAY_WHICH_OPTION = _("Say which option: its id, or its name.")
SAY_WHICH_CATEGORY = _("Say which category: its id, or its name.")
SAY_WHICH_PRODUCT = _("Say which product: its id, or its SKU or name.")
SAY_ONE_TARGET = _("Say one product or one category: its id, or its name.")
SAY_WHICH_LINK = _("Say which link: its id, or the group and the product or category.")
MAX_BELOW_MIN = _("The maximum cannot be below the minimum (0 = no ceiling).")

# How the Modifiers screens name the data the models do not (the assistant's card names each datum by its title).
GROUP = gettext_noop("Group")
OPTION = gettext_noop("Option")
APPLIES_TO = gettext_noop("Applies to")
OWN_TAX_CATEGORY = gettext_noop("Own tax category")
#: The forms' name for it; the model's own, «kitchen name», is the Django admin's (hub#958).
KITCHEN_TICKET_NAME = gettext_noop("Kitchen ticket name")

# The assistant's card names the record a write acts on by these reads (base/assistant.py ``REFERS``), run as whoever
# asks, never by its id: a group, a product and a category by their names; an option by its name and its group, because
# two groups may have an option with one name; a link by its group and what it hangs from.
A_GROUP = names("modifier.group.get")
# A group said by its name, when its id is not known: a group belongs to nothing, so the card reads it by that name
# alone, as the write will find it, and shows the group the write acts on («Salsas picantes» when the person said
# «salsa», hub#1218); words it cannot read (two groups fit, none does) it says as said, never off the card, so adding
# an option or applying a group, which cannot check it, reads it too (hub#1245). Beside the id the write takes its
# record by instead (the group's, or the link's), the card neither reads nor shows the name, which the write does not
# use (``unless_given``, hub#1250); an option by its id is looked for in the group said, so that one is read.
A_GROUP_BY_NAME = names("modifier.group.get", by="group", as_said=True)
AN_OPTION = names("modifier.option.get", name=("label",))
# An option said by its name: two groups may have an option with one name, so the card reads it with its group when it
# is told, as the write finds it, and says it as said when it cannot (hub#1245).
AN_OPTION_BY_NAME = names(
    "modifier.option.get", by="option", within=("group_id", "group"), name=("label",), as_said=True
)
A_LINK = names("modifier.link.get", name=("label",))
A_PRODUCT = names("inventory.product.get")
A_CATEGORY = names("modifier.category.get")

GroupSort = Literal[
    "name",
    "-name",
    "sort_order",
    "-sort_order",
    "min_choices",
    "-min_choices",
    "max_choices",
    "-max_choices",
    "option_count",
    "-option_count",
    "link_count",
    "-link_count",
]
OptionSort = Literal[
    "sort_order", "-sort_order", "name", "-name", "price_delta", "-price_delta"
]
TargetKind = Literal["product", "category"]


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Name = _text(NAME_MAX_LENGTH, 1)
KitchenName = _text(NAME_MAX_LENGTH)
#: How a person names a group, an option, a product (SKU or name) or a category.
Said = _text(NAME_MAX_LENGTH, 1)
TaxKey = _text(120)
Choices = Annotated[int, Field(ge=0, le=MAX_CHOICES)]
Order = Annotated[int, Field(ge=0, le=2_147_483_647)]
Delta = Annotated[int, Field(ge=-MAX_DELTA, le=MAX_DELTA, json_schema_extra={"money": True})]
Search = _text(NAME_MAX_LENGTH)


class _Input(Schema):
    model_config = ConfigDict(extra="forbid")


# Pages: every list is paginated, limit ≤ 100.


class PageIn(_Input):
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


# References: by id, or as a person says it.


class GroupRefIn(_Input):
    id: UUID | None = Field(None, title=GROUP, description="The group's id.", json_schema_extra=A_GROUP)
    group: Said | None = Field(
        None,
        description="The group's name, when its id is not known (e.g. «Sauces»).",
        json_schema_extra=unless_given(A_GROUP_BY_NAME, "id"),
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and self.group is None:
            raise ValueError(str(SAY_WHICH_GROUP))
        return self


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


# Inputs: groups


class GroupListIn(PageIn):
    search: Search | None = Field(
        None, description="Part of the name or of the kitchen name."
    )
    name: Search | None = Field(None, description="Part of the name.")
    required: bool | None = Field(
        None,
        description="Only required groups (true: minimum 1 or more) or only optional ones (false).",
    )
    sort: GroupSort = Field(
        "sort_order",
        description="Order (by order then name by default); a leading '-' reverses it.",
    )


class GroupIn(_Input):
    name: Name = Field(
        description="The group's name, unique in the business (e.g. «Sauces»)."
    )
    kitchen_name: KitchenName = Field(
        "", title=KITCHEN_TICKET_NAME, description="Its name on the kitchen ticket; empty = the name."
    )
    min_choices: Choices = Field(
        0,
        description="How many options must be chosen at least; 1 or more makes the group required.",
    )
    max_choices: Choices = Field(
        0,
        description="How many options may be chosen at most; 0 = no ceiling, otherwise not below the minimum.",
    )
    allow_repeat: bool = Field(
        False, description="True: the same option may be chosen more than once."
    )
    sort_order: Order = Field(
        0, description="Where the group shows in the till: lower first."
    )

    @field_validator("max_choices")
    @classmethod
    def _not_below_min(cls, value: int, info: ValidationInfo) -> int:
        minimum = info.data.get("min_choices")
        if value and minimum is not None and value < minimum:
            raise ValueError(str(MAX_BELOW_MIN))
        return value


class GroupPatchIn(GroupRefIn):
    """Only the fields sent are changed; ``null`` leaves one as it is."""

    name: Name | None = Field(None, description="New name.")
    kitchen_name: KitchenName | None = Field(
        None, title=KITCHEN_TICKET_NAME, description="New kitchen name; empty = the name."
    )
    min_choices: Choices | None = Field(
        None, description="New minimum; 1 or more makes it required."
    )
    max_choices: Choices | None = Field(
        None, description="New maximum; 0 = no ceiling."
    )
    allow_repeat: bool | None = Field(
        None, description="Whether the same option may be chosen more than once."
    )
    sort_order: Order | None = Field(None, description="New order.")


# Inputs: options


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


class OptionIn(_OwningGroup):
    name: Name = Field(
        description="The option's name, unique in its group (e.g. «Cheese»)."
    )
    kitchen_name: KitchenName = Field(
        "",
        title=KITCHEN_TICKET_NAME,
        description="Its name on the kitchen ticket (e.g. «+CHEESE»); empty = the name.",
    )
    price_delta: Delta = Field(
        0,
        description="Its supplement in cents: positive charges more, negative is a discount, 0 is free.",
    )
    tax_category_key: TaxKey = Field(
        "",
        title=OWN_TAX_CATEGORY,
        description="Only when it taxes differently from the dish: the key (e.g. product.generic) or the name of "
        "its own tax category, billed on a line of its own; empty = the dish's.",
    )
    is_default: bool = Field(
        False, description="True: it comes chosen when the till opens the group."
    )
    sort_order: Order = Field(
        0, description="Where the option shows in its group: lower first."
    )


class OptionPatchIn(OptionRefIn):
    """Only the fields sent are changed; ``null`` leaves one as it is; ``tax_category_key: ""`` clears it."""

    name: Name | None = Field(None, description="New name.")
    kitchen_name: KitchenName | None = Field(
        None, title=KITCHEN_TICKET_NAME, description="New kitchen name; empty = the name."
    )
    price_delta: Delta | None = Field(
        None, description="New supplement in cents (negative = a discount)."
    )
    tax_category_key: TaxKey | None = Field(
        None,
        title=OWN_TAX_CATEGORY,
        description="New own tax category (key or name); empty = back to the dish's.",
    )
    is_default: bool | None = Field(
        None, description="Whether it comes chosen when the till opens the group."
    )
    sort_order: Order | None = Field(None, description="New order.")


# Inputs: links


class LinkListIn(PageIn):
    group_id: UUID | None = Field(None, description="Only the links of this group.")
    group: Said | None = Field(
        None, description="Only the links of the group with this name."
    )
    product_id: UUID | None = Field(None, description="Only the links to this product.")
    category_id: UUID | None = Field(
        None, description="Only the links to this category."
    )


class _Target(_Input):
    product_id: UUID | None = Field(None, description="The product's id.", json_schema_extra=A_PRODUCT)
    product: Said | None = Field(
        None, description="The product's SKU or name, when its id is not known."
    )
    category_id: UUID | None = Field(None, description="The category's id.", json_schema_extra=A_CATEGORY)
    category: Said | None = Field(
        None, description="The category's name, when its id is not known."
    )

    def _targets(self) -> int:
        product = self.product_id is not None or self.product is not None
        category = self.category_id is not None or self.category is not None
        return int(product) + int(category)


class LinkIn(_Target):
    group_id: UUID | None = Field(None, description="The group's id.", json_schema_extra=A_GROUP)
    group: Said | None = Field(
        None,
        description="The group's name, when its id is not known (e.g. «Sauces»).",
        json_schema_extra=unless_given(A_GROUP_BY_NAME, "group_id"),
    )

    @model_validator(mode="after")
    def _named(self):
        if self.group_id is None and self.group is None:
            raise ValueError(str(SAY_WHICH_GROUP))
        if self._targets() != 1:
            raise ValueError(str(SAY_ONE_TARGET))
        return self


class LinkRefIn(_Target):
    id: UUID | None = Field(None, title=APPLIES_TO, description="The link's id.", json_schema_extra=A_LINK)
    group_id: UUID | None = Field(None, description="The group's id.", json_schema_extra=A_GROUP)
    group: Said | None = Field(
        None,
        description="The group's name, when its id is not known.",
        json_schema_extra=unless_given(A_GROUP_BY_NAME, "id", "group_id"),
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and (
            (self.group_id is None and self.group is None) or self._targets() != 1
        ):
            raise ValueError(str(SAY_WHICH_LINK))
        return self


class CategoryRefIn(_Input):
    id: UUID | None = Field(None, description="The category's id.")
    category: Said | None = Field(
        None, description="The category's name, when its id is not known."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and self.category is None:
            raise ValueError(str(SAY_WHICH_CATEGORY))
        return self


# Inputs: the till's reads


class TargetIn(_Product):
    pass


class ResolveIn(_Product):
    option_ids: list[UUID] = Field(
        default_factory=list,
        max_length=MAX_PICKS,
        description="The ids of the options chosen, in the order they were chosen; an option repeated is chosen "
        "that many times.",
    )


class DropIn(Schema):
    """Inventory's payload of a deleted product or category, as it comes (extra keys are ignored)."""

    id: UUID = Field(description="The id of the deleted product or category.")


# Outputs


class GroupOut(Schema):
    id: UUID = Field(description="The group's id.")
    name: str = Field(description="Name.")
    kitchen_name: str = Field(
        description="Name on the kitchen ticket; empty = the name."
    )
    min_choices: int = Field(
        description="Options to choose at least; 1 or more = required."
    )
    max_choices: int = Field(description="Options to choose at most; 0 = no ceiling.")
    allow_repeat: bool = Field(
        description="The same option may be chosen more than once."
    )
    is_required: bool = Field(description="True when the minimum is 1 or more.")
    sort_order: int = Field(description="Order in the till.")
    option_count: int = Field(description="How many options it has.")
    default_count: int = Field(description="How many of them come chosen by default.")
    link_count: int = Field(
        description="How many live products and categories it hangs from."
    )
    created_at: datetime = Field(description="When it was created.")
    updated_at: datetime = Field(description="When it was last changed.")


class OptionOut(Schema):
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


class LinkOut(Schema):
    id: UUID = Field(description="The link's id.")
    group_id: UUID = Field(description="The group.")
    group_name: str = Field(description="The group's name.")
    target_kind: TargetKind = Field(description="product or category.")
    product_id: UUID | None = Field(description="The product, when it hangs from one.")
    product_name: str | None = Field(description="The product's name.")
    product_sku: str | None = Field(description="The product's SKU.")
    category_id: UUID | None = Field(
        description="The category, when it hangs from one."
    )
    category_name: str | None = Field(description="The category's name.")
    created_at: datetime = Field(description="When it was linked.")


class OptionDetailOut(OptionOut):
    label: str = Field(description="How a person tells it apart: its name and its group, «Large (Drinks)».")


class LinkDetailOut(LinkOut):
    label: str = Field(description="How a person tells it apart: its group and what it hangs from, «Sauces · Burger».")


class CategoryRefOut(Schema):
    id: UUID = Field(description="The category's id.")
    name: str = Field(description="Its name, as Inventory shows it.")


class TargetOptionOut(Schema):
    id: UUID = Field(
        description="The option's id: what the till sends back when it is chosen."
    )
    name: str = Field(description="Name, as the customer reads it.")
    kitchen_name: str = Field(
        description="Name on the kitchen ticket; empty = the name."
    )
    price_delta: int = Field(
        description="Supplement in cents; negative = a discount; 0 = free."
    )
    tax_category_key: str | None = Field(
        description="Key of its own tax category; null = the dish's."
    )
    is_default: bool = Field(description="Comes chosen when the sheet opens.")


class TargetGroupOut(Schema):
    id: UUID = Field(description="The group's id.")
    name: str = Field(description="Name.")
    kitchen_name: str = Field(
        description="Name on the kitchen ticket; empty = the name."
    )
    min_choices: int = Field(
        description="Options to choose at least; 1 or more = required."
    )
    max_choices: int = Field(description="Options to choose at most; 0 = no ceiling.")
    allow_repeat: bool = Field(
        description="The same option may be chosen more than once."
    )
    is_required: bool = Field(description="True when the minimum is 1 or more.")
    options: list[TargetOptionOut] = Field(description="Its options, in their order.")


class TargetOut(Schema):
    product_id: UUID = Field(description="The product.")
    product_name: str = Field(description="The product's name.")
    groups: list[TargetGroupOut] = Field(
        description="The groups it carries (its own and its categories'), each once, by order and name; a group "
        "without options is left out."
    )


class PickOut(Schema):
    option_id: UUID = Field(description="The option chosen.")
    group_id: UUID = Field(description="Its group.")
    group_name: str = Field(description="Its group's name.")
    name: str = Field(description="Its name, as the customer reads it (the receipt).")
    kitchen_name: str = Field(
        description="What the kitchen reads: its kitchen name, or its name."
    )
    price_delta: int = Field(description="Its supplement in cents, from the catalog.")
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
    price_delta: int = Field(description="Its unit price in cents, from the catalog (always more than zero).")
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


class DeletedOut(Schema):
    id: UUID = Field(description="What was deleted.")


class DropOut(Schema):
    dropped: int = Field(description="How many links were dropped.")
