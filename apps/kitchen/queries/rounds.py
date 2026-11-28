"""The rounds Sales fired that the kitchen has not saved yet, read from Sales' lines and shown as tickets «not saved
yet», with the number they will have and their dishes routed by today's routing.
"""

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from decimal import Decimal
from uuid import UUID

from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.kitchen.allergy import frozen
from apps.kitchen.models import DayCounter, Destination, ItemStatus, KitchenSettings, Station, TicketItem, TicketStatus
from apps.kitchen.queries.reads import business_day, number_of
from apps.kitchen.queries.routing import Routing, routing
from apps.kitchen.queries.views import ItemView, LineFacts, TicketView
from apps.sale.models.orders import Order, OrderLine
from apps.sale.queries.people import person_names

#: How long after its check closed a round the kitchen never saved is still read from Sales.
UNSAVED_WINDOW = dt.timedelta(days=1)


@dataclass
class Round:
    """The lines of one check fired together (same round, same moment): one ticket."""

    order: Order
    round_no: int
    fired_at: dt.datetime
    lines: list[OrderLine] = field(default_factory=list)
    #: Who sent it, by the name a person reads (``person_names``).
    waiter: str = ""

    @property
    def anchor(self) -> OrderLine:
        return self.lines[0]


def pending_lines(settings: KitchenSettings, order_ids: Iterable[UUID] | None = None) -> list[OrderLine]:
    """The lines Sales fired (not services) since the kitchen receives, that no dish holds yet, of the
    checks still open or closed within the last day — a kitchen that never writes (on paper) does not read
    a growing past (the relay's reaction saves every round a moment after it is fired, so the window only
    covers the time until it arrives). Two reads: the open checks by
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
    found = [line for line in found if cooks(line)]
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
    names = person_names(rnd.anchor.created_by for rnd in rounds.values())
    for rnd in rounds.values():
        rnd.waiter = names.get(rnd.anchor.created_by, rnd.anchor.created_by)
    return list(rounds.values())


def menu_dishes(line: OrderLine) -> list[dict]:
    """The dishes of a menu's line (SALE-F12, as Menus answered when it was ordered) that are cooked: a
    service never is. None for a line ordered on its own."""
    if line.combo_id is None:
        return []
    return [dish for dish in line.combo.get("components", []) if not dish.get("is_service")]


def cooks(line: OrderLine) -> bool:
    """A menu is cooked when one of its dishes is not a service (Menus never sells one with nothing picked):
    a menu of services only has nothing to cook, like a service line."""
    return line.combo_id is None or bool(menu_dishes(line))


def line_options(line: OrderLine) -> list[str]:
    """The options chosen for the line (SALE-F11) by the names the cook reads (Modifiers' kitchen names, else
    their names), in the order chosen."""
    return [pick["kitchen_name"] for pick in line.modifiers]


def dish_id(line_id: UUID, dish: int) -> UUID:
    """The id of a dish of a round: the id of its line or, for the dish ``n`` of a menu's line, that id with
    its lowest bits flipped by ``n``: still a UUIDv7 of the same moment, and the same every time it is worked
    out, so a round not saved yet and the saved one share the ids of its dishes."""
    return UUID(int=line_id.int ^ dish) if dish else line_id


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
        modifiers=line_options(line),
        **frozen(line.allergy, line.allergens),
    )


def dishes_of_menu(
    line: OrderLine, first_position: int, route: Routing, facts: LineFacts
) -> list[ItemView]:
    """The dishes of a menu's line (KITCHEN-F06): each one at the station of its own product (else of its
    category), the quantity times the menus ordered, under the menu's header (its kitchen name, else its
    name) and with the menu's note; the menu's amount on its first dish, so the ticket counts it once."""
    header = line.combo.get("kitchen_name") or line.name
    items = []
    for number, dish in enumerate(menu_dishes(line), start=1):
        product_id = UUID(dish["product_id"]) if dish.get("product_id") else None
        category_id = UUID(dish["category_id"]) if dish.get("category_id") else None
        item = dish_of(line, first_position + number - 1, route.station_for(product_id, category_id), facts)
        items.append(
            replace(
                item,
                id=dish_id(line.id, number),
                product_id=product_id,
                category_id=category_id,
                name=dish["product_name"],
                quantity=Decimal(dish["quantity"]) * line.quantity,
                unit="ud",
                total=line.line_total if number == 1 else 0,
                modifiers=[option["kitchen_name"] for option in dish.get("options", [])],
                **frozen(line.allergy, dish.get("allergens", [])),
                menu_name=header,
                menu_dish=number,
            )
        )
    return items


def round_view(rnd: Round, day: dt.date, sequence: int, route: Routing) -> TicketView:
    """A round not saved yet, as the kitchen will save it (normal, dine in: what only the send knows): a
    dish per line, and a menu's line, one per dish of the menu (KITCHEN-F06)."""
    items: list[ItemView] = []
    for line in rnd.lines:
        facts = LineFacts(
            line.removed_at,
            line.void_reason,
            line.order_id,
            rnd.order.status,
            rnd.order.closed_at,
            rnd.order.label,
        )
        if menu_dishes(line):
            items.extend(dishes_of_menu(line, len(items) + 1, route, facts))
        else:
            items.append(
                dish_of(
                    line,
                    len(items) + 1,
                    route.station_for(line.product_id, line.category_id),
                    facts,
                )
            )
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
        waiter=rnd.waiter or rnd.anchor.created_by,
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
