"""The board (KITCHEN-F10, F13, F15, F31): the tickets in flight, by station, and what is left to cook."""

from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from live.context import OperationContext
from live.operations import operation

from apps.kitchen.models import Station, TicketStatus
from apps.kitchen.queries.outputs import ticket_out
from apps.kitchen.queries.reads import COOKING, IN_FLIGHT, current_settings
from apps.kitchen.queries.scope import ALL, find_scope, scoped, station_map
from apps.kitchen.queries.state import in_flight_views
from apps.kitchen.queries.views import ItemView, TicketView
from apps.kitchen.schemas.board import AllDayIn, AllDayOut, BoardIn, BoardOut

PRIORITY_RANK = {"rush": 0, "vip": 1, "normal": 2}
#: The most tickets each list of the board shows (a result stays under 256 KB).
BOARD_CAP = 200


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
        "asks": {
            "en": (
                "what's cooking right now?",
                "what's left on the grill?",
            ),
            "es": (
                "¿qué tiene pendiente ahora la plancha?",
                "¿qué hay en marcha en la pantalla?",
            ),
        },
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
        "asks": {
            "en": (
                "how many burgers are left to cook?",
                "how many of each dish do we still have to make?",
            ),
            "es": (
                "¿cuántas hamburguesas quedan por hacer?",
                "dame el total de platos pendientes de cada puesto",
            ),
        },
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
