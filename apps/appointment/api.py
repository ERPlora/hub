"""Ninja routes of the appointment app: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``): a record travels in the input (query string on GET, body on POST),
by its id or by its number or name. The platform's reactions (``mark_charged``, ``unmark_charged``,
``customer.reassign``, ``customer.erase``, ``staff.release``) have no route.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.appointment import queries, services
from apps.appointment.schemas import (
    AppointmentCreateIn,
    AppointmentListIn,
    AppointmentRefIn,
    BlockedTimeCreateIn,
    BlockedTimeListIn,
    BlockedTimeRefIn,
    BulkCreateIn,
    BulkDeleteIn,
    CancelIn,
    CheckIn,
    CountForServiceIn,
    ForCustomerIn,
    HistoryIn,
    LanesIn,
    MaterializeIn,
    NoticesIn,
    RecurringCreateIn,
    RecurringGetIn,
    RecurringListIn,
    RecurringRefIn,
    RecurringUpdateIn,
    RescheduleIn,
    SettingsIn,
    SlotsIn,
    UpdateIn,
)

router = Router(tags=["appointment"])


# Appointments: reads


@bind(router, "appointment.appointment.list", "/appointment/appointments")
async def appointment_list(request, params: Query[AppointmentListIn]):
    return await run_operation(request, queries.list_appointments, params)


@bind(router, "appointment.appointment.get", "/appointment/appointments/detail")
async def appointment_get(request, params: Query[AppointmentRefIn]):
    return await run_operation(request, queries.get_appointment, params)


@bind(router, "appointment.appointment.history", "/appointment/appointments/history")
async def appointment_history(request, params: Query[HistoryIn]):
    return await run_operation(request, queries.appointment_history, params)


@bind(
    router,
    "appointment.appointment.list_for_customer",
    "/appointment/appointments/for_customer",
)
async def appointment_for_customer(request, params: Query[ForCustomerIn]):
    return await run_operation(request, queries.list_for_customer, params)


@bind(
    router,
    "appointment.appointment.count_active_for_service",
    "/appointment/appointments/count_for_service",
)
async def appointment_count_for_service(request, params: Query[CountForServiceIn]):
    return await run_operation(request, queries.count_active_for_service, params)


@bind(
    router,
    "appointment.appointment.count_to_confirm",
    "/appointment/appointments/count_to_confirm",
)
async def appointment_count_to_confirm(request):
    return await run_operation(request, queries.count_to_confirm)


@bind(router, "appointment.appointment.notices", "/appointment/appointments/notices")
async def appointment_notices(request, params: Query[NoticesIn]):
    return await run_operation(request, queries.notices, params)


# Appointments: writes


@bind(router, "appointment.appointment.create", "/appointment/appointments", status=201)
async def appointment_create(request, data: AppointmentCreateIn):
    return await run_operation(request, services.create_appointment, data)


@bind(
    router,
    "appointment.appointment.bulk_create",
    "/appointment/appointments/bulk_create",
    status=201,
)
async def appointment_bulk_create(request, data: BulkCreateIn):
    return await run_operation(request, services.bulk_create, data)


@bind(
    router, "appointment.appointment.reschedule", "/appointment/appointments/reschedule"
)
async def appointment_reschedule(request, data: RescheduleIn):
    return await run_operation(request, services.reschedule, data)


@bind(router, "appointment.appointment.update", "/appointment/appointments/update")
async def appointment_update(request, data: UpdateIn):
    return await run_operation(request, services.update_appointment, data)


@bind(router, "appointment.appointment.confirm", "/appointment/appointments/confirm")
async def appointment_confirm(request, data: AppointmentRefIn):
    return await run_operation(request, services.confirm, data)


@bind(router, "appointment.appointment.start", "/appointment/appointments/start")
async def appointment_start(request, data: AppointmentRefIn):
    return await run_operation(request, services.start, data)


@bind(router, "appointment.appointment.complete", "/appointment/appointments/complete")
async def appointment_complete(request, data: AppointmentRefIn):
    return await run_operation(request, services.complete, data)


@bind(
    router,
    "appointment.appointment.mark_no_show",
    "/appointment/appointments/mark_no_show",
)
async def appointment_mark_no_show(request, data: AppointmentRefIn):
    return await run_operation(request, services.mark_no_show, data)


@bind(router, "appointment.appointment.cancel", "/appointment/appointments/cancel")
async def appointment_cancel(request, data: CancelIn):
    return await run_operation(request, services.cancel, data)


@bind(router, "appointment.appointment.delete", "/appointment/appointments/delete")
async def appointment_delete(request, data: AppointmentRefIn):
    return await run_operation(request, services.delete_appointment, data)


@bind(
    router,
    "appointment.appointment.bulk_delete",
    "/appointment/appointments/bulk_delete",
)
async def appointment_bulk_delete(request, data: BulkDeleteIn):
    return await run_operation(request, services.bulk_delete, data)


@bind(router, "appointment.appointment.charge", "/appointment/appointments/charge")
async def appointment_charge(request, data: AppointmentRefIn):
    return await run_operation(request, services.charge, data)


# The agenda and the free times


@bind(router, "appointment.agenda.lanes", "/appointment/lanes")
async def agenda_lanes(request, params: Query[LanesIn]):
    return await run_operation(request, queries.agenda_lanes, params)


@bind(router, "appointment.availability.slots", "/appointment/availability/slots")
async def availability_slots(request, params: Query[SlotsIn]):
    return await run_operation(request, queries.availability_slots, params)


@bind(router, "appointment.availability.check", "/appointment/availability/check")
async def availability_check(request, params: Query[CheckIn]):
    return await run_operation(request, queries.availability_check, params)


# Blocks


@bind(router, "appointment.blocked_time.list", "/appointment/blocked_times")
async def blocked_time_list(request, params: Query[BlockedTimeListIn]):
    return await run_operation(request, queries.list_blocked_times, params)


@bind(
    router, "appointment.blocked_time.create", "/appointment/blocked_times", status=201
)
async def blocked_time_create(request, data: BlockedTimeCreateIn):
    return await run_operation(request, services.create_blocked_time, data)


@bind(router, "appointment.blocked_time.delete", "/appointment/blocked_times/delete")
async def blocked_time_delete(request, data: BlockedTimeRefIn):
    return await run_operation(request, services.delete_blocked_time, data)


# Series


@bind(router, "appointment.recurring.list", "/appointment/recurring")
async def recurring_list(request, params: Query[RecurringListIn]):
    return await run_operation(request, queries.list_series, params)


@bind(router, "appointment.recurring.get", "/appointment/recurring/detail")
async def recurring_get(request, params: Query[RecurringGetIn]):
    return await run_operation(request, queries.get_series, params)


@bind(router, "appointment.recurring.create", "/appointment/recurring", status=201)
async def recurring_create(request, data: RecurringCreateIn):
    return await run_operation(request, services.create_series, data)


@bind(router, "appointment.recurring.materialize", "/appointment/recurring/materialize")
async def recurring_materialize(request, data: MaterializeIn):
    return await run_operation(request, services.materialize, data)


@bind(router, "appointment.recurring.update", "/appointment/recurring/update")
async def recurring_update(request, data: RecurringUpdateIn):
    return await run_operation(request, services.update_series, data)


@bind(router, "appointment.recurring.activate", "/appointment/recurring/activate")
async def recurring_activate(request, data: RecurringRefIn):
    return await run_operation(request, services.activate_series, data)


@bind(router, "appointment.recurring.deactivate", "/appointment/recurring/deactivate")
async def recurring_deactivate(request, data: RecurringRefIn):
    return await run_operation(request, services.deactivate_series, data)


@bind(router, "appointment.recurring.delete", "/appointment/recurring/delete")
async def recurring_delete(request, data: RecurringRefIn):
    return await run_operation(request, services.delete_series, data)


# Settings


@bind(router, "appointment.settings.get", "/appointment/settings")
async def settings_get(request):
    return await run_operation(request, queries.get_settings)


@bind(router, "appointment.settings.update", "/appointment/settings")
async def settings_update(request, data: SettingsIn):
    return await run_operation(request, services.update_settings, data)
