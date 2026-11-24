"""The courses of a menu: what one is made, changed or put in order with, and how one reads back with its choices."""

from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator, model_validator

from apps.combo.schemas.choices import OptionOut
from apps.combo.schemas.fields import D_MAX, D_MIN, D_REPEAT, SAY_WHICH_MENU, GroupIds, Name, Picks, _ceiling, _named
from apps.combo.schemas.references import ComboRefIn, GroupRefIn, _ComboOfIn


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


class GroupRecoverIn(GroupIn):
    """A course of a separate copy its menu no longer has: what ``combo.group.create`` takes."""

    stands_for: UUID = Field(description="The course of the copy it is made again for, by its id there.")


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


class GroupOut(Schema):
    id: UUID
    combo_id: UUID
    name: str
    min_choices: int
    max_choices: int
    allow_repeat: bool
    sort_order: int
    options: list[OptionOut]
