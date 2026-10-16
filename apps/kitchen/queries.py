"""Read operations of the kitchen app (``READ ONLY``): the board, what is left to cook, the tickets, the
tickets of a check, the stations, the routing, the settings and the history.

Phase 1 has no relay of events, so the kitchen reads what Sales did (WORKBOOK «A qué reacciona»):

- a round Sales fired that the kitchen has not saved yet is read from Sales' lines (``pending_rounds``)
  and shown as a ticket «not saved yet» (``saved = False``), with the id of its first line, the number
  it will have and its dishes routed by today's routing; the first write of the kitchen saves it
  (services.settle);
- what Sales did after (a line voided, the check voided or charged) is applied when read by
  ``effective`` (KITCHEN-F27, F28, F29), without writing; services.settle applies the same function
  and saves its changes with their History.

services.py reuses these helpers inside its own transaction. Every list pages (``limit`` ≤ 100) with
``id`` as the last tie-break. ``find_*`` resolve how a person names a record (assistant, voice): by id,
else a number or an exact name, else the only one that contains it; several → 409 ``*_ambiguous``.
"""

import datetime as dt
import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from decimal import Decimal
from uuid import UUID

from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.kitchen.models import (
    CategoryRoute,
    DayCounter,
    Destination,
    ItemStatus,
    KitchenSettings,
    LogEntry,
    ProductRoute,
    Station,
    Ticket,
    TicketItem,
    TicketStatus,
)
from apps.kitchen.schemas import (
    AllDayIn,
    AllDayOut,
    BoardIn,
    BoardOut,
    ByOrderIn,
    LogListIn,
    LogPage,
    NoIn,
    RoutingListIn,
    RoutingPage,
    SettingsOut,
    StationListIn,
    StationPage,
    TicketListIn,
    TicketOut,
    TicketPage,
    TicketRefIn,
    TicketsOut,
)
from apps.sale.models import Order, OrderLine

TICKET_NOT_FOUND = _("That kitchen ticket does not exist in this business.")
TICKET_AMBIGUOUS = _(
    "“%(said)s” matches several tickets: %(names)s. Say which one by its number."
)
STATION_NOT_FOUND = _("That station does not exist in this business.")
STATION_AMBIGUOUS = _("“%(said)s” matches several stations: %(names)s. Say which one.")

IN_FLIGHT = (TicketStatus.PENDING, TicketStatus.PREPARING, TicketStatus.READY)
COOKING = (TicketStatus.PENDING, TicketStatus.PREPARING)
TO_DO = (ItemStatus.PENDING, ItemStatus.PREPARING)
STRUCK = (ItemStatus.VOIDED, ItemStatus.CANCELLED)
PRIORITY_RANK = {"rush": 0, "vip": 1, "normal": 2}
#: The most tickets each list of the board shows (a result stays under 256 KB).
BOARD_CAP = 200
#: How many names an ambiguous reference lists.
MAX_CANDIDATES = 5
#: A settings row lost (a database emptied): the kitchen receives everything.
EPOCH = dt.datetime(2000, 1, 1, tzinfo=dt.UTC)
NONE_SAID = "none"
#: How long after its check closed a round the kitchen never saved is still read from Sales.
UNSAVED_WINDOW = dt.timedelta(days=1)
FULL_NUMBER = re.compile(r"^\d{8}-\d{1,4}$")

FACTORY = {
    "show_timer": True,
    "warning_minutes": 15,
    "critical_minutes": 30,
    "color_coding": True,
    "sound_enabled": True,
    "sound_volume": 70,
    "sound_tone": "chime",
    "print_pass": False,
    "works_from_screen": True,
    "default_order_type": "dine_in",
}


# --- The business's clock ------------------------------------------------------------------------


def business_zone():
    """The business's time zone (phase 1: ``settings.TIME_ZONE``, Europe/Madrid; the Hub keeps no zone yet)."""
    return timezone.get_current_timezone()


