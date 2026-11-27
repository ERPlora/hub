"""The groups of options: how one is named, what one is made, recovered or changed with, and how one reads back."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator, model_validator

from apps.modifier.models import MAX_OPTIONS
from apps.modifier.schemas.fields import (
    A_GROUP,
    A_GROUP_BY_NAME,
    GROUP,
    KITCHEN_TICKET_NAME,
    SAY_WHICH_GROUP,
    Choices,
    KitchenName,
    Name,
    Order,
    PageIn,
    Said,
    Search,
    _Input,
)
from apps.modifier.schemas.options import OptionOfCopyIn
from base.recovery import RecoveredOut
from base.schemas.assistant import no_limit, unless_given

MAX_BELOW_MIN = _("The maximum cannot be below the minimum (0 = no ceiling).")

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
        json_schema_extra=no_limit(),
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
    max_choices: Choices | None = Field(None, description="New maximum; 0 = no ceiling.", json_schema_extra=no_limit())
    allow_repeat: bool | None = Field(
        None, description="Whether the same option may be chosen more than once."
    )
    sort_order: Order | None = Field(None, description="New order.")


class GroupRecoverIn(GroupIn):
    """A group of a separate copy the business no longer has: what ``modifier.group.create`` takes and its options
    there."""

    options: list[OptionOfCopyIn] = Field(
        [], max_length=MAX_OPTIONS, description="Its options in the copy, in the order they were added."
    )


class _GroupFields(Schema):
    """What a group is, on the screen's list and on the till's sheet alike."""

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


class GroupOut(_GroupFields):
    sort_order: int = Field(description="Order in the till.")
    option_count: int = Field(description="How many options it has.")
    default_count: int = Field(description="How many of them come chosen by default.")
    link_count: int = Field(
        description="How many live products and categories it hangs from."
    )
    created_at: datetime = Field(description="When it was created.")
    updated_at: datetime = Field(description="When it was last changed.")


class GroupRecoveredOut(GroupOut, RecoveredOut):
    """A group made again from a separate copy, and the options it came back without."""
