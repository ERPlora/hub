"""What the schemas of the kitchen app share: the messages, the titles and the record marks the assistant's
card reads, the closed lists and the types and limits of the fields, the closed input and the input of a
reaction, pages, and naming a ticket, a dish or a station."""

from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints, model_validator

from base.schemas.assistant import names


T = TypeVar("T")

#: The most dishes a ticket made by hand takes.
MAX_ITEMS = 100

SAY_WHICH_TICKET = _("Say which ticket: its id, its number or its label.")
SAY_WHICH_STATION = _("Say which station: its id or its name.")
SAY_PRODUCT_OR_CATEGORY = _("Say one product or one category, not both.")
SAY_WHAT_DISH = _("Say which dish: a product of the catalogue or its name.")
ADD_A_DISH = _("Add at least one dish.")

# How the Kitchen screens name the data the models do not (the assistant's card names each datum by its title).
TICKET_TYPE = gettext_noop("Ticket type")
DISHES = gettext_noop("Dishes")
STATION_COLOUR = gettext_noop("Station colour")

# The assistant's card names the record a write acts on by these reads (base/assistant/cards.py ``REFERS``), run as whoever
# asks, never by its id: a ticket by its number, as the «Cancel ticket …?» dialog and its sheet say it; a dish and a
# station by their names, as the board and the stations' «Delete …?» dialog say them; a product and a category of
# Inventory by their names, as Inventory says them; a check of Sales by its title (else its amount) and a line of it by
# its dish, as Sales says them.
A_TICKET = names("kitchen.ticket.get", by="ticket_id", name=("number",))
A_DISH = names("kitchen.item.get")
A_STATION = names("kitchen.station.get", by="station_id")
A_PRODUCT = names("inventory.product.get")
A_CATEGORY = names("inventory.category.get")
A_CHECK = names("sale.record.get", by="order_id")
A_CHECK_LINE = names("sale.record.get", by="line_id")
#: The type of a round is the ticket's: the card says it by its label («Para llevar»), never by its code.
OF_ORDER_TYPE = {"choices_of": "order_type"}

TicketStatus = Literal["pending", "preparing", "ready", "served", "cancelled"]
ItemStatus = Literal["pending", "preparing", "ready", "served", "cancelled", "voided"]
OrderType = Literal["dine_in", "takeaway", "delivery"]
Priority = Literal["normal", "rush", "vip"]
Destination = Literal["both", "display", "printer"]
PrinterUsage = Literal["kitchen", "bar"]
SoundTone = Literal["chime", "bell", "buzzer"]
LogAction = Literal[
    "received",
    "created",
    "started",
    "ready",
    "item_ready",
    "item_recalled",
    "item_voided",
    "served",
    "recalled",
    "cancelled",
    "rushed",
    "unrushed",
    "reprinted",
    "deleted",
]
TicketSort = Literal[
    "received_at",
    "-received_at",
    "number",
    "-number",
    "status",
    "-status",
    "total",
    "-total",
]
StationSort = Literal[
    "sort_order", "-sort_order", "name", "-name", "in_progress", "-in_progress"
]


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Said = _text(120, 1)
Label = _text(120)
Notes = _text(2000)
Note = _text(255)
Reason = _text(255)
Hex = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]
Minutes = Annotated[int, Field(ge=1, le=120)]
Volume = Annotated[int, Field(ge=0, le=100)]
Quantity = Annotated[
    Decimal, Field(gt=0, le=Decimal("9999"), max_digits=12, decimal_places=3)
]


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


class Reaction(Schema):
    """The input of a reaction to another app's event: what it needs, the rest of the payload ignored."""

    model_config = ConfigDict(extra="ignore")


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


# ── References ───────────────────────────────────────────────────────────────────────────────────


class TicketRefIn(In):
    ticket_id: UUID | None = Field(None, description="The ticket's id.", json_schema_extra=A_TICKET)
    ticket: Said | None = Field(
        None,
        description="The ticket as a person says it: its number («12», «#0012», «20261014-0012») or its label "
        "(«Table 4»), when its id is not known.",
    )

    @model_validator(mode="after")
    def _ticket_named(self):
        _named(self.ticket_id, self.ticket, SAY_WHICH_TICKET)
        return self


class ItemRefIn(In):
    id: UUID = Field(description="The dish's id, as its ticket gives it.")


class _StationNamed(In):
    @model_validator(mode="after")
    def _station_named(self):
        _named(self.station_id, self.station, SAY_WHICH_STATION)
        return self


class StationRefIn(_StationNamed):
    station_id: UUID | None = Field(None, description="The station's id.", json_schema_extra=A_STATION)
    station: Said | None = Field(
        None, description="The station's name («grill»), when its id is not known."
    )


StationScope = Annotated[
    str | None,
    Field(
        None,
        max_length=120,
        description="Only one station: its id or its name («grill»), or «none» for the dishes with no "
        "station. Without it, every station (the pass).",
    ),
]
