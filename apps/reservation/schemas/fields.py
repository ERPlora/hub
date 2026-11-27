"""What every schema of the reservation app shares: the messages and titles several use, the field types, the marks
of the ids a write names, and the inputs, pages and answers every operation is built from."""

from typing import Annotated, Generic, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints

from apps.reservation.models import MAX_GUESTS, MAX_MINUTES
from base.schemas.assistant import names

T = TypeVar("T")

SAY_FOR_WHOM = _("Say who the reservation is for: a customer, or the guest's name.")

# How the Reservations screens name the data the models do not (the assistant's card names each datum by its title).
GUEST = gettext_noop("Guest")
ZONE = gettext_noop("Zone")
BOOK_ANYWAY = gettext_noop("Book anyway")
ON_BEHALF_OF = gettext_noop("On behalf of the customer")


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Said = _text(100, 1)
GuestName = _text(200)
Phone = _text(60)
Email = _text(254)
Notes = _text(2000)
Guests = Annotated[int, Field(ge=1, le=MAX_GUESTS)]
Minutes = Annotated[int, Field(ge=1, le=MAX_MINUTES)]
Weekday = Annotated[int, Field(ge=0, le=6, json_schema_extra={"enum": list(range(7))})]

D_GUEST_NAME = "The guest's name as the staff say it at the door; empty takes the customer card's."
D_GUEST_PHONE = (
    "The guest's phone as typed, beside the guest's name or card; with no customer chosen, the live card with this "
    "number is used, or one is created."
)
#: The marks of the ids of the records a write names (``names``): the read that names each one, and by what.
A_RESERVATION = names("reservation.reservation.get", name=("label",))
AN_ENTRY = names("reservation.waitlist.get", name=("label",))
A_SLOT = names("reservation.time_slot.get", name=("label",))
A_BLOCK = names("reservation.blocked_date.get", name=("label",))
A_CUSTOMER = names("customer.customer.detail")
#: A table with its zone («5 (Terraza)»), as Tables names it: its number repeats across zones (hub#550).
A_TABLE = names("table.table.get", name=("label",))
D_LABEL = "The words it is named by, in the caller's language, as the book's screens say it: «{example}»."


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


class Reaction(Schema):
    """The input of a reaction to another app's event: what it needs, the rest of the payload ignored."""

    model_config = ConfigDict(extra="ignore")


class PageIn(In):
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


class NoIn(In):
    pass


class DeletedOut(Schema):
    id: UUID = Field(description="The id of what was deleted.")


class ChangedOut(Schema):
    changed: int = Field(description="How many rows changed.")
