"""Ninja routes of the attendance app: each route calls exactly one operation and holds no logic.

No path parameters: ids (or a person's name) travel in the input (query string on GET, body on POST),
because a route takes one parameter, the operation's input. The scheduled review and the reaction to a
termination are the system's: they have no route.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.attendance import queries, services
from apps.attendance.schemas import (
    BreakIn,
    ClockInIn,
    ClockOutIn,
    CorrectIn,
    CorrectionListIn,
    PersonListIn,
    PersonRefIn,
    PresenceListIn,
    RecordExportIn,
    RecordListIn,
    RecordRefIn,
    SettingsIn,
)

router = Router(tags=["attendance"])


# Working days


@bind(router, "attendance.record.current", "/attendance/current")
async def record_current(request):
    return await run_operation(request, queries.current)


@bind(router, "attendance.record.list", "/attendance/records")
async def record_list(request, params: Query[RecordListIn]):
    return await run_operation(request, queries.list_records, params)


@bind(router, "attendance.record.detail", "/attendance/records/detail")
async def record_detail(request, params: Query[RecordRefIn]):
    return await run_operation(request, queries.record_detail, params)


@bind(router, "attendance.record.export", "/attendance/records/export")
async def record_export(request, params: Query[RecordExportIn]):
    return await run_operation(request, queries.export_records, params)


@bind(router, "attendance.record.correct", "/attendance/records/correct")
async def record_correct(request, data: CorrectIn):
    return await run_operation(request, services.correct_record, data)


# Clocking


@bind(router, "attendance.record.clock_in", "/attendance/clock_in")
async def clock_in(request, data: ClockInIn):
    return await run_operation(request, services.clock_in, data)


@bind(router, "attendance.record.clock_out", "/attendance/clock_out")
async def clock_out(request, data: ClockOutIn):
    return await run_operation(request, services.clock_out, data)


@bind(router, "attendance.break.start", "/attendance/breaks/start")
async def break_start(request, data: BreakIn):
    return await run_operation(request, services.start_break, data)


@bind(router, "attendance.break.end", "/attendance/breaks/end")
async def break_end(request, data: BreakIn):
    return await run_operation(request, services.end_break, data)


# History, who is in, people and settings


@bind(router, "attendance.correction.list", "/attendance/corrections")
async def correction_list(request, params: Query[CorrectionListIn]):
    return await run_operation(request, queries.list_corrections, params)


@bind(router, "attendance.presence.list", "/attendance/presence")
async def presence_list(request, params: Query[PresenceListIn]):
    return await run_operation(request, queries.list_presence, params)


@bind(router, "attendance.presence.count", "/attendance/presence/count")
async def presence_count(request):
    return await run_operation(request, queries.count_presence)


@bind(router, "attendance.person.list", "/attendance/people")
async def person_list(request, params: Query[PersonListIn]):
    return await run_operation(request, queries.list_people, params)


@bind(router, "attendance.person.detail", "/attendance/people/detail")
async def person_detail(request, params: Query[PersonRefIn]):
    return await run_operation(request, queries.person_detail, params)


@bind(router, "attendance.settings.get", "/attendance/settings")
async def settings_get(request):
    return await run_operation(request, queries.get_settings)


@bind(router, "attendance.settings.update", "/attendance/settings")
async def settings_update(request, data: SettingsIn):
    return await run_operation(request, services.update_settings, data)