def zone_name() -> str:
    zone = business_zone()
    return getattr(zone, "key", str(zone))


def business_day(moment: dt.datetime) -> dt.date:
    return timezone.localtime(moment, business_zone()).date()


def start_of(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, dt.time.min, tzinfo=business_zone())


def number_of(day: dt.date, sequence: int) -> str:
    return f"{day:%Y%m%d}-{sequence:04d}"


# --- Settings --------------------------------------------------------------------------------------


def current_settings() -> KitchenSettings:
    """The settings row, or the factory values (receiving everything) when it is missing."""
    row = KitchenSettings.objects.first()
    return row if row is not None else KitchenSettings(**FACTORY, receiving_since=EPOCH)


def settings_out(row: KitchenSettings) -> dict:
    return {**{name: getattr(row, name) for name in FACTORY}, "timezone": zone_name()}


# --- What the kitchen reads of a ticket ----------------------------------------------------------


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

    @property
    def struck(self) -> bool:
        return self.status in STRUCK

    @property
    def to_do(self) -> bool:
        return self.status in TO_DO


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
    return ItemView(
        id=item.id,
        position=item.position,
        sale_line_id=item.sale_line_id,
        product_id=item.product_id,
        category_id=item.category_id,
        name=item.name,
        quantity=item.quantity,
        unit=item.unit,
        notes=item.notes,
        station_id=item.station_id,
        station_name=item.station_name,
        destination=item.destination,
        printer_usage=item.printer_usage,
        printer_name=item.printer_name,
        status=item.status,
        void_reason=item.void_reason,
        ready_at=item.ready_at,
        total=item.total,
        facts=facts,
    )


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
            waiter=ticket.waiter,
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


# --- Rounds Sales fired that the kitchen has not saved -------------------------------------------


@dataclass
class Round:
    """The lines of one check fired together (same round, same moment): one ticket."""

    order: Order
    round_no: int
    fired_at: dt.datetime
    lines: list[OrderLine] = field(default_factory=list)

    @property
    def anchor(self) -> OrderLine:
        return self.lines[0]


def pending_lines(settings: KitchenSettings, order_ids: Iterable[UUID] | None = None) -> list[OrderLine]:
    """The lines Sales fired (not services) since the kitchen receives, that no dish holds yet, of the
    checks still open or closed within the last day — a kitchen that never writes (on paper) does not read
    a growing past (phase 2's relay saves every round when it is fired). Two reads: the open checks by
    their status (Sales' index), the recently closed ones by their closing time."""
    lines = OrderLine.objects.filter(fired_at__isnull=False, is_service=False).filter(
        ~Exists(TicketItem.objects.filter(sale_line_id=OuterRef("pk")))
    )
    if settings.receiving_since:
        lines = lines.filter(fired_at__gte=settings.receiving_since)
    if order_ids is not None:
        lines = lines.filter(order_id__in=list(order_ids))
    open_checks = Order.objects.filter(status=Order.Status.OPEN).values("id")
    closed_lately = Order.objects.filter(
        status__in=(Order.Status.COMPLETED, Order.Status.VOIDED),
        closed_at__gte=timezone.now() - UNSAVED_WINDOW,
    ).values("id")
    found = [
        *lines.filter(order_id__in=open_checks).select_related("order"),
        *lines.filter(order_id__in=closed_lately).select_related("order"),
    ]
    found.sort(key=lambda line: (line.fired_at, line.order_id, line.round_no, line.position, line.id))
    return found


def pending_rounds(
    settings: KitchenSettings, order_ids: Iterable[UUID] | None = None
) -> list[Round]:
    """The rounds not saved yet, in the order their numbers are given (when fired, then the check)."""
    rounds: dict[tuple, Round] = {}
    for line in pending_lines(settings, order_ids):
        key = (line.order_id, line.round_no, line.fired_at)
        if key not in rounds:
            rounds[key] = Round(
                order=line.order, round_no=line.round_no, fired_at=line.fired_at
            )
        rounds[key].lines.append(line)
    return list(rounds.values())


