"""The tickets (KITCHEN-F19, F21): their list, the device notices, one ticket or one dish as a person names it, and
the tickets of a check.
"""

import datetime as dt
import re
from collections.abc import Callable
from uuid import UUID

from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import INTERNAL, operation

from apps.kitchen.models import KitchenSettings, Ticket, TicketItem
from apps.kitchen.queries.outputs import item_out, row_out, ticket_out
from apps.kitchen.queries.reads import IN_FLIGHT, MAX_CANDIDATES, STRUCK, business_day, current_settings
from apps.kitchen.queries.rounds import unsaved_views
from apps.kitchen.queries.scope import station_map
from apps.kitchen.queries.state import effective, in_flight_views
from apps.kitchen.queries.views import ItemView, TicketView, saved_views
from apps.kitchen.schemas.fields import ItemRefIn, TicketRefIn
from apps.kitchen.schemas.tickets import (
    ByOrderIn,
    ItemOut,
    NoticesIn,
    NoticesOut,
    TicketListIn,
    TicketOut,
    TicketPage,
    TicketsOut,
)
from apps.sale.models.orders import OrderLine
from base.ordering import list_order
from base.text_search import contains_text

TICKET_NOT_FOUND = _("That kitchen ticket does not exist in this business.")
TICKET_AMBIGUOUS = _(
    "“%(said)s” matches several tickets: %(names)s. Say which one by its number."
)
DISH_NOT_FOUND = _("That dish is on no kitchen ticket of this business.")
FULL_NUMBER = re.compile(r"^\d{8}-\d{1,4}$")


def _matches(view: TicketView, params: TicketListIn) -> bool:
    if params.search:
        text = params.search.strip().casefold()
        if text not in view.number.casefold() and text not in view.label.casefold():
            return False
    return all(
        value is None or getattr(view, name) == value
        for name, value in (
            ("status", params.status),
            ("order_type", params.order_type),
            ("priority", params.priority),
        )
    )


def merged_page(  # noqa: PLR0913, PLR0917
    first: list[dict],
    rest,
    key: Callable[[dict], tuple],
    descending: bool,
    offset: int,
    limit: int,
    row: Callable,
) -> tuple[list[dict], int]:
    """A page of two sorted sources: ``first`` (few rows, in memory) and ``rest`` (a sorted queryset of
    any size, read only around the page). Returns the page's rows and the total."""
    first = sorted(first, key=key, reverse=descending)

    def before(a: tuple, b: tuple) -> bool:
        return a > b if descending else a < b

    skip = max(0, offset - len(first))
    window = [row(ticket) for ticket in rest[skip : offset + limit]]
    included = first
    if skip:
        pivot = key(row(rest[skip - 1]))
        included = [item for item in first if not before(key(item), pivot)]
    start = skip + (len(first) - len(included))
    merged = sorted(window + included, key=key, reverse=descending)
    return merged[offset - start : offset - start + limit], len(first) + rest.count()


def _final_row(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "number": ticket.number,
        "short_number": ticket.short_number,
        "label": ticket.label,
        "order_type": ticket.order_type,
        "priority": ticket.priority,
        "status": ticket.status,
        "round_no": ticket.round_no,
        "items_count": ticket.items_alive,
        "total": ticket.total,
        "received_at": ticket.received_at,
        "order_id": ticket.order_id,
        "saved": True,
    }


