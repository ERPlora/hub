"""Ninja routes of the table app: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``): a record travels in the input (query string on GET, body on
POST), by its id or as a person says it. The platform's own writes (``close_by_order``, the holds'
sweep and the reactions to Reservations and Customers) have no route.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.table import queries, services
from apps.table.schemas import (
    ByIdIn,
    ByOrderIn,
    HoldPlaceIn,
    HoldReleaseIn,
    SessionCloseIn,
    SessionGuestsIn,
    SessionLinkOrderIn,
    SessionListIn,
    SessionMergeIn,
    SessionOpenIn,
    SessionRefIn,
    SessionRestoreIn,
    SessionSplitIn,
    SessionTransferIn,
    SettingsIn,
    TableBulkIn,
    TableIn,
    TableListIn,
    TableMoveIn,
    TablePatchIn,
    TableRefIn,
    WaiterListIn,
    ZoneIn,
    ZoneListIn,
    ZonePatchIn,
    ZoneRefIn,
)

router = Router(tags=["table"])


# Zones


@bind(router, "table.zone.list", "/table/zones")
async def zone_list(request, params: Query[ZoneListIn]):
    return await run_operation(request, queries.list_zones, params)


@bind(router, "table.zone.get", "/table/zones/detail")
async def zone_get(request, params: Query[ZoneRefIn]):
    return await run_operation(request, queries.get_zone, params)


@bind(router, "table.zone.create", "/table/zones", status=201)
async def zone_create(request, data: ZoneIn):
    return await run_operation(request, services.create_zone, data)


@bind(router, "table.zone.update", "/table/zones/update")
async def zone_update(request, data: ZonePatchIn):
    return await run_operation(request, services.update_zone, data)


@bind(router, "table.zone.delete", "/table/zones/delete")
async def zone_delete(request, data: ZoneRefIn):
    return await run_operation(request, services.delete_zone, data)


# Tables


@bind(router, "table.table.list", "/table/tables")
async def table_list(request, params: Query[TableListIn]):
    return await run_operation(request, queries.list_tables, params)


@bind(router, "table.table.get", "/table/tables/detail")
async def table_get(request, params: Query[TableRefIn]):
    return await run_operation(request, queries.get_table, params)


@bind(router, "table.table.create", "/table/tables", status=201)
async def table_create(request, data: TableIn):
    return await run_operation(request, services.create_table, data)


@bind(router, "table.table.bulk_create", "/table/tables/bulk_create", status=201)
async def table_bulk_create(request, data: TableBulkIn):
    return await run_operation(request, services.bulk_create_tables, data)


@bind(router, "table.table.update", "/table/tables/update")
async def table_update(request, data: TablePatchIn):
    return await run_operation(request, services.update_table, data)


@bind(router, "table.table.move", "/table/tables/move")
async def table_move(request, data: TableMoveIn):
    return await run_operation(request, services.move_table, data)


@bind(router, "table.table.delete", "/table/tables/delete")
async def table_delete(request, data: TableRefIn):
    return await run_operation(request, services.delete_table, data)


# Table checks


@bind(router, "table.session.list", "/table/sessions")
async def session_list(request, params: Query[SessionListIn]):
    return await run_operation(request, queries.list_sessions, params)


@bind(router, "table.session.get", "/table/sessions/detail")
async def session_get(request, params: Query[SessionRefIn]):
    return await run_operation(request, queries.get_session, params)


@bind(router, "table.session.by_order", "/table/sessions/by_order")
async def session_by_order(request, params: Query[ByOrderIn]):
    return await run_operation(request, queries.sessions_by_order, params)


@bind(router, "table.session.open", "/table/sessions/open", status=201)
async def session_open(request, data: SessionOpenIn):
    return await run_operation(request, services.open_session, data)


@bind(router, "table.session.close", "/table/sessions/close")
async def session_close(request, data: SessionCloseIn):
    return await run_operation(request, services.close_session, data)


@bind(router, "table.session.transfer", "/table/sessions/transfer")
async def session_transfer(request, data: SessionTransferIn):
    return await run_operation(request, services.transfer_session, data)


@bind(router, "table.session.merge", "/table/sessions/merge")
async def session_merge(request, data: SessionMergeIn):
    return await run_operation(request, services.merge_session, data)


@bind(router, "table.session.split", "/table/sessions/split")
async def session_split(request, data: SessionSplitIn):
    return await run_operation(request, services.split_session, data)


@bind(router, "table.session.set_guests", "/table/sessions/set_guests")
async def session_set_guests(request, data: SessionGuestsIn):
    return await run_operation(request, services.set_guests, data)


@bind(router, "table.session.park", "/table/sessions/park")
async def session_park(request, data: SessionRefIn):
    return await run_operation(request, services.park_session, data)


@bind(router, "table.session.restore", "/table/sessions/restore")
async def session_restore(request, data: SessionRestoreIn):
    return await run_operation(request, services.restore_session, data)


@bind(router, "table.session.link_order", "/table/sessions/link_order")
async def session_link_order(request, data: SessionLinkOrderIn):
    return await run_operation(request, services.link_order, data)


@bind(router, "table.session.delete", "/table/sessions/delete")
async def session_delete(request, data: ByIdIn):
    return await run_operation(request, services.delete_session, data)


# Waiters, floor and settings


@bind(router, "table.waiter.list", "/table/waiters")
async def waiter_list(request, params: Query[WaiterListIn]):
    return await run_operation(request, queries.list_waiters, params)


@bind(router, "table.floor.status", "/table/floor/status")
async def floor_status(request):
    return await run_operation(request, queries.floor_status)


@bind(router, "table.settings.get", "/table/settings")
async def settings_get(request):
    return await run_operation(request, queries.get_settings)


@bind(router, "table.settings.update", "/table/settings")
async def settings_update(request, data: SettingsIn):
    return await run_operation(request, services.update_settings, data)


# Holds


@bind(router, "table.hold.place", "/table/holds", status=201)
async def hold_place(request, data: HoldPlaceIn):
    return await run_operation(request, services.place_hold, data)


@bind(router, "table.hold.release", "/table/holds/release")
async def hold_release(request, data: HoldReleaseIn):
    return await run_operation(request, services.release_hold, data)