@dataclass
class Routing:
    """Where a dish goes today: its product's station, else its category's (active stations only)."""

    products: dict[UUID, Station]
    categories: dict[UUID, Station]

    def station_for(
        self, product_id: UUID | None, category_id: UUID | None
    ) -> Station | None:
        if product_id is not None and product_id in self.products:
            return self.products[product_id]
        if category_id is not None:
            return self.categories.get(category_id)
        return None


def product_routes(**filters):
    """The routes of products still in the catalogue (a product deleted in Inventory no longer counts)."""
    return ProductRoute.objects.filter(product__is_deleted=False, **filters)


def category_routes(**filters):
    """The routes of categories still in the catalogue."""
    return CategoryRoute.objects.filter(category__is_deleted=False, **filters)


def routing() -> Routing:
    live = {"station__is_active": True, "station__is_deleted": False}
    return Routing(
        products={
            route.product_id: route.station
            for route in product_routes(**live).select_related("station")
        },
        categories={
            route.category_id: route.station
            for route in category_routes(**live).select_related("station")
        },
    )


def line_notes(line: OrderLine) -> str:
    """The note the cook reads: the waiter's, and the reason of a comp (as Sales fires it)."""
    return " · ".join(
        text for text in (line.notes, line.gift_reason if line.is_gift else "") if text
    )


def provisional_numbers(rounds: list[Round]) -> list[tuple[dt.date, int]]:
    """The number each round will have: the next ones of its day's counter, in the rounds' order."""
    days = {business_day(rnd.fired_at) for rnd in rounds}
    last = dict(
        DayCounter.objects.filter(day__in=days).values_list("day", "last_number")
    )
    taken: dict[dt.date, int] = defaultdict(int)
    numbers = []
    for rnd in rounds:
        day = business_day(rnd.fired_at)
        taken[day] += 1
        numbers.append((day, last.get(day, 0) + taken[day]))
    return numbers


def dish_of(
    line: OrderLine, position: int, station: Station | None, facts: LineFacts | None
) -> ItemView:
    return ItemView(
        id=line.id,
        position=position,
        sale_line_id=line.id,
        product_id=line.product_id,
        category_id=line.category_id,
        name=line.name,
        quantity=line.quantity,
        unit=line.unit,
        notes=line_notes(line),
        station_id=station.id if station else None,
        station_name=station.name if station else "",
        destination=station.destination if station else Destination.BOTH,
        printer_usage=station.printer_usage if station else "kitchen",
        printer_name=station.printer_name if station else "",
        status=ItemStatus.PENDING,
        void_reason="",
        ready_at=None,
        total=line.line_total,
        facts=facts,
    )


def round_view(rnd: Round, day: dt.date, sequence: int, route: Routing) -> TicketView:
    """A round not saved yet, as the kitchen will save it (normal, dine in: what only the send knows)."""
    items = [
        dish_of(
            line,
            position,
            route.station_for(line.product_id, line.category_id),
            LineFacts(
                line.removed_at,
                line.void_reason,
                line.order_id,
                rnd.order.status,
                rnd.order.closed_at,
            ),
        )
        for position, line in enumerate(rnd.lines, start=1)
    ]
    return TicketView(
        id=rnd.anchor.id,
        number=number_of(day, sequence),
        day=day,
        sequence=sequence,
        order_id=rnd.order.id,
        round_no=rnd.round_no,
        label=rnd.order.label,
        order_type="dine_in",
        priority="normal",
        status=TicketStatus.PENDING,
        notes="",
        waiter=rnd.anchor.created_by,
        received_at=rnd.fired_at,
        started_at=None,
        ready_at=None,
        served_at=None,
        cancelled_at=None,
        rush_count=0,
        saved=False,
        items=items,
    )


