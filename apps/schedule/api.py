"""Ninja routes of the schedule app: each route calls exactly one operation and holds no logic.

No path parameters: ids (or a special day's name or date) travel in the input (query string on GET,
body on POST), because a route takes one parameter, the operation's input.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.schedule import queries, services
from apps.schedule.schemas import (
    BulkSpecialDayIn,
    HoursRangeIn,
    IsOpenIn,
    OverrideIn,
    OverrideListIn,
    OverridePatchIn,
    OverrideRefIn,
    SetDayIn,
    SettingsIn,
    SpecialDayIn,
    SpecialDayListIn,
    SpecialDayPatchIn,
    SpecialDayRefIn,
)

router = Router(tags=["schedule"])


# The week


@bind(router, "schedule.week.get", "/schedule/week")
async def week_get(request):
    return await run_operation(request, queries.get_week)


@bind(router, "schedule.week.set_day", "/schedule/week/set_day")
async def week_set_day(request, data: SetDayIn):
    return await run_operation(request, services.set_day, data)


@bind(router, "schedule.week.confirm", "/schedule/week/confirm")
async def week_confirm(request):
    return await run_operation(request, services.confirm_week)


# Special days


@bind(router, "schedule.special_day.list", "/schedule/special_days")
async def special_day_list(request, params: Query[SpecialDayListIn]):
    return await run_operation(request, queries.list_special_days, params)


@bind(router, "schedule.special_day.create", "/schedule/special_days", status=201)
async def special_day_create(request, data: SpecialDayIn):
    return await run_operation(request, services.create_special_day, data)


@bind(
    router,
    "schedule.special_day.bulk_create",
    "/schedule/special_days/bulk_create",
    status=201,
)
async def special_day_bulk_create(request, data: BulkSpecialDayIn):
    return await run_operation(request, services.bulk_create_special_days, data)


@bind(router, "schedule.special_day.update", "/schedule/special_days/update")
async def special_day_update(request, data: SpecialDayPatchIn):
    return await run_operation(request, services.update_special_day, data)


@bind(router, "schedule.special_day.delete", "/schedule/special_days/delete")
async def special_day_delete(request, data: SpecialDayRefIn):
    return await run_operation(request, services.delete_special_day, data)


# Temporary changes


@bind(router, "schedule.override.list", "/schedule/overrides")
async def override_list(request, params: Query[OverrideListIn]):
    return await run_operation(request, queries.list_overrides, params)


@bind(router, "schedule.override.create", "/schedule/overrides", status=201)
async def override_create(request, data: OverrideIn):
    return await run_operation(request, services.create_override, data)


@bind(router, "schedule.override.update", "/schedule/overrides/update")
async def override_update(request, data: OverridePatchIn):
    return await run_operation(request, services.update_override, data)


@bind(router, "schedule.override.delete", "/schedule/overrides/delete")
async def override_delete(request, data: OverrideRefIn):
    return await run_operation(request, services.delete_override, data)


# Settings


@bind(router, "schedule.settings.get", "/schedule/settings")
async def settings_get(request):
    return await run_operation(request, queries.get_settings)


@bind(router, "schedule.settings.update", "/schedule/settings")
async def settings_update(request, data: SettingsIn):
    return await run_operation(request, services.update_settings, data)


# Is it open? The hours of a range (the appointment book's)


@bind(router, "schedule.business.is_open", "/schedule/is_open")
async def business_is_open(request, params: Query[IsOpenIn]):
    return await run_operation(request, queries.business_is_open, params)


@bind(router, "schedule.hours.for_range", "/schedule/hours")
async def hours_for_range(request, params: Query[HoursRangeIn]):
    return await run_operation(request, queries.hours_for_range, params)
