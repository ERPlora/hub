"""Schemas of the custom fields a business adds to its cards."""

from typing import Annotated, Literal
from uuid import UUID

from ninja import Field, Schema
from pydantic import StringConstraints, ValidationInfo, field_validator

from apps.customer.schemas.contact import EMAIL, PHONE
from apps.customer.schemas.fields import INT4_MAX, OPTIONS_MISSING, FieldRefIn, FieldType, Page, PageIn, _text
from base.schemas.assistant import IN_OWN_WORDS


class FieldListIn(PageIn):
    search: str | None = Field(
        None, max_length=200, description="Text to look for in the name."
    )
    field_type: FieldType | None = Field(None, description="Only fields of this type.")
    is_required: bool | None = Field(
        None, description="Only required (true) or optional (false) fields."
    )
    is_active: bool | None = Field(
        None, description="Only active (true) or inactive (false) fields."
    )
    sort: Literal["name", "field_type", "is_required", "sort_order", "is_active"] = (
        Field("name", description="The column to order by; the id breaks ties.")
    )
    descending: bool = Field(
        False, description="Order from the highest to the lowest (Z to A)."
    )


def _options(value: list[str], info: ValidationInfo) -> list[str]:
    """A select's options, trimmed, without empties or repeats; no options for the other types."""
    kept = list(dict.fromkeys(option.strip() for option in value if option.strip()))
    field_type = info.data.get("field_type")
    if field_type == "select" and not kept:
        raise ValueError(OPTIONS_MISSING)
    if field_type not in (None, "select"):
        return []
    return kept


Options = Annotated[
    list[Annotated[str, StringConstraints(max_length=100), Field(json_schema_extra=IN_OWN_WORDS)]],
    Field(max_length=100),
]


class FieldIn(Schema):
    name: _text(100, 1) = Field(
        description="The field's name, unique among the active fields."
    )
    field_type: FieldType = Field(
        "text", description="Its type: text, number, date, boolean, select or textarea."
    )
    options: Options = Field([], description="The choices of a select field.")
    is_required: bool = Field(
        False, description="Whether every card must have a value when saved in full."
    )
    sort_order: int = Field(0, ge=0, le=INT4_MAX, description="Its place on the card, lowest first.")

    _check_options = field_validator("options")(_options)


class FieldPatchIn(FieldRefIn):
    name: _text(100, 1) | None = Field(None, description="The new name.")
    field_type: FieldType | None = Field(
        None, description="The new type; not possible once cards have values."
    )
    options: Options | None = Field(
        None, description="The new choices of a select field."
    )
    is_required: bool | None = Field(None, description="Whether it is required.")
    sort_order: int | None = Field(None, ge=0, le=INT4_MAX, description="The new place on the card.")
    is_active: bool | None = Field(
        None, description="Whether the field is shown on the cards."
    )

    @field_validator("options")
    @classmethod
    def _check_options(
        cls, value: list[str] | None, info: ValidationInfo
    ) -> list[str] | None:
        if value is None:
            return None
        # The type may come from the stored field: the service checks a select keeps an option.
        return list(dict.fromkeys(option.strip() for option in value if option.strip()))


class FieldRow(Schema):
    id: UUID = Field(description="The field's id.")
    name: str = Field(description="Name.")
    field_type: FieldType = Field(description="Type.")
    options: list[str] = Field(description="The choices of a select field.")
    is_required: bool = Field(description="Whether it is required.")
    sort_order: int = Field(description="Place on the card.")
    is_active: bool = Field(description="Whether it is shown on the cards.")


FieldPage = Page[FieldRow]


class FieldValueRow(Schema):
    """What a card keeps in one of its custom fields, with the card and the field by name."""

    customer: str = Field(description="The card's name.")
    phone: str | None = PHONE
    email: str | None = EMAIL
    field: str = Field(description="The custom field's name.")
    value: str = Field(description="What the card keeps in it.")


FieldValuePage = Page[FieldValueRow]
