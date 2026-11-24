"""The types, limits, messages and record marks the schemas of Menus share, their pages and the closed input.

Every list is paginated, limit ≤ 100.
"""

from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import AfterValidator, ConfigDict, StringConstraints

from apps.combo.models import MAX_PICKS, NAME_MAX_LENGTH
from base.schemas import assistant

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
# What the assistant's card calls the record a write acts on by its id (its Spanish in this app's catalog), as the
# screens call one («Withdraw this menu?», «Course · Starters»), never «Record».
T_MENU = gettext_noop("Menu")
T_COURSE = gettext_noop("Course")
T_CHOICE = gettext_noop("Choice")

# The assistant's card names the record a write acts on by these reads (base/assistant/cards.py ``REFERS``), run as whoever
# asks, never by its id: a menu and a course by their name and a choice by its product's, as the builder's «Withdraw»
# and «Remove» dialogs say them; a product of Inventory by its name, as Inventory's screens say it.
A_MENU = assistant.names("combo.combo.get")
# What a person says by its name, when its id is not known: the card reads it by that name too, as the write will find
# it, so it shows what the write acts on («Menú vegano» when the person said «vegano», hub#1217), and words it cannot
# read (two fit, none does) as said, never off the card (hub#1245). A course is found inside its menu and a choice by
# its product inside its menu and its course: each is read with them (``within``), never with the write's ``id``, which
# is the record of the write (a course's, a choice's) and no menu's. Beside the id the write takes its record by
# instead (the datum's own, or the one of the record that holds it: a course's menu is the course's own), the card
# neither reads nor shows the name, which the write does not use (``unless_given``, hub#1250), nor the id of a menu or
# a course beside the id of a course or a choice, or of the course a choice is said in (hub#1278).
A_MENU_BY_NAME = assistant.names("combo.combo.get", by="combo", as_said=True)
A_COURSE_BY_NAME = assistant.names("combo.group.get", by="group", within=("combo_id", "combo"), as_said=True)
A_CHOICE_BY_NAME = assistant.names(
    "combo.option.get",
    by="product",
    within=("combo_id", "combo", "group_id", "group"),
    name=("product_name",),
    as_said=True,
)
A_PRODUCT_BY_NAME = assistant.names("inventory.product.get", by="product", as_said=True)
A_COURSE = assistant.names("combo.group.get")
A_CHOICE = assistant.names("combo.option.get", name=("product_name",))
A_PRODUCT = assistant.names("inventory.product.get")

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
Cents = Annotated[int, Field(ge=0, le=MAX_CENTS, json_schema_extra={"money": True})]
Delta = Annotated[int, Field(ge=-MAX_CENTS, le=MAX_CENTS, json_schema_extra={"money": True})]
Picks = Annotated[int, Field(ge=0, le=MAX_PICKS)]
Order = Annotated[int, Field(ge=0, le=MAX_ORDER)]
SupplyKind = Literal["service", "goods"]
Direction = Literal["asc", "desc"]


def _ids(mark: dict, most: int):
    """Records by their ids, each one once: the assistant's card names each one as ``mark`` says."""
    return Annotated[
        list[Annotated[UUID, Field(json_schema_extra=mark)]],
        Field(min_length=1, max_length=most),
        AfterValidator(_unique),
    ]


GroupIds = _ids(A_COURSE, MAX_GROUPS)
OptionIds = _ids(A_CHOICE, MAX_OPTIONS)
ProductIds = _ids(A_PRODUCT, MAX_OPTIONS)

# Field descriptions shared by several schemas (the assistant reads them).
D_COMBO_ID = "The menu's id. Give it, or its name in `combo`."
D_COMBO = "The menu's name («menu of the day»), when its id is not known."
D_GROUP_ID = "The course's id. Give it, or its name in `group` with its menu."
D_GROUP = (
    "The course's name inside the menu («Starters», «Drink»), when its id is not known."
)
D_PRODUCT_ID = "Id of the product (Inventory app)."
D_PRODUCT = "The product's SKU or name («Lentils»), without its id: in the person's own words, never translated."
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


class DeletedOut(Schema):
    id: UUID