@operation(
    "kitchen.ticket.list",
    kind="query",
    permission="kitchen.view_ticket",
    input=TicketListIn,
    output=TicketPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what got cancelled on the display today?",
                "list this morning's rushes",
            ),
            "es": (
                "¿qué se anuló ayer en la pantalla?",
                "busca las urgentes de esta mañana",
            ),
        },
        "description": "List the kitchen tickets, newest first, searching their number or label (Table 4) and "
        "filtering by status, type or priority («which tickets were cancelled today»)."
    },
)
def list_tickets(ctx: OperationContext, params: TicketListIn) -> dict:
    field_name = params.sort.lstrip("-")
    descending = params.sort.startswith("-")
    in_flight = [
        row_out(view)
        for view in in_flight_views(current_settings())
        if _matches(view, params)
    ]
    final = (
        Ticket.objects.filter(is_deleted=False)
        .exclude(status__in=IN_FLIGHT)
        .annotate(items_alive=Count("items", filter=~Q(items__status__in=STRUCK)))
    )
    if params.search:
        final = final.filter(contains_text(params.search, "number", "label"))
    for name in ("status", "order_type", "priority"):
        value = getattr(params, name)
        if value is not None:
            final = final.filter(**{name: value})
    final = final.order_by(*list_order(field_name, descending=descending))
    rows, total = merged_page(
        in_flight,
        final,
        key=lambda row: (row[field_name], row["id"]),
        descending=descending,
        offset=params.offset,
        limit=params.limit,
        row=_final_row,
    )
    return {
        "rows": rows,
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
    }


#: How far back the device notices go when nobody says (the shell tells each row once per device).
NOTICES_WINDOW = dt.timedelta(hours=24)


@operation(
    "kitchen.ticket.notices",
    kind="query",
    permission="kitchen.view_ticket",
    input=NoticesIn,
    output=NoticesOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "any new rounds just in?",
                "what has just come in?",
            ),
            "es": (
                "¿hay alguna comanda nueva?",
                "¿qué acaba de llegar a la pantalla?",
            ),
        },
        "description": "The new kitchen tickets, the newest first, with their destination, dishes and waiter; "
        "a round fired by Sales is included before the relay saves it, with the same id it keeps afterwards."
    },
)
def notices(ctx: OperationContext, params: NoticesIn) -> dict:
    since = params.since or timezone.now() - NOTICES_WINDOW
    settings = current_settings()
    saved = Ticket.objects.filter(is_deleted=False, received_at__gte=since).prefetch_related("items")
    views = [
        view
        for view in [*saved_views(saved), *unsaved_views(settings)]
        if view.received_at >= since
    ]
    views.sort(key=lambda view: (view.received_at, view.id), reverse=True)
    return {
        "rows": [
            {
                "id": view.id,
                "at": view.received_at,
                "number": view.number,
                "label": view.label,
                "dish_names": ", ".join(item.name for item in view.live_items),
                "waiter": view.waiter,
            }
            for view in views[: params.limit]
        ]
    }


def _today() -> dt.date:
    return business_day(timezone.now())


def _one(said: str, candidates: list[TicketView]) -> TicketView:
    if not candidates:
        raise NotFound(str(TICKET_NOT_FOUND), code="kitchen.ticket_not_found")
    if len(candidates) > 1:
        names = ", ".join(
            f"#{view.short_number} {view.label}".strip()
            for view in sorted(candidates, key=lambda view: view.received_at)[
                :MAX_CANDIDATES
            ]
        )
        raise Conflict(
            str(TICKET_AMBIGUOUS) % {"said": said, "names": names},
            code="kitchen.ticket_ambiguous",
        )
    return candidates[0]


def find_ticket_view(ref: TicketRefIn, settings: KitchenSettings) -> TicketView:
    """A ticket by its id, its number («12», «#0012», «20261014-0012») or its label («Table 4»): saved
    or a round not saved yet, as Sales left it."""
    saved = Ticket.objects.filter(is_deleted=False).prefetch_related("items")
    if ref.ticket_id is not None:
        found = saved.filter(pk=ref.ticket_id).first()
        if found is not None:
            return effective(saved_views([found])[0], settings)[0]
        return _one(
            str(ref.ticket_id),
            [
                effective(view, settings)[0]
                for view in unsaved_views(settings)
                if view.id == ref.ticket_id
            ],
        )
    said = ref.ticket.strip()
    text = said.lstrip("#").strip()
    in_flight = in_flight_views(settings)
    if FULL_NUMBER.match(text):
        day, sequence = text.split("-")
        number = f"{day}-{int(sequence):04d}"
        matches = [view for view in in_flight if view.number == number]
        return _one(
            said,
            matches
            or [effective(v, settings)[0] for v in saved_views(saved.filter(number=number))],
        )
    if text.isdigit():
        sequence = int(text)
        matches = [view for view in in_flight if view.sequence == sequence]
        today = [view for view in matches if view.day == _today()]
        if matches:
            return _one(said, today if len(matches) > 1 and today else matches)
        recent = saved.filter(sequence=sequence).order_by("-received_at", "-id")[:1]
        return _one(
            said, [effective(view, settings)[0] for view in saved_views(recent)]
        )
    exact = [view for view in in_flight if view.label.casefold() == text.casefold()]
    return _one(
        said,
        exact
        or [view for view in in_flight if text.casefold() in view.label.casefold()],
    )