def unsaved_views(
    settings: KitchenSettings, order_ids: Iterable[UUID] | None = None
) -> list[TicketView]:
    """The rounds not saved yet (of ``order_ids`` only, if given), each with the number it will have: they
    are numbered among every round not saved yet, so a check reads the numbers the board shows."""
    rounds = pending_rounds(settings)
    if not rounds:
        return []
    wanted = None if order_ids is None else set(order_ids)
    route = routing()
    return [
        round_view(rnd, day, sequence, route)
        for rnd, (day, sequence) in zip(
            rounds, provisional_numbers(rounds), strict=True
        )
        if wanted is None or rnd.order.id in wanted
    ]


# --- What Sales did after: the effective state (KITCHEN-F27, F28, F29) ----------------------------


def _latest(moments: Iterable[dt.datetime | None]) -> dt.datetime:
    known = [moment for moment in moments if moment is not None]
    return max(known) if known else timezone.now()


def _cancel(view: TicketView, at: dt.datetime) -> None:
    view.status = TicketStatus.CANCELLED
    view.cancelled_at = at
    for item in view.items:
        if item.status not in (ItemStatus.VOIDED, ItemStatus.SERVED):
            item.status = ItemStatus.CANCELLED


def _serve(view: TicketView, at: dt.datetime) -> None:
    view.status = TicketStatus.SERVED
    view.served_at = at
    view.ready_at = view.ready_at or at
    for item in view.items:
        if not item.struck:
            item.status = ItemStatus.SERVED
            item.ready_at = item.ready_at or at


def effective(
    view: TicketView, settings: KitchenSettings
) -> tuple[TicketView, list[Change]]:
    """The ticket as it stands after what Sales did to its lines and checks, and what changed.

    In order: a line voided in the till strikes its dish (F29) — the round with nothing alive left is
    cancelled, with only ready dishes left it goes to the pass —; every check of its lines voided
    cancels it (F28); every check charged in full (F27) serves it when it was ready before the charge,
    or when nobody marks it on a screen (every dish to paper only, or the kitchen on paper since before
    the charge). A ticket made by hand, or already served or cancelled, never changes here.
    """
    if view.status not in IN_FLIGHT or not any(item.facts for item in view.items):
        return view, []
    view = replace(view, items=[replace(item) for item in view.items])
    changes: list[Change] = []

    voided = [
        item
        for item in view.items
        if item.facts
        and item.facts.removed_at
        and item.status not in (*STRUCK, ItemStatus.SERVED)
    ]
    for item in voided:
        item.status = ItemStatus.VOIDED
        item.void_reason = item.facts.void_reason
        changes.append(
            Change("item_voided", item.facts.removed_at, item.id, item.void_reason)
        )
    if voided:
        at = _latest(item.facts.removed_at for item in voided)
        live = view.live_items
        if not live:
            _cancel(view, at)
            changes.append(Change("cancelled", at))
            return view, changes
        if view.status != TicketStatus.READY and all(
            item.status == ItemStatus.READY for item in live
        ):
            view.status = TicketStatus.READY
            view.ready_at = at
            view.started_at = view.started_at or at
            changes.append(Change("ready", at))

    linked = [item for item in view.live_items if item.facts]
    statuses = {item.facts.order_status for item in linked}
    if not linked or len(statuses) != 1:
        return view, changes
    closed = _latest(item.facts.order_closed_at for item in linked)
    if statuses == {Order.Status.VOIDED}:
        _cancel(view, closed)
        changes.append(Change("cancelled", closed))
    elif statuses == {Order.Status.COMPLETED}:
        if view.status == TicketStatus.READY:
            if view.ready_at is not None and view.ready_at <= closed:
                _serve(view, closed)
                changes.append(Change("served", closed))
        elif all(
            item.destination == Destination.PRINTER for item in view.live_items
        ) or (
            not settings.works_from_screen
            and closed >= (settings.screen_changed_at or EPOCH)
        ):
            _serve(view, closed)
            changes.append(Change("served", closed))
    return view, changes


