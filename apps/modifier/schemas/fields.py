"""The types, titles and record marks the schemas of Modifiers share, their pages and the closed input.

Every list is paginated, limit ≤ 100.
"""

from typing import Annotated, Generic, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints

from apps.modifier.models import MAX_CHOICES, MAX_DELTA, NAME_MAX_LENGTH
from base.schemas.assistant import names

T = TypeVar("T")

SAY_WHICH_GROUP = _("Say which group: its id, or its name.")

# How the Modifiers screens name the data the models do not (the assistant's card names each datum by its title).
GROUP = gettext_noop("Group")
OPTION = gettext_noop("Option")
APPLIES_TO = gettext_noop("Applies to")
OWN_TAX_CATEGORY = gettext_noop("Own tax category")
#: The forms' name for it; the model's own, «kitchen name», is the Django admin's (hub#958).
KITCHEN_TICKET_NAME = gettext_noop("Kitchen ticket name")

# The assistant's card names the record a write acts on by these reads (base/assistant/cards.py ``REFERS``), run as whoever
# asks, never by its id: a group, a product and a category by their names; an option by its name and its group, because
# two groups may have an option with one name; a link by its group and what it hangs from.
A_GROUP = names("modifier.group.get")
# A group said by its name, when its id is not known: a group belongs to nothing, so the card reads it by that name
# alone, as the write will find it, and shows the group the write acts on («Salsas picantes» when the person said
# «salsa», hub#1218); words it cannot read (two groups fit, none does) it says as said, never off the card, so adding
# an option or applying a group, which cannot check it, reads it too (hub#1245). Beside the id the write takes its
# record by instead (the group's, or the link's), the card neither reads nor shows the name, which the write does not
# use (``unless_given``, hub#1250); an option by its id is looked for in the group said, so that one is read. Beside
# a link's id the card neither reads nor shows the group, the product or the category whose id comes with it: letting
# the link go takes it by its id alone (hub#1278).
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
# A product or a category said by its name, when a group is applied to it or let go from it: the card reads it by those
# words, as the write will find it (a product by its SKU or its name, a category by its name), so it shows the one the
# write acts on, and says it as said when it cannot read it (hub#1291). Beside the id the write takes its record by
# instead (the product's or the category's or, letting a group go, the link's), it neither reads nor shows it.
A_PRODUCT_BY_NAME = names("inventory.product.get", by="product", as_said=True)
A_CATEGORY_BY_NAME = names("modifier.category.get", by="category", as_said=True)


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


class DeletedOut(Schema):
    id: UUID = Field(description="What was deleted.")
