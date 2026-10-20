"""Ninja routes of the cash register app: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``): ids travel in the input, because a route takes one parameter, the
operation's input.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.cash_register import queries, services
from apps.cash_register.schemas import (
    CountAddIn,
    CountListIn,
    MovementAddIn,
    MovementListIn,
    RegisterIn,
    RegisterListIn,
    RegisterUpdateIn,
    SessionCloseIn,
    SessionGetIn,
    SessionListIn,
    SessionOpenIn,
    SettingsPatchIn,
)

router = Router(tags=["cash_register"])


# Settings


@bind(router, "cash_register.settings.get", "/cash_register/settings")
async def settings_get(request):
    return await run_operation(request, queries.get_settings)


@bind(router, "cash_register.settings.update", "/cash_register/settings")
async def settings_update(request, data: SettingsPatchIn):
    return await run_operation(request, services.update_settings, data)


# Drawers


@bind(router, "cash_register.register.list", "/cash_register/registers")
async def register_list(request, params: Query[RegisterListIn]):
    return await run_operation(request, queries.list_registers, params)


@bind(router, "cash_register.register.create", "/cash_register/registers", status=201)
async def register_create(request, data: RegisterIn):
    return await run_operation(request, services.create_register, data)


@bind(router, "cash_register.register.update", "/cash_register/registers/update")
async def register_update(request, data: RegisterUpdateIn):
    return await run_operation(request, services.update_register, data)


# Sessions


@bind(router, "cash_register.session.list", "/cash_register/sessions")
async def session_list(request, params: Query[SessionListIn]):
    return await run_operation(request, queries.list_sessions, params)


@bind(router, "cash_register.session.current", "/cash_register/sessions/current")
async def session_current(request):
    return await run_operation(request, queries.current_session)


@bind(router, "cash_register.session.get", "/cash_register/sessions/detail")
async def session_get(request, params: Query[SessionGetIn]):
    return await run_operation(request, queries.get_session, params)


@bind(router, "cash_register.session.open", "/cash_register/sessions/open", status=201)
async def session_open(request, data: SessionOpenIn):
    return await run_operation(request, services.open_session, data)


@bind(router, "cash_register.session.close", "/cash_register/sessions/close")
async def session_close(request, data: SessionCloseIn):
    return await run_operation(request, services.close_session, data)


@bind(router, "cash_register.session.auto_close", "/cash_register/sessions/auto_close")
async def session_auto_close(request):
    return await run_operation(request, services.auto_close)


@bind(router, "cash_register.session.print", "/cash_register/sessions/print")
async def session_print(request, data: SessionGetIn):
    return await run_operation(request, services.print_session, data)


# Movements and counts


@bind(router, "cash_register.movement.list", "/cash_register/movements")
async def movement_list(request, params: Query[MovementListIn]):
    return await run_operation(request, queries.list_movements, params)


@bind(router, "cash_register.movement.add", "/cash_register/movements", status=201)
async def movement_add(request, data: MovementAddIn):
    return await run_operation(request, services.add_movement, data)


@bind(router, "cash_register.count.list", "/cash_register/counts")
async def count_list(request, params: Query[CountListIn]):
    return await run_operation(request, queries.list_counts, params)


@bind(router, "cash_register.count.add", "/cash_register/counts", status=201)
async def count_add(request, data: CountAddIn):
    return await run_operation(request, services.add_count, data)


# Currency


@bind(router, "cash_register.currency.get", "/cash_register/currency")
async def currency_get(request):
    return await run_operation(request, queries.get_currency)
