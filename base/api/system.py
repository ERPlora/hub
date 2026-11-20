"""Routes of System: the apps' cards, the status, the events and the failed events."""

from live.ninja import bind, run_operation
from ninja import Query, Router

from base import queries, services
from base.schemas.failed_events import FailedEventDiscardIn, FailedEventIn, FailedEventListIn

router = Router()


@bind(router, "base.system.cards", "/system/cards")
async def system_cards(request):
    return await run_operation(request, queries.home.system_cards)


@bind(router, "base.system.status", "/system/status")
async def system_status(request):
    return await run_operation(request, queries.system.system_status)


@bind(router, "base.event.list", "/system/events")
async def event_list(request):
    return await run_operation(request, queries.system.event_list)


@bind(router, "base.failed_event.list", "/system/failed-events")
async def failed_event_list(request, params: Query[FailedEventListIn]):
    return await run_operation(request, queries.system.failed_event_list, params)


@bind(router, "base.failed_event.detail", "/system/failed-events/detail")
async def failed_event_detail(request, data: Query[FailedEventIn]):
    return await run_operation(request, queries.system.failed_event_detail, data)


@bind(router, "base.failed_event.retry", "/system/failed-events/retry")
async def failed_event_retry(request, data: FailedEventIn):
    return await run_operation(request, services.failed_events.failed_event_retry, data)


@bind(router, "base.failed_event.retry_all", "/system/failed-events/retry_all")
async def failed_event_retry_all(request):
    return await run_operation(request, services.failed_events.failed_event_retry_all)


@bind(router, "base.failed_event.discard", "/system/failed-events/discard")
async def failed_event_discard(request, data: FailedEventDiscardIn):
    return await run_operation(request, services.failed_events.failed_event_discard, data)
