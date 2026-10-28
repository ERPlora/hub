"""Input and output schemas of the combo app's operations (OpenAPI, live params, 422 per field, and the
assistant's tools: every input field carries a ``description``).

Every input refuses a field it does not declare. A menu is named by its id or its name («menu of the
day»); a course by its id, or by its name inside a menu («Starters»); a choice by its id, or by its
product inside a menu; a product by its id, its SKU or its name: the assistant is used by voice.
``queries.find_combo``, ``find_group`` and ``find_option`` turn the text into the row. Money is in
cents.
"""

import datetime as dt
import json
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import (
    BeforeValidator,
    AfterValidator,
    ConfigDict,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

from apps.combo.models import MAX_PICKS, NAME_MAX_LENGTH

T = TypeVar("T")

# Validation messages (English source, Spanish in locale/).
SAY_WHICH_MENU = _("Say which menu: its id or its name.")
SAY_WHICH_COURSE = _("Say which course: its id, or its name and its menu.")
SAY_WHICH_CHOICE = _("Say which choice: its id, or its product and its menu.")
SAY_WHICH_PRODUCT = _("Choose a product of the catalogue first.")
SAY_WHICH_PICK = _("Say which choice: its id or its product.")
NOT_A_PICK = _("A pick is an object with its choice or its product.")
CEILING_BELOW_FLOOR = _(
    "The maximum (%(max)s) is below the minimum (%(min)s): nobody could ever satisfy this course."
)
REPEATED_ID = _("Each one goes once in the list.")

# How the Menus screens name the data the models do not (the assistant's card names each datum by its title).
VAT_CATEGORY = gettext_noop("VAT category")
NEW_PRODUCT = gettext_noop("New product")

#: Ninety-nine billion euros in cents: far above any price, inside a bigint (Inventory's bound).
MAX_CENTS = 9_999_999_999_999
#: Courses a menu holds and choices a course holds: a menu fits in one live result (256 KB).
MAX_GROUPS = 20
MAX_OPTIONS = 40
MAX_ORDER = 1_000_000
#: The longest tax category key (Taxes' ``CATEGORY_KEY_MAX_LENGTH``).
TAX_KEY_MAX_LENGTH = 80


def _text(max_length: int, min_length: int = 0):
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


def _unique(values: list) -> list:
    if len(set(values)) != len(values):
        raise ValueError(str(REPEATED_ID))
    return values


Name = _text(NAME_MAX_LENGTH, 1)
KitchenName = _text(NAME_MAX_LENGTH)
Reference = _text(NAME_MAX_LENGTH, 1)
Search = _text(120)
TaxKey = _text(TAX_KEY_MAX_LENGTH)
Cents = Annotated[int, Field(ge=0, le=MAX_CENTS)]
Delta = Annotated[int, Field(ge=-MAX_CENTS, le=MAX_CENTS)]
Picks = Annotated[int, Field(ge=0, le=MAX_PICKS)]
Order = Annotated[int, Field(ge=0, le=MAX_ORDER)]
SupplyKind = Literal["service", "goods"]
Direction = Literal["asc", "desc"]
GroupIds = Annotated[
    list[UUID], Field(min_length=1, max_length=MAX_GROUPS), AfterValidator(_unique)
]
OptionIds = Annotated[
    list[UUID], Field(min_length=1, max_length=MAX_OPTIONS), AfterValidator(_unique)
]

# Field descriptions shared by several schemas (the assistant reads them).
D_COMBO_ID = "The menu's id. Give it, or its name in `combo`."
D_COMBO = "The menu's name («menu of the day»), when its id is not known."
D_GROUP_ID = "The course's id. Give it, or its name in `group` with its menu."
D_GROUP = (
    "The course's name inside the menu («Starters», «Drink»), when its id is not known."
)
D_PRODUCT_ID = "Id of the product (Inventory app)."
D_PRODUCT = "The product's SKU or name («Lentils»), when its id is not known."
D_PRICE = "The closed price in cents: what the customer pays for the whole menu, whatever they pick."
D_DELTA = "Supplement in cents added to the closed price when this choice is picked; negative makes it cheaper."
D_SUPPLY = (
    "How the menu is sold and billed: `service` = eaten in, one line at the menu's own tax category, drinks "
    "included (art. 91.Uno.2.2 LIVA); `goods` = to take away, split in one line per dish when the dishes do "
    "not share a tax category (art. 79.Dos LIVA)."
)
D_TAX = "Key of the tax category of the whole menu (Taxes app, e.g. `restaurant.food`); required when eaten in."
D_MIN = "Minimum picks: 1 or more makes the course compulsory, 0 optional."
D_MAX = "Maximum picks; 0 means no limit. Never below the minimum."
D_REPEAT = "Whether the same choice may be picked more than once (two coffees)."


def _named(ref_id: Any, text: Any, message) -> None:
    if ref_id is None and text is None:
        raise ValueError(str(message))


def _ceiling(min_choices: int | None, max_choices: int | None) -> None:
    if (
        min_choices is not None
        and max_choices is not None
        and max_choices != 0
        and max_choices < min_choices
    ):
        raise ValueError(
            str(CEILING_BELOW_FLOOR) % {"max": max_choices, "min": min_choices}
        )


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


# Pages: every list is paginated, limit ≤ 100.


class PageIn(In):
    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return (1 to 100)."
    )
    offset: int = Field(
        0, ge=0, description="How many rows to skip, for the next pages."
    )


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="Rows that match, over all pages.")
    limit: int = Field(description="Rows per page asked.")
    offset: int = Field(description="Rows skipped.")


