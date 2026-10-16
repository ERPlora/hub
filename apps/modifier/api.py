"""Ninja routes of the modifier app: each route calls exactly one operation and holds no logic.

No path parameters: a group, an option or a link travels in the input (query string on GET, body on
POST), by its id or as a person names it, because a route takes one parameter, the operation's input.
The reactions to Inventory's events (``modifier.link.drop_product``/``drop_category``) have no route:
only the platform runs them.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.modifier import queries, services
from apps.modifier.schemas import (
    GroupIn,
    GroupListIn,
    GroupPatchIn,
    GroupRefIn,
    LinkIn,
    LinkListIn,
    LinkRefIn,
    OptionIn,
    OptionListIn,
    OptionPatchIn,
    OptionRefIn,
    ResolveIn,
    TargetIn,
)

router = Router(tags=["modifier"])


# Groups


@bind(router, "modifier.group.list", "/modifier/groups")
async def group_list(request, params: Query[GroupListIn]):
    return await run_operation(request, queries.list_groups, params)


@bind(router, "modifier.group.get", "/modifier/groups/detail")
async def group_detail(request, params: Query[GroupRefIn]):
    return await run_operation(request, queries.get_group, params)


@bind(router, "modifier.group.for_target", "/modifier/groups/for_target")
async def group_for_target(request, params: Query[TargetIn]):
    return await run_operation(request, queries.for_target, params)


@bind(router, "modifier.group.create", "/modifier/groups", status=201)
async def group_create(request, data: GroupIn):
    return await run_operation(request, services.create_group, data)


@bind(router, "modifier.group.update", "/modifier/groups/update")
async def group_update(request, data: GroupPatchIn):
    return await run_operation(request, services.update_group, data)


@bind(router, "modifier.group.delete", "/modifier/groups/delete")
async def group_delete(request, data: GroupRefIn):
    return await run_operation(request, services.delete_group, data)


# Options


@bind(router, "modifier.option.list", "/modifier/options")
async def option_list(request, params: Query[OptionListIn]):
    return await run_operation(request, queries.list_options, params)


@bind(router, "modifier.option.create", "/modifier/options", status=201)
async def option_create(request, data: OptionIn):
    return await run_operation(request, services.create_option, data)


@bind(router, "modifier.option.update", "/modifier/options/update")
async def option_update(request, data: OptionPatchIn):
    return await run_operation(request, services.update_option, data)


@bind(router, "modifier.option.delete", "/modifier/options/delete")
async def option_delete(request, data: OptionRefIn):
    return await run_operation(request, services.delete_option, data)


# Links


@bind(router, "modifier.link.list", "/modifier/links")
async def link_list(request, params: Query[LinkListIn]):
    return await run_operation(request, queries.list_links, params)


@bind(router, "modifier.link.attach", "/modifier/links/attach", status=201)
async def link_attach(request, data: LinkIn):
    return await run_operation(request, services.attach_link, data)


@bind(router, "modifier.link.detach", "/modifier/links/detach")
async def link_detach(request, data: LinkRefIn):
    return await run_operation(request, services.detach_link, data)


# The till's valuation of what was chosen


@bind(router, "modifier.selection.resolve", "/modifier/selections/resolve")
async def selection_resolve(request, params: Query[ResolveIn]):
    return await run_operation(request, queries.resolve_selection, params)
