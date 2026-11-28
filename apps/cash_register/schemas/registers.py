"""The drawers: their list, one of them, a new one and a change of one, named by its id or its name."""

from uuid import UUID

from ninja import Field, Schema
from pydantic import model_validator

from apps.cash_register.schemas.fields import (
    A_DRAWER,
    DRAWER,
    NOTHING_TO_CHANGE,
    SAY_WHICH_DRAWER,
    Closed,
    Name,
    Page,
    PageIn,
)

class RegisterListIn(PageIn):
    search: str | None = Field(
        None, max_length=100, description="Part of the drawer's name."
    )
    is_active: bool | None = Field(
        None, description="Only active (or inactive) drawers."
    )


class RegisterOut(Schema):
    id: UUID = Field(description="The drawer's id.")
    name: str = Field(description="Its name.")
    is_active: bool = Field(description="It can be chosen when opening a session.")


RegisterPage = Page[RegisterOut]


class RegisterIn(Closed):
    name: Name = Field(description="The drawer's name, e.g. Bar.")


class RegisterGetIn(Closed):
    register_id: UUID = Field(description="The drawer's id.")


class RegisterUpdateIn(Closed):
    register_id: UUID | None = Field(None, description="The drawer's id.", json_schema_extra=A_DRAWER)
    register_name: Name | None = Field(
        None, title=DRAWER, description="Its name, when the id is not known."
    )
    name: Name | None = Field(None, description="Its new name.")
    is_active: bool | None = Field(
        None, description="Activate (true) or deactivate (false) it."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.register_id is None and self.register_name is None:
            raise ValueError(str(SAY_WHICH_DRAWER))
        if self.name is None and self.is_active is None:
            raise ValueError(str(NOTHING_TO_CHANGE))
        return self
