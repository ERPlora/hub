"""Ninja routes of the kitchen app: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``): a record travels in the input (query string on GET, body on POST),
by its id or as a person says it. The system's own writes (``receive`` and ``sync``, the reactions to
Sales' events) have no route.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.kitchen import queries, services
from apps.kitchen.schemas import (
    AllDayIn,
    BoardIn,
    ByOrderIn,
    ItemBumpIn,
    ItemRecallIn,
    LogListIn,
    NoIn,
    RoutingClearIn,
    RoutingListIn,
    RoutingSetIn,
    SettingsPatchIn,
    StationIn,
    StationListIn,
    StationPatchIn,
    StationRefIn,
    TicketCancelIn,
    TicketCreateIn,
    TicketListIn,
    TicketRefIn,
    TicketRushIn,
    TicketSendIn,
)

router = Router(tags=["kitchen"])


# The board


@bind(router, "kitchen.ticket.board", "/kitchen/board")
async def ticket_board(request, params: Query[BoardIn]):
    return await run_operation(request, queries.board, params)


@bind(router, "kitchen.ticket.all_day", "/kitchen/all_day")
async def ticket_all_day(request, params: Query[AllDayIn]):
    return await run_operation(request, queries.all_day, params)


# Tickets


@bind(router, "kitchen.ticket.list", "/kitchen/tickets")
async def ticket_list(request, params: Query[TicketListIn]):
    return await run_operation(request, queries.list_tickets, params)


@bind(router, "kitchen.ticket.get", "/kitchen/tickets/detail")
async def ticket_get(request, params: Query[TicketRefIn]):
    return await run_operation(request, queries.get_ticket, params)


@bind(router, "kitchen.ticket.by_order", "/kitchen/tickets/by_order")
async def ticket_by_order(request, params: Query[ByOrderIn]):
    return await run_operation(request, queries.tickets_of_order, params)


@bind(router, "kitchen.ticket.create", "/kitchen/tickets", status=201)
async def ticket_create(request, data: TicketCreateIn):
    return await run_operation(request, services.create_ticket, data)


@bind(router, "kitchen.ticket.send", "/kitchen/tickets/send", status=201)
async def ticket_send(request, data: TicketSendIn):
    return await run_operation(request, services.send, data)


@bind(router, "kitchen.ticket.start", "/kitchen/tickets/start")
async def ticket_start(request, data: TicketRefIn):
    return await run_operation(request, services.start_ticket, data)


@bind(router, "kitchen.ticket.ready", "/kitchen/tickets/ready")
async def ticket_ready(request, data: TicketRefIn):
    return await run_operation(request, services.ready_ticket, data)


@bind(router, "kitchen.ticket.serve", "/kitchen/tickets/serve")
async def ticket_serve(request, data: TicketRefIn):
    return await run_operation(request, services.serve_ticket, data)


@bind(router, "kitchen.ticket.recall", "/kitchen/tickets/recall")
async def ticket_recall(request, data: TicketRefIn):
    return await run_operation(request, services.recall_ticket, data)


@bind(router, "kitchen.ticket.cancel", "/kitchen/tickets/cancel")
async def ticket_cancel(request, data: TicketCancelIn):
    return await run_operation(request, services.cancel_ticket, data)


@bind(router, "kitchen.ticket.delete", "/kitchen/tickets/delete")
async def ticket_delete(request, data: TicketRefIn):
    return await run_operation(request, services.delete_ticket, data)


@bind(router, "kitchen.ticket.set_rush", "/kitchen/tickets/set_rush")
async def ticket_set_rush(request, data: TicketRushIn):
    return await run_operation(request, services.set_rush, data)


@bind(router, "kitchen.ticket.reprint", "/kitchen/tickets/reprint")
async def ticket_reprint(request, data: TicketRefIn):
    return await run_operation(request, services.reprint_ticket, data)


# Dishes


@bind(router, "kitchen.item.bump", "/kitchen/items/bump")
async def item_bump(request, data: ItemBumpIn):
    return await run_operation(request, services.bump_items, data)


@bind(router, "kitchen.item.recall", "/kitchen/items/recall")
async def item_recall(request, data: ItemRecallIn):
    return await run_operation(request, services.recall_items, data)


# Stations and routing


@bind(router, "kitchen.station.list", "/kitchen/stations")
async def station_list(request, params: Query[StationListIn]):
    return await run_operation(request, queries.list_stations, params)


@bind(router, "kitchen.station.create", "/kitchen/stations", status=201)
async def station_create(request, data: StationIn):
    return await run_operation(request, services.create_station, data)


@bind(router, "kitchen.station.update", "/kitchen/stations/update")
async def station_update(request, data: StationPatchIn):
    return await run_operation(request, services.update_station, data)


@bind(router, "kitchen.station.delete", "/kitchen/stations/delete")
async def station_delete(request, data: StationRefIn):
    return await run_operation(request, services.delete_station, data)


@bind(router, "kitchen.routing.list", "/kitchen/routing")
async def routing_list(request, params: Query[RoutingListIn]):
    return await run_operation(request, queries.list_routing, params)


@bind(router, "kitchen.routing.set", "/kitchen/routing")
async def routing_set(request, data: RoutingSetIn):
    return await run_operation(request, services.set_route, data)


@bind(router, "kitchen.routing.clear", "/kitchen/routing/clear")
async def routing_clear(request, data: RoutingClearIn):
    return await run_operation(request, services.clear_route, data)


# Settings and history


@bind(router, "kitchen.settings.get", "/kitchen/settings")
async def settings_get(request, params: Query[NoIn]):
    return await run_operation(request, queries.get_settings, params)


@bind(router, "kitchen.settings.update", "/kitchen/settings")
async def settings_update(request, data: SettingsPatchIn):
    return await run_operation(request, services.update_settings, data)


@bind(router, "kitchen.log.list", "/kitchen/log")
async def log_list(request, params: Query[LogListIn]):
    return await run_operation(request, queries.list_log, params)