def in_flight_views(
    settings: KitchenSettings, order_ids: Iterable[UUID] | None = None
) -> list[TicketView]:
    """Every ticket the kitchen holds as on the line (saved, or a round not saved yet), as Sales left it
    (``effective``): some of them may be served or cancelled by now."""
    saved = Ticket.objects.filter(
        is_deleted=False, status__in=IN_FLIGHT
    ).prefetch_related("items")
    if order_ids is not None:
        lines = OrderLine.objects.filter(order_id__in=list(order_ids)).values("id")
        saved = saved.filter(
            Exists(
                TicketItem.objects.filter(ticket=OuterRef("pk"), sale_line_id__in=lines)
            )
        )
    views = saved_views(saved) + unsaved_views(settings, order_ids)
    return [effective(view, settings)[0] for view in views]


# --- Stations and how a person names them --------------------------------------------------------


#: The whole board (no station chosen): «Todas», the pass.
ALL = object()


def station_map() -> dict[UUID, Station]:
    return {station.id: station for station in Station.objects.all()}


def find_station(station_id: UUID | None, said: str | None) -> Station:
    """A live station by its id, else by its exact name, else the only one whose name contains it."""
    stations = Station.objects.filter(is_deleted=False)
    if station_id is not None:
        found = stations.filter(pk=station_id).first()
        if found is None:
            raise NotFound(str(STATION_NOT_FOUND), code="kitchen.station_not_found")
        return found
    text = (said or "").strip()
    exact = list(stations.filter(name__iexact=text)[:2])
    candidates = exact or list(
        stations.filter(name__icontains=text).order_by("name", "id")[
            : MAX_CANDIDATES + 1
        ]
    )
    if not candidates:
        raise NotFound(str(STATION_NOT_FOUND), code="kitchen.station_not_found")
    if len(candidates) > 1:
        names = ", ".join(station.name for station in candidates[:MAX_CANDIDATES])
        raise Conflict(
            str(STATION_AMBIGUOUS) % {"said": text, "names": names},
            code="kitchen.station_ambiguous",
        )
    return candidates[0]


def find_scope(said: str | None):
    """``ALL`` (every station), ``None`` («none»: the dishes with no station) or a station's id."""
    text = (said or "").strip()
    if not text:
        return ALL
    if text.casefold() == NONE_SAID:
        return None
    try:
        station_id = UUID(text)
    except ValueError:
        return find_station(None, text).id
    # Only a live station: a tablet that remembers one deleted since is told so and goes back to every
    # station, instead of an empty board for ever.
    return find_station(station_id, None).id


def in_scope(item: ItemView, scope) -> bool:
    return scope is ALL or item.station_id == scope


def scoped(view: TicketView, scope) -> TicketView:
    """The ticket with the dishes of one station only (all of them with no station chosen)."""
    if scope is ALL:
        return view
    return replace(view, items=[item for item in view.items if in_scope(item, scope)])


# --- Turning views into outputs ------------------------------------------------------------------


def item_out(item: ItemView, stations: dict[UUID, Station]) -> dict:
    station = stations.get(item.station_id) if item.station_id else None
    return {
        "id": item.id,
        "position": item.position,
        "product_id": item.product_id,
        "name": item.name,
        "quantity": item.quantity,
        "unit": item.unit,
        "notes": item.notes,
        "station_id": item.station_id,
        "station_name": station.name if station else item.station_name,
        "station_color": station.color if station else "",
        "destination": item.destination,
        "printer_usage": item.printer_usage,
        "status": item.status,
        "void_reason": item.void_reason,
        "ready_at": item.ready_at,
    }


