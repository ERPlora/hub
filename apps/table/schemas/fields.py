"""What the schemas of the table app share: the most guests of a party, the messages, titles and record marks
of several topics, the shape and status of a table, the closed input, naming a record as a person says it, and pages."""

from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints

from base.schemas.assistant import names

T = TypeVar("T")

#: A party may exceed the table's seats (it only warns); this is just a sanity cap.
MAX_GUESTS = 999

SAY_WHICH_ZONE = _("Say which zone: its id, or its name.")
SAY_WHICH_TABLE = _("Say which table: its id, or its number.")

# How the Tables screens name the data the models do not (the assistant's card names each datum by its title).
ZONE_COLOUR = gettext_noop("Zone colour")
DESTINATION_TABLE = gettext_noop("Destination table")
DESTINATION_ZONE = gettext_noop("Destination zone")
MOVE_TO_ZONE = gettext_noop("Move to zone")
# The record a write acts on (its ``id``), as the room's screens call it.
ZONE = gettext_noop("Zone")
TABLE = gettext_noop("Table")
CHECK = gettext_noop("Check")

#: The marks of the ids of the records a write names (``names``): the read that names each one, and by what.
A_ZONE = names("table.zone.get")
A_TABLE = names("table.table.get", name=("label",))
A_CHECK = names("table.session.get", name=("label",))
A_SALES_CHECK = names("sale.order.get", by="order_id", name=("label",))
A_CUSTOMER = names("customer.customer.detail")
A_RESERVATION = names("table.hold.by_reservation", by="reservation_id", name=("label",))
A_LINE = names("table.session.line")

Shape = Literal["square", "round", "rectangle"]
TableStatus = Literal["available", "occupied", "reserved", "blocked"]


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Said = _text(100, 1)


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


def _named(value_id, said, message) -> None:
    if value_id is None and not said:
        raise ValueError(str(message))


# ── Pages ────────────────────────────────────────────────────────────────────────────────────────


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
