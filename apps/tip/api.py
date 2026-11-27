"""Ninja routes of the tips app: each route calls exactly one operation and holds no logic. The tip travels in the input
(query string on GET, body on POST), never in the path. The reactions to Sales' events have no route."""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.tip import queries
from apps.tip.schemas import (
    ReportIn,
    SettingsPatchIn,
    SuggestionIn,
    TipAddIn,
    TipListIn,
    TipPatchIn,
    TipRefIn,
    TipVoidIn,
)
from apps.tip.services import settings, tips

router = Router(tags=["tip"])


@bind(router, "tip.settings.get", "/tip/settings")
async def settings_get(request):
    return await run_operation(request, queries.get_settings)


@bind(router, "tip.settings.update", "/tip/settings")
async def settings_update(request, data: SettingsPatchIn):
    return await run_operation(request, settings.update_settings, data)


@bind(router, "tip.suggestion.get", "/tip/suggestions")
async def suggestion_get(request, params: Query[SuggestionIn]):
    return await run_operation(request, queries.get_suggestions, params)


@bind(router, "tip.tip.list", "/tip/tips")
async def tip_list(request, params: Query[TipListIn]):
    return await run_operation(request, queries.list_tips, params)


@bind(router, "tip.tip.get", "/tip/tips/detail")
async def tip_get(request, params: Query[TipRefIn]):
    return await run_operation(request, queries.get_tip, params)


@bind(router, "tip.tip.add", "/tip/tips", status=201)
async def tip_add(request, data: TipAddIn):
    return await run_operation(request, tips.add_tip, data)


@bind(router, "tip.tip.update", "/tip/tips/update")
async def tip_update(request, data: TipPatchIn):
    return await run_operation(request, tips.update_tip, data)


@bind(router, "tip.tip.void", "/tip/tips/void")
async def tip_void(request, data: TipVoidIn):
    return await run_operation(request, tips.void_tip, data)


@bind(router, "tip.report.get", "/tip/report")
async def report_get(request, params: Query[ReportIn]):
    return await run_operation(request, queries.get_report, params)


@bind(router, "tip.report.mine", "/tip/report/mine")
async def report_mine(request):
    return await run_operation(request, queries.my_tips)
