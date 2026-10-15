"""Ninja routes of the combo app: each route calls exactly one operation and holds no logic.

No path parameters: ids (or a menu's, a course's or a product's name) travel in the input (query string
on GET, body on POST), because a route takes one parameter, the operation's input. On the query string
of ``resolve`` each pick is a JSON object per ``choices``. The platform's reaction (``drop_product``)
has no route: no person and no API key reaches it.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.combo import queries, services
from apps.combo.schemas import (
    ComboIn,
    ComboListIn,
    ComboPatchIn,
    ComboRefIn,
    ForSaleIn,
    GroupIn,
    GroupPatchIn,
    GroupRefIn,
    GroupReorderIn,
    OptionBulkIn,
    OptionIn,
    OptionPatchIn,
    OptionRefIn,
    OptionReorderIn,
    ResolveIn,
)

router = Router(tags=["combo"])


# Menus


@bind(router, "combo.combo.list", "/combo/combos")
async def combo_list(request, params: Query[ComboListIn]):
    return await run_operation(request, queries.list_combos, params)


@bind(router, "combo.combo.get", "/combo/combos/detail")
async def combo_get(request, params: Query[ComboRefIn]):
    return await run_operation(request, queries.get_combo, params)


@bind(router, "combo.combo.for_sale", "/combo/combos/for_sale")
async def combo_for_sale(request, params: Query[ForSaleIn]):
    return await run_operation(request, queries.list_for_sale, params)


@bind(router, "combo.combo.resolve", "/combo/combos/resolve")
async def combo_resolve(request, params: Query[ResolveIn]):
    return await run_operation(request, queries.resolve, params)


@bind(router, "combo.combo.create", "/combo/combos", status=201)
async def combo_create(request, data: ComboIn):
    return await run_operation(request, services.create_combo, data)


@bind(router, "combo.combo.update", "/combo/combos/update")
async def combo_update(request, data: ComboPatchIn):
    return await run_operation(request, services.update_combo, data)


@bind(router, "combo.combo.delete", "/combo/combos/delete")
async def combo_delete(request, data: ComboRefIn):
    return await run_operation(request, services.delete_combo, data)


# Courses


@bind(router, "combo.group.create", "/combo/groups", status=201)
async def group_create(request, data: GroupIn):
    return await run_operation(request, services.create_group, data)


@bind(router, "combo.group.update", "/combo/groups/update")
async def group_update(request, data: GroupPatchIn):
    return await run_operation(request, services.update_group, data)


@bind(router, "combo.group.delete", "/combo/groups/delete")
async def group_delete(request, data: GroupRefIn):
    return await run_operation(request, services.delete_group, data)


@bind(router, "combo.group.reorder", "/combo/groups/reorder")
async def group_reorder(request, data: GroupReorderIn):
    return await run_operation(request, services.reorder_groups, data)


# Choices


@bind(router, "combo.option.create", "/combo/options", status=201)
async def option_create(request, data: OptionIn):
    return await run_operation(request, services.create_option, data)


@bind(router, "combo.option.bulk_create", "/combo/options/bulk_create", status=201)
async def option_bulk_create(request, data: OptionBulkIn):
    return await run_operation(request, services.bulk_create_options, data)


@bind(router, "combo.option.update", "/combo/options/update")
async def option_update(request, data: OptionPatchIn):
    return await run_operation(request, services.update_option, data)


@bind(router, "combo.option.delete", "/combo/options/delete")
async def option_delete(request, data: OptionRefIn):
    return await run_operation(request, services.delete_option, data)


@bind(router, "combo.option.reorder", "/combo/options/reorder")
async def option_reorder(request, data: OptionReorderIn):
    return await run_operation(request, services.reorder_options, data)