# References


class ComboRefIn(In):
    id: UUID | None = Field(None, description=D_COMBO_ID)
    combo: Reference | None = Field(None, description=D_COMBO)

    @model_validator(mode="after")
    def _combo_named(self):
        _named(self.id, self.combo, SAY_WHICH_MENU)
        return self


class _ComboOfIn(In):
    """The menu something belongs to, by id or by name."""

    combo_id: UUID | None = Field(None, description=D_COMBO_ID)
    combo: Reference | None = Field(None, description=D_COMBO)


class _GroupOfIn(_ComboOfIn):
    """The course something belongs to: its id, or its name with its menu."""

    group_id: UUID | None = Field(None, description=D_GROUP_ID)
    group: Reference | None = Field(None, description=D_GROUP)

    def _group_named(self) -> None:
        if self.group_id is None and (
            self.group is None or (self.combo_id is None and self.combo is None)
        ):
            raise ValueError(str(SAY_WHICH_COURSE))


class GroupRefIn(_ComboOfIn):
    id: UUID | None = Field(None, description=D_GROUP_ID)
    group: Reference | None = Field(None, description=D_GROUP)

    @model_validator(mode="after")
    def _course_named(self):
        if self.id is None and (
            self.group is None or (self.combo_id is None and self.combo is None)
        ):
            raise ValueError(str(SAY_WHICH_COURSE))
        return self


class OptionRefIn(_ComboOfIn):
    id: UUID | None = Field(
        None, description="The choice's id. Give it, or its product with its menu."
    )
    group_id: UUID | None = Field(
        None, description="The course of the choice, when the product is in several."
    )
    group: Reference | None = Field(None, description=D_GROUP)
    product: Reference | None = Field(
        None,
        description="The SKU or name of the choice's product, when its id is not known.",
    )

    @model_validator(mode="after")
    def _choice_named(self):
        if self.id is None and (
            self.product is None
            or (self.combo_id is None and self.combo is None and self.group_id is None)
        ):
            raise ValueError(str(SAY_WHICH_CHOICE))
        return self


# Menus


class ComboListIn(PageIn):
    search: Search | None = Field(
        None, description="Text to look for in the name or the kitchen name."
    )
    name: Search | None = Field(
        None, description="Keep the menus whose name contains this."
    )
    supply_kind: SupplyKind | None = Field(
        None, description="Keep the menus sold this way: service (eaten in) or goods."
    )
    is_active: bool | None = Field(
        None,
        description="true: only the menus on sale; false: only the withdrawn ones.",
    )
    sort: Literal["sort_order", "name", "price", "supply_kind", "is_active", "id"] = (
        Field(
            "sort_order",
            description="Column to sort by; the name and the id break ties.",
        )
    )
    dir: Direction = Field("asc", description="asc or desc.")