@operation(
    "kitchen.ticket.get",
    kind="query",
    permission="kitchen.view_ticket",
    input=TicketRefIn,
    output=TicketOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how far along is number 12?",
                "show me number 12 with its dishes",
            ),
            "es": (
                "¿cómo van los platos de la 12?",
                "¿qué platos le quedan a la 7?",
            ),
        },
        "description": "One kitchen ticket with its dishes and their state, by its id, its number («ticket 12») or "
        "its label («how is table 4 going»)."
    },
)
def get_ticket(ctx: OperationContext, params: TicketRefIn) -> dict:
    return ticket_out(find_ticket_view(params, current_settings()))


def find_dish(item_id: UUID, settings: KitchenSettings) -> ItemView:
    """A dish by its id: of a saved ticket, or of a round not saved yet (the board shows it already and its dishes keep
    their ids once saved), as Sales left it."""
    ticket_id = (
        TicketItem.objects.filter(pk=item_id, ticket__is_deleted=False)
        .values_list("ticket_id", flat=True)
        .first()
    )
    if ticket_id is not None:
        views = saved_views(Ticket.objects.filter(pk=ticket_id).prefetch_related("items"))
    else:
        views = unsaved_views(settings)
    holder = next((view for view in views if any(item.id == item_id for item in view.items)), None)
    if holder is None:
        raise NotFound(str(DISH_NOT_FOUND), code="kitchen.item_not_found")
    return next(item for item in effective(holder, settings)[0].items if item.id == item_id)


@operation(
    "kitchen.item.get",
    kind="query",
    permission="kitchen.view_ticket",
    input=ItemRefIn,
    output=ItemOut,
    ai=INTERNAL,
)
def get_item(ctx: OperationContext, params: ItemRefIn) -> dict:
    """One dish by its id, for the assistant's card (``schemas.A_DISH``): the screens and the model read the dishes with
    their ticket, so it is no tool of the assistant nor a route of the API."""
    return item_out(find_dish(params.id, current_settings()), station_map())


@operation(
    "kitchen.ticket.by_order",
    kind="query",
    permission="kitchen.view_ticket",
    input=ByOrderIn,
    output=TicketsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which rounds has table 4's check sent?",
                "show me the rounds of this check",
            ),
            "es": (
                "¿qué rondas ha mandado la cuenta de la mesa 4?",
                "¿cómo van los platos de esta cuenta?",
            ),
        },
        "description": "The kitchen tickets of a check of Sales (its rounds, also the ones of a check merged into "
        "it), the newest round first, with their dishes and their state."
    },
)
def tickets_of_order(ctx: OperationContext, params: ByOrderIn) -> dict:
    settings = current_settings()
    lines = OrderLine.objects.filter(order_id=params.order_id).values("id")
    saved = Ticket.objects.filter(is_deleted=False).filter(
        Exists(TicketItem.objects.filter(ticket=OuterRef("pk"), sale_line_id__in=lines))
    )
    views = saved_views(saved.prefetch_related("items")) + unsaved_views(
        settings, [params.order_id]
    )
    views = [effective(view, settings)[0] for view in views]
    views.sort(key=lambda view: (view.received_at, view.id), reverse=True)
    stations = station_map()
    return {"tickets": [ticket_out(view, stations) for view in views]}
