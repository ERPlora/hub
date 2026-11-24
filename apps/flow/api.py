"""Ninja routes of the flow app: each route calls exactly one operation and holds no logic.

No path parameters: an automation's id (or its name) travels in the input (query string on GET, body on
POST). «Try it» takes the automation as JSON text (``document``), since a GET carries no nested object.
The engine (``flow.run.react`` and the two scheduled tasks) has no route: no person and no API key
reaches it.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.flow import queries, services
from apps.flow.schemas.catalog import CatalogIn
from apps.flow.schemas.drafts import DraftListIn, DraftProposeIn, DraftRefIn
from apps.flow.schemas.dry_run import SampleIn, TestIn
from apps.flow.schemas.flows import CreateIn, EnabledIn, FlowListIn, FlowRefIn, GrantIn, StatusIn, UpdateIn
from apps.flow.schemas.questions import AnswerIn, QuestionRefIn
from apps.flow.schemas.recipe_flows import RecipeRefIn
from apps.flow.schemas.runs import RunIn, RunListIn, RunRefIn
from apps.flow.schemas.stored_secrets import SecretRefIn, SecretSetIn

router = Router(tags=["flow"])


# Automations


@bind(router, "flow.flow.list", "/flow/flows")
async def flow_list(request, params: Query[FlowListIn]):
    return await run_operation(request, queries.flows.list_flows, params)


@bind(router, "flow.flow.detail", "/flow/flows/detail")
async def flow_detail(request, params: Query[FlowRefIn]):
    return await run_operation(request, queries.flows.flow_detail, params)


@bind(router, "flow.flow.status", "/flow/flows/status")
async def flow_status(request, params: Query[StatusIn]):
    return await run_operation(request, queries.flows.flow_status, params)


@bind(router, "flow.flow.test", "/flow/flows/test")
async def flow_test(request, params: Query[TestIn]):
    return await run_operation(request, queries.dry_run.try_flow, params)


@bind(router, "flow.flow.create", "/flow/flows", status=201)
async def flow_create(request, data: CreateIn):
    return await run_operation(request, services.flows.create_flow, data)


@bind(router, "flow.flow.update", "/flow/flows/update")
async def flow_update(request, data: UpdateIn):
    return await run_operation(request, services.flows.update_flow, data)


@bind(router, "flow.flow.set_enabled", "/flow/flows/set_enabled")
async def flow_set_enabled(request, data: EnabledIn):
    return await run_operation(request, services.flows.set_enabled, data)


@bind(router, "flow.flow.duplicate", "/flow/flows/duplicate", status=201)
async def flow_duplicate(request, data: FlowRefIn):
    return await run_operation(request, services.flows.duplicate_flow, data)


@bind(router, "flow.flow.delete", "/flow/flows/delete")
async def flow_delete(request, data: FlowRefIn):
    return await run_operation(request, services.flows.delete_flow, data)


@bind(router, "flow.flow.grant", "/flow/flows/grant")
async def flow_grant(request, data: GrantIn):
    return await run_operation(request, services.flows.grant, data)


@bind(router, "flow.flow.run", "/flow/flows/run")
async def flow_run(request, data: RunIn):
    return await run_operation(request, services.runs.run_now, data)


# Runs and drafts


@bind(router, "flow.run.list", "/flow/runs")
async def run_list(request, params: Query[RunListIn]):
    return await run_operation(request, queries.runs.list_runs, params)


@bind(router, "flow.run.get", "/flow/runs/detail")
async def run_get(request, params: Query[RunRefIn]):
    return await run_operation(request, queries.runs.get_run, params)


@bind(router, "flow.run.retry", "/flow/runs/retry")
async def run_retry(request, data: RunRefIn):
    return await run_operation(request, services.runs.retry_run, data)


@bind(router, "flow.draft.list", "/flow/drafts")
async def draft_list(request, params: Query[DraftListIn]):
    return await run_operation(request, queries.drafts.list_drafts, params)


@bind(router, "flow.draft.get", "/flow/drafts/detail")
async def draft_get(request, params: Query[DraftRefIn]):
    return await run_operation(request, queries.drafts.get_draft, params)


@bind(router, "flow.draft.propose", "/flow/drafts", status=201)
async def draft_propose(request, data: DraftProposeIn):
    return await run_operation(request, services.drafts.propose_draft, data)


@bind(router, "flow.draft.dismiss", "/flow/drafts/dismiss")
async def draft_dismiss(request, data: DraftRefIn):
    return await run_operation(request, services.drafts.dismiss_draft, data)


# What the editor offers


@bind(router, "flow.catalog.read", "/flow/catalog")
async def catalog_read(request, params: Query[CatalogIn]):
    return await run_operation(request, queries.catalog.read_catalog, params)


@bind(router, "flow.event.sample", "/flow/events/sample")
async def event_sample(request, params: Query[SampleIn]):
    return await run_operation(request, queries.dry_run.event_sample, params)


# Secrets (FLOW-F26): names only; a value goes in and never comes out.


@bind(router, "flow.secret.list", "/flow/secrets")
async def secret_list(request):
    return await run_operation(request, queries.stored_secrets.list_secrets)


@bind(router, "flow.secret.set", "/flow/secrets")
async def secret_set(request, data: SecretSetIn):
    return await run_operation(request, services.stored_secrets.set_secret, data)


@bind(router, "flow.secret.delete", "/flow/secrets/delete")
async def secret_delete(request, data: SecretRefIn):
    return await run_operation(request, services.stored_secrets.delete_secret, data)


# «Waiting for your answer» (FLOW-F29)


@bind(router, "flow.question.list", "/flow/questions")
async def question_list(request):
    return await run_operation(request, queries.questions.list_questions)


@bind(router, "flow.question.get", "/flow/questions/detail")
async def question_get(request, params: Query[QuestionRefIn]):
    return await run_operation(request, queries.questions.get_question, params)


@bind(router, "flow.question.answer", "/flow/questions/answer")
async def question_answer(request, data: AnswerIn):
    return await run_operation(request, services.questions.answer_question, data)


# The ready-made automations the apps bring (FLOW-F33 to F36)


@bind(router, "flow.recipe.list", "/flow/recipes")
async def recipe_list(request):
    return await run_operation(request, queries.recipe_flows.list_recipes)


@bind(router, "flow.recipe.enable", "/flow/recipes/enable")
async def recipe_enable(request, data: RecipeRefIn):
    return await run_operation(request, services.recipe_flows.enable_recipe, data)


@bind(router, "flow.recipe.disable", "/flow/recipes/disable")
async def recipe_disable(request, data: RecipeRefIn):
    return await run_operation(request, services.recipe_flows.disable_recipe, data)


@bind(router, "flow.recipe.restore", "/flow/recipes/restore")
async def recipe_restore(request, data: RecipeRefIn):
    return await run_operation(request, services.recipe_flows.restore_recipe, data)


@bind(router, "flow.recipe.repair", "/flow/recipes/repair")
async def recipe_repair(request, data: RecipeRefIn):
    return await run_operation(request, services.recipe_flows.repair_recipe, data)