def ticket_out(
    view: TicketView,
    stations: dict[UUID, Station] | None = None,
    print_error: str | None = None,
) -> dict:
    stations = station_map() if stations is None else stations
    return {
        "id": view.id,
        "number": view.number,
        "short_number": view.short_number,
        "label": view.label,
        "order_type": view.order_type,
        "priority": view.priority,
        "status": view.status,
        "round_no": view.round_no,
        "waiter": view.waiter,
        "notes": view.notes,
        "order_id": view.order_id,
        "received_at": view.received_at,
        "started_at": view.started_at,
        "ready_at": view.ready_at,
        "served_at": view.served_at,
        "cancelled_at": view.cancelled_at,
        "rush_count": view.rush_count,
        "total": view.total,
        "saved": view.saved,
        "items": [item_out(item, stations) for item in view.items],
        "print_error": print_error,
    }


def row_out(view: TicketView) -> dict:
    return {
        "id": view.id,
        "number": view.number,
        "short_number": view.short_number,
        "label": view.label,
        "order_type": view.order_type,
        "priority": view.priority,
        "status": view.status,
        "round_no": view.round_no,
        "items_count": len(view.live_items),
        "total": view.total,
        "received_at": view.received_at,
        "order_id": view.order_id,
        "saved": view.saved,
    }


# --- The board (KITCHEN-F10, F13, F15, F31) ------------------------------------------------------


def _cooking_order(view: TicketView):
    return (PRIORITY_RANK.get(view.priority, 2), view.received_at, view.id)


def _chips(views: list[TicketView], stations: dict[UUID, Station]) -> list[dict]:
    ids = {item.station_id for view in views for item in view.live_items}
    known = sorted(
        (
            stations[station_id]
            for station_id in ids
            if station_id in stations and not stations[station_id].is_deleted
        ),
        key=lambda station: (station.sort_order, station.name.casefold(), station.id),
    )
    chips = [
        {"id": station.id, "name": station.name, "color": station.color}
        for station in known
    ]
    if None in ids:
        chips.append({"id": None, "name": "", "color": ""})
    return chips


@operation(
    "kitchen.ticket.board",
    kind="query",
    permission="kitchen.view_ticket",
    input=BoardIn,
    output=BoardOut,
    expose_api=True,
    ai={
        "description": "The kitchen display: the tickets being cooked (rush first, then VIP, then the oldest) and "
        "the ones waiting at the pass, with their dishes, for every station or one («what is pending on the "
        "grill»). Also what the cash close asks: the tickets not served yet."
    },
)
def board(ctx: OperationContext, params: BoardIn) -> dict:
    scope = find_scope(params.station)
    views = [
        view for view in in_flight_views(current_settings()) if view.status in IN_FLIGHT
    ]
    stations = station_map()
    cooking, ready = [], []
    for view in views:
        mine = scoped(view, scope)
        if view.status in COOKING and any(item.to_do for item in mine.items):
            cooking.append(mine)
        elif view.status == TicketStatus.READY and (scope is ALL or mine.live_items):
            ready.append(mine)
    cooking.sort(key=_cooking_order)
    ready.sort(key=lambda view: (view.ready_at or view.received_at, view.id))
    return {
        "cooking": [ticket_out(view, stations) for view in cooking[:BOARD_CAP]],
        "ready": [ticket_out(view, stations) for view in ready[:BOARD_CAP]],
        "cooking_count": len(cooking),
        "ready_count": len(ready),
        "stations": _chips(views, stations),
        "truncated": len(cooking) > BOARD_CAP or len(ready) > BOARD_CAP,
    }


