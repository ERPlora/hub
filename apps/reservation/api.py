"""Ninja routes of the reservation app: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``): a record travels in the input (query string on GET, body on POST), by
its id or as a person says it. The reactions to Customers (the platform's own writes) have no route.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.reservation import queries, services
from apps.reservation.schemas import (
    BlockedDateIn,
    BlockedDateListIn,
    BlockedDateRefIn,
    CancelIn,
    DayIn,
    ReservationIn,
    ReservationListIn,
    ReservationPatchIn,
    ReservationRefIn,
    SettingsIn,
    TablesIn,
    TimeSlotIn,
    TimeSlotListIn,
    TimeSlotRefIn,
    WaitlistConvertIn,
    WaitlistIn,
    WaitlistListIn,
    WaitlistPatchIn,
    WaitlistRefIn,
)

router = Router(tags=["reservation"])


# Reservations


@bind(router, "reservation.reservation.list", "/reservation/reservations")
async def reservation_list(request, params: Query[ReservationListIn]):
    return await run_operation(request, queries.list_reservations, params)


@bind(router, "reservation.reservation.get", "/reservation/reservations/detail")
async def reservation_get(request, params: Query[ReservationRefIn]):
    return await run_operation(request, queries.get_reservation, params)


@bind(router, "reservation.reservation.create", "/reservation/reservations", status=201)
async def reservation_create(request, data: ReservationIn):
    return await run_operation(request, services.create_reservation, data)


@bind(router, "reservation.reservation.update", "/reservation/reservations/update")
async def reservation_update(request, data: ReservationPatchIn):
    return await run_operation(request, services.update_reservation, data)


@bind(router, "reservation.reservation.confirm", "/reservation/reservations/confirm")
async def reservation_confirm(request, data: ReservationRefIn):
    return await run_operation(request, services.confirm_reservation, data)


@bind(router, "reservation.reservation.seat", "/reservation/reservations/seat")
async def reservation_seat(request, data: ReservationRefIn):
    return await run_operation(request, services.seat_reservation, data)


@bind(router, "reservation.reservation.complete", "/reservation/reservations/complete")
async def reservation_complete(request, data: ReservationRefIn):
    return await run_operation(request, services.complete_reservation, data)


@bind(router, "reservation.reservation.cancel", "/reservation/reservations/cancel")
async def reservation_cancel(request, data: CancelIn):
    return await run_operation(request, services.cancel_reservation, data)


@bind(router, "reservation.reservation.no_show", "/reservation/reservations/no_show")
async def reservation_no_show(request, data: ReservationRefIn):
    return await run_operation(request, services.no_show_reservation, data)


@bind(router, "reservation.reservation.delete", "/reservation/reservations/delete")
async def reservation_delete(request, data: ReservationRefIn):
    return await run_operation(request, services.delete_reservation, data)


@bind(
    router,
    "reservation.reservation.release_unconfirmed",
    "/reservation/reservations/release_unconfirmed",
)
async def reservation_release_unconfirmed(request):
    return await run_operation(request, services.release_unconfirmed)


# Availability


@bind(router, "reservation.availability.day", "/reservation/availability/day")
async def availability_day(request, params: Query[DayIn]):
    return await run_operation(request, queries.day_availability, params)


@bind(router, "reservation.availability.tables", "/reservation/availability/tables")
async def availability_tables(request, params: Query[TablesIn]):
    return await run_operation(request, queries.free_tables, params)


# Slots


@bind(router, "reservation.time_slot.list", "/reservation/time_slots")
async def time_slot_list(request, params: Query[TimeSlotListIn]):
    return await run_operation(request, queries.list_slots, params)


@bind(router, "reservation.time_slot.create", "/reservation/time_slots", status=201)
async def time_slot_create(request, data: TimeSlotIn):
    return await run_operation(request, services.create_slot, data)


@bind(router, "reservation.time_slot.get", "/reservation/time_slots/detail")
async def time_slot_get(request, params: Query[TimeSlotRefIn]):
    return await run_operation(request, queries.get_slot, params)


@bind(router, "reservation.time_slot.delete", "/reservation/time_slots/delete")
async def time_slot_delete(request, data: TimeSlotRefIn):
    return await run_operation(request, services.delete_slot, data)


# Blocked dates


@bind(router, "reservation.blocked_date.list", "/reservation/blocked_dates")
async def blocked_date_list(request, params: Query[BlockedDateListIn]):
    return await run_operation(request, queries.list_blocked, params)


@bind(
    router, "reservation.blocked_date.create", "/reservation/blocked_dates", status=201
)
async def blocked_date_create(request, data: BlockedDateIn):
    return await run_operation(request, services.create_blocked, data)


@bind(router, "reservation.blocked_date.get", "/reservation/blocked_dates/detail")
async def blocked_date_get(request, params: Query[BlockedDateRefIn]):
    return await run_operation(request, queries.get_blocked, params)


@bind(router, "reservation.blocked_date.delete", "/reservation/blocked_dates/delete")
async def blocked_date_delete(request, data: BlockedDateRefIn):
    return await run_operation(request, services.delete_blocked, data)


# Waitlist


@bind(router, "reservation.waitlist.list", "/reservation/waitlist")
async def waitlist_list(request, params: Query[WaitlistListIn]):
    return await run_operation(request, queries.list_waitlist, params)


@bind(router, "reservation.waitlist.get", "/reservation/waitlist/detail")
async def waitlist_get(request, params: Query[WaitlistRefIn]):
    return await run_operation(request, queries.get_entry, params)


@bind(router, "reservation.waitlist.create", "/reservation/waitlist", status=201)
async def waitlist_create(request, data: WaitlistIn):
    return await run_operation(request, services.create_entry, data)


@bind(router, "reservation.waitlist.update", "/reservation/waitlist/update")
async def waitlist_update(request, data: WaitlistPatchIn):
    return await run_operation(request, services.update_entry, data)


@bind(router, "reservation.waitlist.convert", "/reservation/waitlist/convert")
async def waitlist_convert(request, data: WaitlistConvertIn):
    return await run_operation(request, services.convert_entry, data)


@bind(router, "reservation.waitlist.delete", "/reservation/waitlist/delete")
async def waitlist_delete(request, data: WaitlistRefIn):
    return await run_operation(request, services.delete_entry, data)


# Settings


@bind(router, "reservation.settings.get", "/reservation/settings")
async def settings_get(request):
    return await run_operation(request, queries.get_settings)


@bind(router, "reservation.settings.update", "/reservation/settings")
async def settings_update(request, data: SettingsIn):
    return await run_operation(request, services.update_settings, data)
