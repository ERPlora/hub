"""Ninja routes of the pricing app: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``): an id travels in the input, because a route takes one parameter,
the operation's input. The reactions to other apps' events (``pricing.catalog.*``) have no route: only
the platform runs them.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.pricing import queries, services
from apps.pricing.schemas import (
    PriceItemIn,
    PriceItemListIn,
    PriceItemPatchIn,
    PriceItemRefIn,
    PriceListDefaultIn,
    PriceListIn,
    PriceListListIn,
    PriceListPatchIn,
    PriceListRefIn,
    ResolveIn,
    RuleIn,
    RuleListIn,
    RulePatchIn,
    RuleRefIn,
)

router = Router(tags=["pricing"])


# Price lists


@bind(router, "pricing.price_list.list", "/pricing/price_lists")
async def price_list_list(request, params: Query[PriceListListIn]):
    return await run_operation(request, queries.list_price_lists, params)


@bind(router, "pricing.price_list.get", "/pricing/price_lists/detail")
async def price_list_get(request, params: Query[PriceListRefIn]):
    return await run_operation(request, queries.get_price_list, params)


@bind(router, "pricing.price_list.create", "/pricing/price_lists", status=201)
async def price_list_create(request, data: PriceListIn):
    return await run_operation(request, services.create_price_list, data)


@bind(router, "pricing.price_list.update", "/pricing/price_lists/update")
async def price_list_update(request, data: PriceListPatchIn):
    return await run_operation(request, services.update_price_list, data)


@bind(router, "pricing.price_list.set_default", "/pricing/price_lists/set_default")
async def price_list_set_default(request, data: PriceListDefaultIn):
    return await run_operation(request, services.set_default_price_list, data)


@bind(router, "pricing.price_list.deactivate", "/pricing/price_lists/deactivate")
async def price_list_deactivate(request, data: PriceListRefIn):
    return await run_operation(request, services.deactivate_price_list, data)


@bind(router, "pricing.price_list.activate", "/pricing/price_lists/activate")
async def price_list_activate(request, data: PriceListRefIn):
    return await run_operation(request, services.activate_price_list, data)


# Prices


@bind(router, "pricing.price_item.list", "/pricing/price_items")
async def price_item_list(request, params: Query[PriceItemListIn]):
    return await run_operation(request, queries.list_price_items, params)


@bind(router, "pricing.price_item.add", "/pricing/price_items", status=201)
async def price_item_add(request, data: PriceItemIn):
    return await run_operation(request, services.add_price_item, data)


@bind(router, "pricing.price_item.update", "/pricing/price_items/update")
async def price_item_update(request, data: PriceItemPatchIn):
    return await run_operation(request, services.update_price_item, data)


@bind(router, "pricing.price_item.remove", "/pricing/price_items/remove")
async def price_item_remove(request, data: PriceItemRefIn):
    return await run_operation(request, services.remove_price_item, data)


# Rules


@bind(router, "pricing.rule.list", "/pricing/rules")
async def rule_list(request, params: Query[RuleListIn]):
    return await run_operation(request, queries.list_rules, params)


@bind(router, "pricing.rule.create", "/pricing/rules", status=201)
async def rule_create(request, data: RuleIn):
    return await run_operation(request, services.create_rule, data)


@bind(router, "pricing.rule.update", "/pricing/rules/update")
async def rule_update(request, data: RulePatchIn):
    return await run_operation(request, services.update_rule, data)


@bind(router, "pricing.rule.deactivate", "/pricing/rules/deactivate")
async def rule_deactivate(request, data: RuleRefIn):
    return await run_operation(request, services.deactivate_rule, data)


@bind(router, "pricing.rule.activate", "/pricing/rules/activate")
async def rule_activate(request, data: RuleRefIn):
    return await run_operation(request, services.activate_rule, data)


# The price of a line


@bind(router, "pricing.price.resolve", "/pricing/prices/resolve")
async def price_resolve(request, params: Query[ResolveIn]):
    return await run_operation(request, queries.resolve_price, params)
