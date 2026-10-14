"""Ninja routes of the tax app: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``): a rule's ``id`` travels in the input, because a route takes one
parameter, the operation's input.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.tax import queries, services
from apps.tax.schemas import (
    AliasIn,
    AliasListIn,
    AliasResolveIn,
    CalculateIn,
    CategoryGetIn,
    CategoryIn,
    CategoryListIn,
    RuleBulkIn,
    RuleCountriesIn,
    RuleEndIn,
    RuleIn,
    RuleListIn,
    RuleParentIn,
    RuleRefIn,
    RuleStatusIn,
)

router = Router(tags=["tax"])


# Categories


@bind(router, "tax.category.list", "/tax/categories")
async def category_list(request, params: Query[CategoryListIn]):
    return await run_operation(request, queries.list_categories, params)


@bind(router, "tax.category.get", "/tax/categories/detail")
async def category_get(request, params: Query[CategoryGetIn]):
    return await run_operation(request, queries.get_category, params)


@bind(router, "tax.category.create", "/tax/categories", status=201)
async def category_create(request, data: CategoryIn):
    return await run_operation(request, services.create_category, data)


# Rules


@bind(router, "tax.rule.list", "/tax/rules")
async def rule_list(request, params: Query[RuleListIn]):
    return await run_operation(request, queries.list_rules, params)


@bind(router, "tax.rule.status", "/tax/rules/status")
async def rule_status(request, params: Query[RuleStatusIn]):
    return await run_operation(request, queries.rule_status, params)


@bind(router, "tax.rule.parent_candidates", "/tax/rules/parent_candidates")
async def rule_parent_candidates(request, params: Query[RuleParentIn]):
    return await run_operation(request, queries.list_parent_candidates, params)


@bind(router, "tax.rule.countries", "/tax/rules/countries")
async def rule_countries(request, params: Query[RuleCountriesIn]):
    return await run_operation(request, queries.rule_countries, params)


@bind(router, "tax.rule.create", "/tax/rules", status=201)
async def rule_create(request, data: RuleIn):
    return await run_operation(request, services.create_rule, data)


@bind(router, "tax.rule.bulk_create", "/tax/rules/bulk_create", status=201)
async def rule_bulk_create(request, data: RuleBulkIn):
    return await run_operation(request, services.bulk_create_rules, data)


@bind(router, "tax.rule.end", "/tax/rules/end")
async def rule_end(request, data: RuleEndIn):
    return await run_operation(request, services.end_rule, data)


@bind(router, "tax.rule.deactivate", "/tax/rules/deactivate")
async def rule_deactivate(request, data: RuleRefIn):
    return await run_operation(request, services.deactivate_rule, data)


@bind(router, "tax.rule.activate", "/tax/rules/activate")
async def rule_activate(request, data: RuleRefIn):
    return await run_operation(request, services.activate_rule, data)


# Aliases


@bind(router, "tax.alias.list", "/tax/aliases")
async def alias_list(request, params: Query[AliasListIn]):
    return await run_operation(request, queries.list_aliases, params)


@bind(router, "tax.alias.resolve", "/tax/aliases/resolve")
async def alias_resolve(request, params: Query[AliasResolveIn]):
    return await run_operation(request, queries.resolve_alias, params)


@bind(router, "tax.alias.create", "/tax/aliases", status=201)
async def alias_create(request, data: AliasIn):
    return await run_operation(request, services.create_alias, data)


# The calculation


@bind(router, "tax.rate.calculate", "/tax/rates/calculate")
async def rate_calculate(request, params: Query[CalculateIn]):
    return await run_operation(request, queries.calculate, params)
