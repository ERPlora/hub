"""Routes of the apps: the list, turning one on or off, and the plan's usage."""

from live.ninja import bind, run_operation
from ninja import Query, Router, Status

from base import queries, services
from base.schemas.apps import AppChangeIn, AppRefIn

router = Router()


@bind(router, "base.app.list", "/apps")
async def app_list(request):
    return await run_operation(request, queries.apps.app_list)


# Turning an app on or off, with the plan's limit: the app by its name or its id in the body; which app
# a name names, by ``base.app.get``. While a hub's own database gets the app's tables the same answer
# comes with 202: accepted, the worker finishes it. Both codes are in the OpenAPI, with the same schema.
@bind(router, "base.app.get", "/apps/detail")
async def app_get(request, params: Query[AppRefIn]):
    return await run_operation(request, queries.apps.app_get, params)


def _accepted_while_creating(answer):
    return Status(202, answer) if answer.state == "creating" else answer


@bind(router, "base.app.enable", "/apps/enable", status=(200, 202))
async def app_enable(request, data: AppChangeIn):
    return _accepted_while_creating(await run_operation(request, services.apps.app_enable, data))


@bind(router, "base.app.disable", "/apps/disable")
async def app_disable(request, data: AppChangeIn):
    return await run_operation(request, services.apps.app_disable, data)


@bind(router, "base.app.retry", "/apps/retry", status=(200, 202))
async def app_retry(request, data: AppChangeIn):
    return _accepted_while_creating(await run_operation(request, services.apps.app_retry, data))


@bind(router, "base.plan.usage", "/system/plan")
async def plan_usage(request):
    return await run_operation(request, queries.usage.plan_usage)