class ComboIn(In):
    name: Name = Field(description="The menu's name on the till («Menu of the day»).")
    kitchen_name: KitchenName = Field(
        "", description="Name on the kitchen ticket; empty uses the name."
    )
    price: Cents = Field(0, description=D_PRICE)
    supply_kind: SupplyKind = Field("service", description=D_SUPPLY)
    tax_category_key: TaxKey | None = Field(
        None, title=VAT_CATEGORY, description=D_TAX
    )
    sort_order: Order = Field(
        0, description="Position on the list of menus and on the till."
    )
    is_active: bool = Field(
        True, description="On sale: false keeps it on the list but off the till."
    )


class ComboPatchIn(ComboRefIn):
    """Only the fields sent change."""

    name: Name | None = Field(None, description="New name.")
    kitchen_name: KitchenName | None = Field(
        None, description="New kitchen name; empty uses the name."
    )
    price: Cents | None = Field(None, description="New closed price, in cents.")
    supply_kind: SupplyKind | None = Field(None, description=D_SUPPLY)
    tax_category_key: TaxKey | None = Field(
        None,
        title=VAT_CATEGORY,
        description=D_TAX + " Empty clears it (only to take away).",
    )
    sort_order: Order | None = Field(None, description="New position on the list.")
    is_active: bool | None = Field(
        None, description="Put on sale (true) or withdraw from the till (false)."
    )


# Courses


class GroupIn(_ComboOfIn):
    name: Name = Field(description="The course's name («Starters», «Mains», «Drink»).")
    min_choices: Picks = Field(1, description=D_MIN)
    max_choices: Picks = Field(1, description=D_MAX)
    allow_repeat: bool = Field(False, description=D_REPEAT)

    @field_validator("max_choices")
    @classmethod
    def _not_below_floor(cls, value: int, info: ValidationInfo) -> int:
        _ceiling(info.data.get("min_choices"), value)
        return value

    @model_validator(mode="after")
    def _menu_named(self):
        _named(self.combo_id, self.combo, SAY_WHICH_MENU)
        return self


class GroupPatchIn(GroupRefIn):
    """Only the fields sent change; the ceiling is checked against what the course keeps."""

    name: Name | None = Field(None, description="New name.")
    min_choices: Picks | None = Field(None, description=D_MIN)
    max_choices: Picks | None = Field(None, description=D_MAX)
    allow_repeat: bool | None = Field(None, description=D_REPEAT)

    @field_validator("max_choices")
    @classmethod
    def _not_below_floor(cls, value: int | None, info: ValidationInfo) -> int | None:
        _ceiling(info.data.get("min_choices"), value)
        return value


class GroupReorderIn(ComboRefIn):
    group_ids: GroupIds = Field(
        title=gettext_noop("Courses"),
        description="Every course of the menu, by id, in the new order.",
    )


# Choices


class OptionIn(_GroupOfIn):
    product_id: UUID | None = Field(None, description=D_PRODUCT_ID)
    product: Reference | None = Field(None, description=D_PRODUCT)
    price_delta: Delta = Field(0, description=D_DELTA)
    is_available: bool = Field(
        True, description="false: sold out today, kept but not offered."
    )

    @model_validator(mode="after")
    def _named_all(self):
        self._group_named()
        _named(self.product_id, self.product, SAY_WHICH_PRODUCT)
        return self


class OptionBulkIn(_GroupOfIn):
    product_ids: OptionIds = Field(
        title=gettext_noop("Products"),
        description="The products to add, by id, in the order they go in (no supplement).",
    )

    @model_validator(mode="after")
    def _course_named(self):
        self._group_named()
        return self


class OptionPatchIn(OptionRefIn):
    """Only the fields sent change; the choice keeps its position."""

    new_product_id: UUID | None = Field(
        None,
        title=NEW_PRODUCT,
        description="Id of the product that replaces the current one.",
    )
    new_product: Reference | None = Field(
        None,
        title=NEW_PRODUCT,
        description="SKU or name of the product that replaces the current one.",
    )
    price_delta: Delta | None = Field(None, description=D_DELTA)
    is_available: bool | None = Field(
        None, description="false: sold out today (not offered); true: back on offer."
    )


