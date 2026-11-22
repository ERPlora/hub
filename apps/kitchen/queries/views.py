"""What the kitchen reads of a ticket: the views of a dish and of a ticket, what Sales says today of each line, and
the views of the saved tickets.
"""

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field, fields
from decimal import Decimal
from uuid import UUID

from apps.kitchen.models import ItemStatus, Ticket, TicketItem
from apps.kitchen.queries.reads import STRUCK, TO_DO
from apps.sale.models import OrderLine
from base.queries.people import without_address


@dataclass
class LineFacts:
    """What Sales says today of the line of a dish: voided, and its check's status."""

    removed_at: dt.datetime | None
    void_reason: str
    order_id: UUID
    order_status: str
    order_closed_at: dt.datetime | None


@dataclass
class ItemView:
    id: UUID
    position: int
    sale_line_id: UUID | None
    product_id: UUID | None
    category_id: UUID | None
    name: str
    quantity: Decimal
    unit: str
    notes: str
    station_id: UUID | None
    station_name: str
    destination: str
    printer_usage: str
    printer_name: str
    status: str
    void_reason: str
    ready_at: dt.datetime | None
    total: int
    facts: LineFacts | None = None
    modifiers: list[str] = field(default_factory=list)
    allergy: list[str] = field(default_factory=list)
    allergy_in_dish: list[str] = field(default_factory=list)
    menu_name: str = ""
    menu_dish: int = 0

    @property
    def menu_line_id(self) -> UUID | None:
        """The menu's line of the check this dish is a dish of: the dishes of one menu share it."""
        return self.sale_line_id if self.menu_dish else None

    @property
    def struck(self) -> bool:
        return self.status in STRUCK

    @property
    def to_do(self) -> bool:
        return self.status in TO_DO


#: What a saved dish keeps of its view, by the same names: all of it but what Sales says of its line today.
SAVED = tuple(column.name for column in fields(ItemView) if column.name != "facts")


@dataclass
class TicketView:
    id: UUID
    number: str
    day: dt.date
    sequence: int
    order_id: UUID | None
    round_no: int
    label: str
    order_type: str
    priority: str
    status: str
    notes: str
    waiter: str
    received_at: dt.datetime
    started_at: dt.datetime | None
    ready_at: dt.datetime | None
    served_at: dt.datetime | None
    cancelled_at: dt.datetime | None
    rush_count: int
    saved: bool
    items: list[ItemView] = field(default_factory=list)

    @property
    def short_number(self) -> str:
        return self.number[-4:]

    @property
    def live_items(self) -> list[ItemView]:
        return [item for item in self.items if not item.struck]

    @property
    def total(self) -> int:
        return sum(
            item.total for item in self.items if item.status != ItemStatus.VOIDED
        )


@dataclass(frozen=True)
class Change:
    """What Sales did that changes a ticket: ``item_voided``, ``cancelled``, ``ready`` or ``served``."""

    kind: str
    at: dt.datetime
    item_id: UUID | None = None
    notes: str = ""


def _item_view(item: TicketItem, facts: LineFacts | None) -> ItemView:
    return ItemView(**{name: getattr(item, name) for name in SAVED}, facts=facts)


def line_facts(line_ids: Iterable[UUID]) -> dict[UUID, LineFacts]:
    ids = [line_id for line_id in line_ids if line_id]
    if not ids:
        return {}
    rows = OrderLine.objects.filter(pk__in=ids).values(
        "id",
        "removed_at",
        "void_reason",
        "order_id",
        "order__status",
        "order__closed_at",
    )
    return {
        row["id"]: LineFacts(
            removed_at=row["removed_at"],
            void_reason=row["void_reason"],
            order_id=row["order_id"],
            order_status=row["order__status"],
            order_closed_at=row["order__closed_at"],
        )
        for row in rows
    }


def saved_views(tickets: Iterable[Ticket]) -> list[TicketView]:
    """The views of saved tickets (their items prefetched or not), with what Sales says of their lines."""
    tickets = list(tickets)
    items_of = {ticket.id: list(ticket.items.all()) for ticket in tickets}
    facts = line_facts(
        item.sale_line_id for items in items_of.values() for item in items
    )
    return [
        TicketView(
            id=ticket.id,
            number=ticket.number,
            day=ticket.day,
            sequence=ticket.sequence,
            order_id=ticket.order_id,
            round_no=ticket.round_no,
            label=ticket.label,
            order_type=ticket.order_type,
            priority=ticket.priority,
            status=ticket.status,
            notes=ticket.notes,
            # A colleague's address only reaches whoever sees the team's contact details: a ticket saved with one reads
            # without it.
            waiter=without_address(ticket.waiter),
            received_at=ticket.received_at,
            started_at=ticket.started_at,
            ready_at=ticket.ready_at,
            served_at=ticket.served_at,
            cancelled_at=ticket.cancelled_at,
            rush_count=ticket.rush_count,
            saved=True,
            items=[
                _item_view(item, facts.get(item.sale_line_id))
                for item in items_of[ticket.id]
            ],
        )
        for ticket in tickets
    ]
