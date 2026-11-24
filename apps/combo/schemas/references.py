"""How a schema names the menu, the course or the choice it is about: by its id, or by its name."""

from uuid import UUID

from ninja import Field
from pydantic import model_validator

from apps.combo.schemas.fields import (
    A_CHOICE,
    A_CHOICE_BY_NAME,
    A_COURSE,
    A_COURSE_BY_NAME,
    A_MENU,
    A_MENU_BY_NAME,
    D_COMBO,
    D_COMBO_ID,
    D_GROUP,
    D_GROUP_ID,
    SAY_WHICH_CHOICE,
    SAY_WHICH_COURSE,
    SAY_WHICH_MENU,
    T_CHOICE,
    T_COURSE,
    T_MENU,
    In,
    Reference,
    _named,
)
from base.schemas import assistant


class ComboRefIn(In):
    id: UUID | None = Field(None, title=T_MENU, description=D_COMBO_ID, json_schema_extra=A_MENU)
    combo: Reference | None = Field(None, description=D_COMBO, json_schema_extra=assistant.unless_given(A_MENU_BY_NAME, "id"))

    @model_validator(mode="after")
    def _combo_named(self):
        _named(self.id, self.combo, SAY_WHICH_MENU)
        return self


class _ComboOfIn(In):
    """The menu something belongs to, by id or by name."""

    combo_id: UUID | None = Field(None, description=D_COMBO_ID, json_schema_extra=A_MENU)
    combo: Reference | None = Field(
        None, description=D_COMBO, json_schema_extra=assistant.unless_given(A_MENU_BY_NAME, "combo_id")
    )


class _GroupOfIn(_ComboOfIn):
    """The course something belongs to: its id, or its name with its menu."""

    combo_id: UUID | None = Field(None, description=D_COMBO_ID, json_schema_extra=assistant.unless_given(A_MENU, "group_id"))
    combo: Reference | None = Field(
        None, description=D_COMBO, json_schema_extra=assistant.unless_given(A_MENU_BY_NAME, "combo_id", "group_id")
    )
    group_id: UUID | None = Field(None, description=D_GROUP_ID, json_schema_extra=A_COURSE)
    group: Reference | None = Field(
        None, description=D_GROUP, json_schema_extra=assistant.unless_given(A_COURSE_BY_NAME, "group_id")
    )

    def _group_named(self) -> None:
        if self.group_id is None and (
            self.group is None or (self.combo_id is None and self.combo is None)
        ):
            raise ValueError(str(SAY_WHICH_COURSE))


class GroupRefIn(_ComboOfIn):
    combo_id: UUID | None = Field(None, description=D_COMBO_ID, json_schema_extra=assistant.unless_given(A_MENU, "id"))
    combo: Reference | None = Field(
        None, description=D_COMBO, json_schema_extra=assistant.unless_given(A_MENU_BY_NAME, "id", "combo_id")
    )
    id: UUID | None = Field(None, title=T_COURSE, description=D_GROUP_ID, json_schema_extra=A_COURSE)
    group: Reference | None = Field(None, description=D_GROUP, json_schema_extra=assistant.unless_given(A_COURSE_BY_NAME, "id"))

    @model_validator(mode="after")
    def _course_named(self):
        if self.id is None and (
            self.group is None or (self.combo_id is None and self.combo is None)
        ):
            raise ValueError(str(SAY_WHICH_COURSE))
        return self


class OptionRefIn(_ComboOfIn):
    combo_id: UUID | None = Field(
        None, description=D_COMBO_ID, json_schema_extra=assistant.unless_given(A_MENU, "id", "group_id")
    )
    combo: Reference | None = Field(
        None, description=D_COMBO, json_schema_extra=assistant.unless_given(A_MENU_BY_NAME, "id", "combo_id", "group_id")
    )
    id: UUID | None = Field(
        None,
        title=T_CHOICE,
        description="The choice's id. Give it, or its product with its menu.",
        json_schema_extra=A_CHOICE,
    )
    group_id: UUID | None = Field(
        None,
        description="The course of the choice, when the product is in several.",
        json_schema_extra=assistant.unless_given(A_COURSE, "id"),
    )
    group: Reference | None = Field(
        None, description=D_GROUP, json_schema_extra=assistant.unless_given(A_COURSE_BY_NAME, "id", "group_id")
    )
    product: Reference | None = Field(
        None,
        description="The choice's product SKU or name, without its id: in the person's own words, never translated.",
        json_schema_extra=assistant.unless_given(A_CHOICE_BY_NAME, "id"),
    )

    @model_validator(mode="after")
    def _choice_named(self):
        if self.id is None and (
            self.product is None
            or (self.combo_id is None and self.combo is None and self.group_id is None)
        ):
            raise ValueError(str(SAY_WHICH_CHOICE))
        return self