@operation(
    "kitchen.ticket.all_day",
    kind="query",
    permission="kitchen.view_ticket",
    input=AllDayIn,
    output=AllDayOut,
    expose_api=True,
    ai={
        "description": "What is left to cook, added up per dish and station across every ticket being cooked, most "
        "first; for one station if named («how many burgers are left on the grill»)."
    },
)
def all_day(ctx: OperationContext, params: AllDayIn) -> dict:
    scope = find_scope(params.station)
    stations = station_map()
    totals: dict[tuple, Decimal] = defaultdict(Decimal)
    shown: dict[tuple, ItemView] = {}
    for view in in_flight_views(current_settings()):
        if view.status not in COOKING:
            continue
        for item in scoped(view, scope).items:
            if not item.to_do:
                continue
            key = (item.product_id or item.name.casefold(), item.unit, item.station_id)
            totals[key] += item.quantity
            shown.setdefault(key, item)
    rows = []
    for key, quantity in totals.items():
        item = shown[key]
        station = stations.get(item.station_id) if item.station_id else None
        rows.append(
            {
                "product_id": item.product_id,
                "name": item.name,
                "unit": item.unit,
                "station_id": item.station_id,
                "station_name": station.name if station else item.station_name,
                "quantity": quantity,
            }
        )
    rows.sort(
        key=lambda row: (
            -row["quantity"],
            row["name"].casefold(),
            row["station_name"].casefold(),
        )
    )
    return {"rows": rows}


# --- The tickets (KITCHEN-F19, F21) ----------------------------------------------------------------


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


def merged_page(
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
        final = final.filter(
            Q(number__icontains=params.search) | Q(label__icontains=params.search)
        )
    for name in ("status", "order_type", "priority"):
        value = getattr(params, name)
        if value is not None:
            final = final.filter(**{name: value})
    prefix = "-" if descending else ""
    final = final.order_by(f"{prefix}{field_name}", f"{prefix}id")
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
        "description": "One kitchen ticket with its dishes and their state, by its id, its number («ticket 12») or "
        "its label («how is table 4 going»)."
    },
)
def get_ticket(ctx: OperationContext, params: TicketRefIn) -> dict:
    return ticket_out(find_ticket_view(params, current_settings()))


