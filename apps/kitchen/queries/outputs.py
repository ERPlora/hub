"""Turning the views of tickets and dishes into the outputs of the operations."""

from uuid import UUID

from apps.kitchen.models import Station
from apps.kitchen.queries.scope import station_map
from apps.kitchen.queries.views import ItemView, TicketView


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
        "modifiers": item.modifiers,
        "allergy": item.allergy,
        "allergy_in_dish": item.allergy_in_dish,
        "menu_name": item.menu_name,
        "menu_line_id": item.menu_line_id,
        "station_id": item.station_id,
        "station_name": station.name if station else item.station_name,
        "station_color": station.color if station else "",
        "destination": item.destination,
        "printer_usage": item.printer_usage,
        "status": item.status,
        "void_reason": item.void_reason,
        "ready_at": item.ready_at,
    }


def _heading(view: TicketView) -> dict:
    """What a ticket and its row in the list both start with: which ticket it is and where it stands."""
    return {
        "id": view.id,
        "number": view.number,
        "short_number": view.short_number,
        "label": view.label,
        "order_type": view.order_type,
        "priority": view.priority,
        "status": view.status,
        "round_no": view.round_no,
    }


def ticket_out(
    view: TicketView,
    stations: dict[UUID, Station] | None = None,
    print_error: str | None = None,
) -> dict:
    stations = station_map() if stations is None else stations
    return {
        **_heading(view),
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
        **_heading(view),
        "items_count": len(view.live_items),
        "total": view.total,
        "received_at": view.received_at,
        "order_id": view.order_id,
        "saved": view.saved,
    }