class OptionReorderIn(_GroupOfIn):
    option_ids: OptionIds = Field(
        title=gettext_noop("Choices"),
        description="Every choice of the course, by id, in the new order.",
    )

    @model_validator(mode="after")
    def _course_named(self):
        self._group_named()
        return self


class DropProductIn(Schema):
    """The payload of Inventory's ``inventory.product.deleted`` (the rest of it is ignored)."""

    id: UUID = Field(description="The product deleted from the catalogue.")
    sku: str = Field("", title=gettext_noop("SKU"), description="Its SKU, as it was.")
    name: str = Field("", description="Its name, as it was.")


# The till


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
        description="SKU or name of the product picked, when the choice's id is not known.",
    )
    group: Reference | None = Field(
        None, description="The course it is picked in, when the product is in several."
    )
    quantity: int = Field(
        1,
        ge=1,
        le=MAX_PICKS,
        description="How many times it is picked (two coffees: 2).",
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


# Outputs


class OptionOut(Schema):
    id: UUID
    group_id: UUID
    product_id: UUID
    product_name: str
    sku: str
    catalog_price: int = Field(description="The product's catalogue price, in cents.")
    price_delta: int
    is_available: bool
    sort_order: int
    status: Literal[
        "offered", "sold_out", "product_inactive", "product_sold_out", "product_deleted", "not_by_unit", "untaxed"
    ] = Field(
        description="offered; sold_out (marked here); product_inactive, product_sold_out, product_deleted or "
        "not_by_unit (in Inventory); untaxed (no rate to bill it at in a menu to take away)."
    )


class GroupOut(Schema):
    id: UUID
    combo_id: UUID
    name: str
    min_choices: int
    max_choices: int
    allow_repeat: bool
    sort_order: int
    options: list[OptionOut]


class ComboOut(Schema):
    id: UUID
    name: str
    kitchen_name: str
    price: int
    supply_kind: SupplyKind
    tax_category_key: str | None
    tax_category_name: str | None
    sort_order: int
    is_active: bool
    group_count: int
    created_at: dt.datetime
    updated_at: dt.datetime


ComboPage = Page[ComboOut]


class BlockerOut(Schema):
    code: str = Field(
        description="combo.not_on_sale, combo.tax_category_inactive, combo.no_choices, combo.group_short or "
        "combo.no_catalog_price."
    )
    message: str
    group_id: UUID | None


class ComboDetailOut(ComboOut):
    groups: list[GroupOut]
    sellable: bool = Field(description="Whether the till offers it now.")
    blockers: list[BlockerOut] = Field(description="Why the till does not offer it.")


class DeletedOut(Schema):
    id: UUID


class DroppedOut(Schema):
    dropped: int = Field(description="Choices removed.")


class SaleOptionOut(Schema):
    id: UUID
    product_id: UUID
    product_name: str
    sku: str
    price_delta: int


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
    price: int
    supply_kind: SupplyKind
    sort_order: int
    groups: list[SaleGroupOut]


SaleComboPage = Page[SaleComboOut]


class ComponentOut(Schema):
    option_id: UUID
    group_id: UUID
    group_name: str
    product_id: UUID
    product_name: str
    sku: str
    category_id: UUID | None = Field(
        description="The product's first category, for the kitchen's routing."
    )
    is_service: bool = Field(description="A service product never moves stock.")
    quantity: int = Field(description="Picks of it in one menu.")
    price_delta: int = Field(description="Supplement of one pick, in cents.")
    catalog_price: int = Field(
        description="The product's catalogue price, in cents: the weight of the split."
    )
    tax_category_key: str | None
    amount: int | None = Field(
        description="Its part of the menu's amount, in cents, when the menu is split."
    )


class ResolvedOut(Schema):
    combo_id: UUID
    name: str
    kitchen_name: str
    supply_kind: SupplyKind
    price: int = Field(description="Today's closed price, in cents.")
    supplements: int = Field(description="The supplements of the picks, in cents.")
    amount: int = Field(
        description="What the menu charges: the amount ordered, or price plus supplements."
    )
    split: bool = Field(
        description="true: one sale line per component, each at its own tax category and amount."
    )
    tax_category_key: str | None = Field(
        description="The tax category of the single line; null when split."
    )
    components: list[ComponentOut]