@operation(
    "kitchen.ticket.by_order",
    kind="query",
    permission="kitchen.view_ticket",
    input=ByOrderIn,
    output=TicketsOut,
    expose_api=True,
    ai={
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


# --- Stations and routing (KITCHEN-F01 to F04) ---------------------------------------------------


def in_progress_by_station(settings: KitchenSettings) -> dict[UUID | None, int]:
    counts: dict[UUID | None, int] = defaultdict(int)
    for view in in_flight_views(settings):
        if view.status in COOKING:
            for item in view.items:
                if item.to_do:
                    counts[item.station_id] += 1
    return counts


def station_row(station: Station, in_progress: int, routes: int) -> dict:
    return {
        "id": station.id,
        "name": station.name,
        "color": station.color,
        "destination": station.destination,
        "printer_usage": station.printer_usage,
        "printer_name": station.printer_name,
        "sort_order": station.sort_order,
        "is_active": station.is_active,
        "in_progress": in_progress,
        "routes": routes,
    }


@operation(
    "kitchen.station.list",
    kind="query",
    permission="kitchen.view_ticket",
    input=StationListIn,
    output=StationPage,
    expose_api=True,
    ai={
        "description": "List the kitchen stations (grill, bar…) with their destination, printer, dishes in "
        "progress and how many products and categories go to them, searching by name."
    },
)
def list_stations(ctx: OperationContext, params: StationListIn) -> dict:
    stations = Station.objects.filter(is_deleted=False).annotate(
        product_count=Count(
            "product_routes",
            filter=Q(product_routes__product__is_deleted=False),
            distinct=True,
        ),
        category_count=Count(
            "category_routes",
            filter=Q(category_routes__category__is_deleted=False),
            distinct=True,
        ),
    )
    if params.search:
        stations = stations.filter(name__icontains=params.search)
    if params.is_active is not None:
        stations = stations.filter(is_active=params.is_active)
    counts = in_progress_by_station(current_settings())
    rows = [
        station_row(
            station,
            counts.get(station.id, 0),
            station.product_count + station.category_count,
        )
        for station in stations
    ]
    field_name = params.sort.lstrip("-")
    rows.sort(
        key=lambda row: (row[field_name], row["name"].casefold(), row["id"]),
        reverse=params.sort.startswith("-"),
    )
    return {
        "rows": rows[params.offset : params.offset + params.limit],
        "total": len(rows),
        "limit": params.limit,
        "offset": params.offset,
    }


@operation(
    "kitchen.routing.list",
    kind="query",
    permission="kitchen.view_ticket",
    input=RoutingListIn,
    output=RoutingPage,
    expose_api=True,
    ai={
        "description": "Which products and categories go to which station («where do the drinks go»), for every "
        "station or one, searching by the product's or category's name."
    },
)
def list_routing(ctx: OperationContext, params: RoutingListIn) -> dict:
    scope = find_scope(params.station)
    live = {"station__is_deleted": False}
    rows = [
        {
            "kind": "category",
            "target_id": route.category_id,
            "target_name": route.category.name,
            "station_id": route.station_id,
            "station_name": route.station.name,
        }
        for route in category_routes(**live).select_related(
            "category", "station"
        )
    ] + [
        {
            "kind": "product",
            "target_id": route.product_id,
            "target_name": route.product.name,
            "station_id": route.station_id,
            "station_name": route.station.name,
        }
        for route in product_routes(**live).select_related(
            "product", "station"
        )
    ]
    if scope is not ALL:
        rows = [row for row in rows if row["station_id"] == scope]
    if params.search:
        text = params.search.casefold()
        rows = [row for row in rows if text in row["target_name"].casefold()]
    rows.sort(
        key=lambda row: (row["kind"], row["target_name"].casefold(), row["target_id"])
    )
    return {
        "rows": rows[params.offset : params.offset + params.limit],
        "total": len(rows),
        "limit": params.limit,
        "offset": params.offset,
    }


# --- Settings and history (KITCHEN-F25, F26) -----------------------------------------------------


@operation(
    "kitchen.settings.get",
    kind="query",
    permission="kitchen.view_ticket",
    input=NoIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "The kitchen display settings: the clock, the amber and red minutes, the sound, the pass on "
        "paper, whether the kitchen works from the screen and the default ticket type."
    },
)
def get_settings(ctx: OperationContext, params: NoIn) -> dict:
    return settings_out(current_settings())


def log_row(entry: LogEntry) -> dict:
    return {
        "id": entry.id,
        "action": entry.action,
        "ticket_id": entry.ticket_id,
        "ticket_number": entry.ticket.number,
        "item_name": entry.item.name if entry.item else "",
        "station_name": entry.station.name if entry.station else "",
        "actor": entry.actor,
        "notes": entry.notes,
        "created_at": entry.created_at,
    }


@operation(
    "kitchen.log.list",
    kind="query",
    permission="kitchen.view_log",
    input=LogListIn,
    output=LogPage,
    expose_api=True,
    ai={
        "description": "The kitchen's history, newest first: what happened (received, dish ready, served, "
        "cancelled…), on which ticket and dish, who did it and when; searching the ticket's number or the notes, "
        "by action and by days."
    },
)
def list_log(ctx: OperationContext, params: LogListIn) -> dict:
    entries = LogEntry.objects.select_related("ticket", "item", "station")
    if params.search:
        entries = entries.filter(
            Q(ticket__number__icontains=params.search)
            | Q(notes__icontains=params.search)
        )
    if params.action is not None:
        entries = entries.filter(action=params.action)
    if params.ticket_id is not None:
        entries = entries.filter(ticket_id=params.ticket_id)
    if params.date_from is not None:
        entries = entries.filter(created_at__gte=start_of(params.date_from))
    if params.date_to is not None:
        entries = entries.filter(
            created_at__lt=start_of(params.date_to + dt.timedelta(days=1))
        )
    entries = entries.order_by("-created_at", "-id")
    page = entries[params.offset : params.offset + params.limit]
    return {
        "rows": [log_row(entry) for entry in page],
        "total": entries.count(),
        "limit": params.limit,
        "offset": params.offset,
    }
