"""What every schema of the staff app shares: text fields, pages, the messages and marks of several topics, and
naming a staff member by id or by name."""

from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import StringConstraints, ValidationInfo, field_validator

from base.schemas.assistant import names

T = TypeVar("T")

# Validation messages (English source, Spanish in locale/).
NO_MEMBER = _("Say which staff member: their id or their name.")
TIME_ORDER = _("The start time must be before the end time.")
END_BEFORE_START = _("The end date cannot be before the start date.")
RANGE_TOO_LONG = _("Ask for at most 731 days at a time.")

#: The longest range staff.availability.for_member answers (two years and a day, as the old module).
MAX_AVAILABILITY_DAYS = 731


# The columns each list sorts by, both ways ("-" first = descending); id is always the tie-break.
def _both_ways(keys: tuple[str, ...]):
    return Literal[tuple(f"{sign}{key}" for key in keys for sign in ("", "-"))]


def _text(max_length: int, min_length: int = 0):
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Name = _text(100, 1)
Text100 = _text(100)
Text500 = _text(500)
Search = _text(100)
# Empty, or #RRGGBB.
Color = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^(#[0-9A-Fa-f]{6})?$")
]
MemberName = _text(200, 1)

# Field descriptions shared by several schemas (the assistant reads them).
D_MEMBER_ID = "The staff member's id. Give it, or their name in `member`."
D_MEMBER = "The staff member's name (first name, full name or part of it) when the id is not known."
D_ROLE_ID = (
    "Id of the role (a catalogue label such as «stylist»; it grants no permission)."
)
D_ROLE = "Name of the role, when its id is not known (an active role of this business)."
# The assistant's card names the record a write acts on by these reads (base/assistant/cards.py ``REFERS``), run as whoever
# asks, never by its id. A schedule says whose it is and a time-off request whose, of what kind and which days: everyone
# may have a «Regular schedule», and one person can ask for several absences.
A_MEMBER = names("staff.member.detail", name=("full_name",))
A_ROLE = names("staff.role.detail")
# What the card calls the record a write acts on.
MEMBER = gettext_noop("Staff member")
ROLE = gettext_noop("Role")
#: A person of the team by their id, named on the card; or by their name in ``member`` (``_said_by``).
MemberId = Annotated[UUID | None, Field(title=MEMBER, description=D_MEMBER_ID, json_schema_extra=A_MEMBER)]


def _member_named(value: str | None, info: ValidationInfo, id_field: str) -> str | None:
    """``member`` is required when the id is not given (and the id itself is valid)."""
    if value is None and id_field in info.data and info.data[id_field] is None:
        raise ValueError(str(NO_MEMBER))
    return value


def _said_by(id_field: str):
    """The validator of ``member`` in a schema that says a person by ``id_field`` or by their name."""
    return field_validator("member")(lambda value, info: _member_named(value, info, id_field))


# Pages: every list is paginated, limit ≤ 100.


class PageIn(Schema):
    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return (1 to 100)."
    )
    offset: int = Field(
        0, ge=0, description="How many rows to skip, for the next pages."
    )


class Page(Schema, Generic[T]):
    rows: list[T]
    total: int = Field(description="Rows that match, over all pages.")
    limit: int
    offset: int


class ByIdIn(Schema):
    id: UUID = Field(description="The id.")


class DeletedOut(Schema):
    id: UUID


# A staff member, by id or by name


class MemberRefIn(Schema):
    id: MemberId = None
    member: MemberName | None = Field(None, validate_default=True, description=D_MEMBER)

    _named = _said_by("id")


class MemberOfIn(Schema):
    member_id: MemberId = None
    member: MemberName | None = Field(None, validate_default=True, description=D_MEMBER)

    _named = _said_by("member_id")
