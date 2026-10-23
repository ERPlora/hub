"""Ninja routes of the staff app: each route calls exactly one operation and holds no logic.

No path parameters: ids (or a staff member's name) travel in the input (query string on GET, body on
POST), because a route takes one parameter, the operation's input.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.staff import queries, services
from apps.staff.schemas import (
    AccountListIn,
    AvailabilityIn,
    BulkCreateIn,
    ByIdIn,
    CommissionReportIn,
    CommissionSummaryIn,
    CompensationListIn,
    MemberIn,
    MemberListIn,
    MemberPatchIn,
    MemberRefIn,
    MyTimeOffIn,
    RoleIn,
    RoleListIn,
    RolePatchIn,
    ScheduleIn,
    ScheduleListIn,
    ScheduleUpdateIn,
    SetActiveIn,
    SettingsIn,
    TerminateIn,
    TimeOffIn,
    TimeOffListIn,
    TimeOffRequestIn,
    TodayIn,
)

router = Router(tags=["staff"])


# Members


@bind(router, "staff.member.list", "/staff/members")
async def member_list(request, params: Query[MemberListIn]):
    return await run_operation(request, queries.list_members, params)


@bind(router, "staff.member.detail", "/staff/members/detail")
async def member_detail(request, params: Query[MemberRefIn]):
    return await run_operation(request, queries.member_detail, params)


@bind(router, "staff.member.mine", "/staff/members/mine")
async def member_mine(request):
    return await run_operation(request, queries.my_record)


@bind(router, "staff.member.current", "/staff/members/current")
async def member_current(request):
    return await run_operation(request, queries.current_record)


@bind(router, "staff.member.compensation", "/staff/members/compensation")
async def member_compensation(request, params: Query[CompensationListIn]):
    return await run_operation(request, queries.compensation, params)


@bind(router, "staff.member.stats", "/staff/members/stats")
async def member_stats(request):
    return await run_operation(request, queries.member_stats)


@bind(router, "staff.member.create", "/staff/members", status=201)
async def member_create(request, data: MemberIn):
    return await run_operation(request, services.create_member, data)


@bind(router, "staff.member.bulk_create", "/staff/members/bulk_create", status=201)
async def member_bulk_create(request, data: BulkCreateIn):
    return await run_operation(request, services.bulk_create_members, data)


@bind(router, "staff.member.update", "/staff/members/update")
async def member_update(request, data: MemberPatchIn):
    return await run_operation(request, services.update_member, data)


@bind(router, "staff.member.deactivate", "/staff/members/deactivate")
async def member_deactivate(request, data: MemberRefIn):
    return await run_operation(request, services.deactivate_member, data)


@bind(router, "staff.member.terminate", "/staff/members/terminate")
async def member_terminate(request, data: TerminateIn):
    return await run_operation(request, services.terminate_member, data)


@bind(router, "staff.commission.summary", "/staff/commissions")
async def commission_summary(request, params: Query[CommissionSummaryIn]):
    return await run_operation(request, queries.commission_summary, params)


@bind(router, "staff.commission.report", "/staff/commissions/report")
async def commission_report(request, params: Query[CommissionReportIn]):
    return await run_operation(request, queries.commission_report, params)


# Accounts (the «Hub user» selector)


@bind(router, "staff.account.list", "/staff/accounts")
async def account_list(request, params: Query[AccountListIn]):
    return await run_operation(request, queries.list_accounts, params)


# Roles


@bind(router, "staff.role.list", "/staff/roles")
async def role_list(request, params: Query[RoleListIn]):
    return await run_operation(request, queries.list_roles, params)


@bind(router, "staff.role.create", "/staff/roles", status=201)
async def role_create(request, data: RoleIn):
    return await run_operation(request, services.create_role, data)


@bind(router, "staff.role.update", "/staff/roles/update")
async def role_update(request, data: RolePatchIn):
    return await run_operation(request, services.update_role, data)


# Schedules and availability


@bind(router, "staff.schedule.list", "/staff/schedules")
async def schedule_list(request, params: Query[ScheduleListIn]):
    return await run_operation(request, queries.list_schedules, params)


@bind(router, "staff.schedule.detail", "/staff/schedules/detail")
async def schedule_detail(request, params: Query[ByIdIn]):
    return await run_operation(request, queries.schedule_detail, params)


@bind(router, "staff.schedule.create", "/staff/schedules", status=201)
async def schedule_create(request, data: ScheduleIn):
    return await run_operation(request, services.create_schedule, data)


@bind(router, "staff.schedule.update", "/staff/schedules/update")
async def schedule_update(request, data: ScheduleUpdateIn):
    return await run_operation(request, services.update_schedule, data)


@bind(router, "staff.schedule.set_active", "/staff/schedules/set_active")
async def schedule_set_active(request, data: SetActiveIn):
    return await run_operation(request, services.set_schedule_active, data)


@bind(router, "staff.schedule.delete", "/staff/schedules/delete")
async def schedule_delete(request, data: ByIdIn):
    return await run_operation(request, services.delete_schedule, data)


@bind(router, "staff.availability.for_member", "/staff/availability")
async def availability(request, params: Query[AvailabilityIn]):
    return await run_operation(request, queries.member_availability, params)


# Time off


@bind(router, "staff.time_off.list", "/staff/time_off")
async def time_off_list(request, params: Query[TimeOffListIn]):
    return await run_operation(request, queries.list_time_off, params)


@bind(router, "staff.time_off.detail", "/staff/time_off/detail")
async def time_off_detail(request, params: Query[ByIdIn]):
    return await run_operation(request, queries.time_off_detail, params)


@bind(router, "staff.time_off.today", "/staff/time_off/today")
async def time_off_today(request, params: Query[TodayIn]):
    return await run_operation(request, queries.away_today, params)


@bind(router, "staff.time_off.mine", "/staff/time_off/mine")
async def time_off_mine(request, params: Query[MyTimeOffIn]):
    return await run_operation(request, queries.my_time_off, params)


@bind(router, "staff.time_off.create", "/staff/time_off", status=201)
async def time_off_create(request, data: TimeOffIn):
    return await run_operation(request, services.create_time_off, data)


@bind(router, "staff.time_off.request", "/staff/time_off/request", status=201)
async def time_off_request(request, data: TimeOffRequestIn):
    return await run_operation(request, services.request_time_off, data)


@bind(router, "staff.time_off.approve", "/staff/time_off/approve")
async def time_off_approve(request, data: ByIdIn):
    return await run_operation(request, services.approve_time_off, data)


@bind(router, "staff.time_off.reject", "/staff/time_off/reject")
async def time_off_reject(request, data: ByIdIn):
    return await run_operation(request, services.reject_time_off, data)


@bind(router, "staff.time_off.cancel", "/staff/time_off/cancel")
async def time_off_cancel(request, data: ByIdIn):
    return await run_operation(request, services.cancel_time_off, data)


# Settings


@bind(router, "staff.settings.get", "/staff/settings")
async def settings_get(request):
    return await run_operation(request, queries.get_settings)


@bind(router, "staff.settings.update", "/staff/settings")
async def settings_update(request, data: SettingsIn):
    return await run_operation(request, services.update_settings, data)
