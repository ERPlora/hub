"""The types, texts and record marks the schemas of Appointments share, their pages and the closed input."""

from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints

from base.schemas.assistant import names

T = TypeVar("T")

#: A booking lasts at most a day.
MAX_MINUTES = 1440
#: Services in one appointment, times in one batch, appointments in one bulk delete.
MAX_SERVICES = 10
MAX_BATCH = 50
MAX_BULK_DELETE = 100

#: How the assistant's card names an appointment, a repeating appointment, a blocked period and what booking one takes,
#: by what their reads answer and never by an id (base/assistant/cards.py).
AN_APPOINTMENT = names("appointment.appointment.get", name=("label",))
A_SERIES = names("appointment.recurring.get", name=("label",))
A_BLOCK = names("appointment.blocked_time.get", name=("label",))
A_CUSTOMER = names("customer.customer.detail")
A_SERVICE = names("service.service.get")
A_MEMBER = names("staff.member.detail", name=("full_name",))
#: What the card calls them, as their lists call one (or many): «Cita», «Citas», «Cita periódica»; a blocked period,
#: which no list shows, as this app's catalog calls one («Bloqueo»).
T_APPOINTMENT = gettext_noop("Appointment")
T_APPOINTMENTS = gettext_noop("Appointments")
T_SERIES = gettext_noop("Repeating appointment")
T_BLOCK = gettext_noop("Blocked period")

SAY_WHAT_TO_EDIT = _("Say what to change.")
END_BEFORE_START = _("The end cannot be before the start.")

Status = Literal[
    "pending", "confirmed", "in_progress", "completed", "cancelled", "no_show"
]
Source = Literal["counter", "phone", "online", "whatsapp"]


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Said = _text(200, 1)
Note = _text(2000)
Reason = _text(500)
Minutes = Annotated[int, Field(ge=1, le=MAX_MINUTES)]


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


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


D_START = "When it starts: the business's wall-clock date and time (2026-10-19 10:00), or an instant with its zone."
D_DURATION = "How many minutes it lasts; empty = the sum of its services (each the professional's own length if set)."
D_SERVICES = (
    "The services, in order (e.g. a cut then a colour), each by its id or its name."
)
D_CONFIRM_OVERLAP = "True only after the person saw the overlapping appointments and chose to book anyway (front desk only)."
#: How the assistant's card names the data no model of Citas names (hub#637): never the title pydantic makes up.
BOOK_EVEN_IF_IT_OVERLAPS = gettext_noop("Book even if it overlaps")


class NoIn(In):
    pass


class DeletedOut(Schema):
    id: UUID
