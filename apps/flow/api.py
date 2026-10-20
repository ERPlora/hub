"""Ninja routes of the flow app: each route calls exactly one operation and holds no logic.

No path parameters: an automation's id (or its name) travels in the input (query string on GET, body on
POST). «Try it» takes the automation as JSON text (``document``), since a GET carries no nested object.
The engine (``flow.run.react`` and the two scheduled tasks) has no route: no person and no API key
reaches it.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.flow import queries, services
from apps.flow.schemas import (
    CreateIn,
    DraftListIn,
    DraftProposeIn,
    DraftRefIn,
    EnabledIn,
    FlowListIn,
    FlowRefIn,
    GrantIn,
    RunIn,
    RunListIn,
    RunRefIn,
    SampleIn,
    SecretRefIn,
    SecretSetIn,
    StatusIn,
    TestIn,
    UpdateIn,
)

router = Router(tags=["flow"])


# Automations


@bind(router, "flow.flow.list", "/flow/flows")
async def flow_list(request, params: Query[FlowListIn]):
    return await run_operation(request, queries.list_flows, params)


@bind(router, "flow.flow.detail", "/flow/flows/detail")
async def flow_detail(request, params: Query[FlowRefIn]):
    return await run_operation(request, queries.flow_detail, params)


@bind(router, "flow.flow.status", "/flow/flows/status")
async def flow_status(request, params: Query[StatusIn]):
    return await run_operation(request, queries.flow_status, params)


@bind(router, "flow.flow.test", "/flow/flows/test")
async def flow_test(request, params: Query[TestIn]):
    return await run_operation(request, queries.try_flow, params)


@bind(router, "flow.flow.create", "/flow/flows", status=201)
async def flow_create(request, data: CreateIn):
    return await run_operation(request, services.create_flow, data)


@bind(router, "flow.flow.update", "/flow/flows/update")
async def flow_update(request, data: UpdateIn):
    return await run_operation(request, services.update_flow, data)


@bind(router, "flow.flow.set_enabled", "/flow/flows/set_enabled")
async def flow_set_enabled(request, data: EnabledIn):
    return await run_operation(request, services.set_enabled, data)


@bind(router, "flow.flow.duplicate", "/flow/flows/duplicate", status=201)
async def flow_duplicate(request, data: FlowRefIn):
    return await run_operation(request, services.duplicate_flow, data)


@bind(router, "flow.flow.delete", "/flow/flows/delete")
async def flow_delete(request, data: FlowRefIn):
    return await run_operation(request, services.delete_flow, data)


@bind(router, "flow.flow.grant", "/flow/flows/grant")
async def flow_grant(request, data: GrantIn):
    return await run_operation(request, services.grant, data)


@bind(router, "flow.flow.run", "/flow/flows/run")
async def flow_run(request, data: RunIn):
    return await run_operation(request, services.run_now, data)


# Runs and drafts


@bind(router, "flow.run.list", "/flow/runs")
async def run_list(request, params: Query[RunListIn]):
    return await run_operation(request, queries.list_runs, params)


@bind(router, "flow.run.retry", "/flow/runs/retry")
async def run_retry(request, data: RunRefIn):
    return await run_operation(request, services.retry_run, data)


@bind(router, "flow.draft.list", "/flow/drafts")
async def draft_list(request, params: Query[DraftListIn]):
    return await run_operation(request, queries.list_drafts, params)


@bind(router, "flow.draft.propose", "/flow/drafts", status=201)
async def draft_propose(request, data: DraftProposeIn):
    return await run_operation(request, services.propose_draft, data)


@bind(router, "flow.draft.dismiss", "/flow/drafts/dismiss")
async def draft_dismiss(request, data: DraftRefIn):
    return await run_operation(request, services.dismiss_draft, data)


# What the editor offers


@bind(router, "flow.catalog.read", "/flow/catalog")
async def catalog_read(request):
    return await run_operation(request, queries.read_catalog)


@bind(router, "flow.event.sample", "/flow/events/sample")
async def event_sample(request, params: Query[SampleIn]):
    return await run_operation(request, queries.event_sample, params)


# Secrets (FLOW-F26): names only; a value goes in and never comes out.


@bind(router, "flow.secret.list", "/flow/secrets")
async def secret_list(request):
    return await run_operation(request, queries.list_secrets)


@bind(router, "flow.secret.set", "/flow/secrets")
async def secret_set(request, data: SecretSetIn):
    return await run_operation(request, services.set_secret, data)


@bind(router, "flow.secret.delete", "/flow/secrets/delete")
async def secret_delete(request, data: SecretRefIn):
    return await run_operation(request, services.delete_secret, data)
