"""Ninja route of an app's help: it calls ``base.help.get`` and holds no logic. ``config/api.py`` mounts it."""

from live.ninja import bind, run_operation
from ninja import Query, Router

from base.queries import app_help
from base.schemas.app_help import AppHelpIn

router = Router(tags=["base"])


@bind(router, "base.help.get", "/help")
async def help_get(request, params: Query[AppHelpIn]):
    return await run_operation(request, app_help.help_get, params)
