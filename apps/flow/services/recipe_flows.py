"""The ready-made automations the apps bring (``flow.recipe.*``, FLOW-F33 to F36): turned on, turned off,
restored to the version their app brings today and repaired."""

import datetime as dt

from django.db import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound, PermissionDenied
from live.operations import atomic, operation
from live.outbox import record_event

from apps.flow import events, recipes
from apps.flow.models import Flow
from apps.flow.queries.catalog import grantable_operations
from apps.flow.queries.flows import flow_row
from apps.flow.queries.reads import MANAGE
from apps.flow.queries.recipe_flows import recipe_flow
from apps.flow.schemas.flows import CreateIn, FlowOut
from apps.flow.schemas.recipe_flows import RecipeEnabledOut, RecipeRefIn

from .flow_document import _apply_trigger, _next_fire, refresh_search_text
from .flows import _switch
from .writes import GRANT_BEYOND_CALLER, _actor

RECIPE_NOT_ON = _("This business has not turned that automation on: there is nothing to change.")


def _recipe_grants(ctx: OperationContext, recipe: recipes.Recipe) -> list[str]:
    """The recipe's permissions, which whoever turns it on or restores it must hold themselves (FLOW-F12's
    rule: nobody allows what they may not do)."""
    wanted = recipes.grants(recipe)
    offered = grantable_operations(ctx.scope)  # an offered recipe asks only for what its steps may use (recipes.shelf)
    for name in wanted:
        if not ctx.has(offered[name].permission):
            raise PermissionDenied(str(GRANT_BEYOND_CALLER) % {"name": name})
    return wanted


def _recipe_flow(ref: str) -> Flow:
    flow = recipe_flow(ref, lock=True)
    if flow is None:
        raise NotFound(str(RECIPE_NOT_ON), code="flow.recipe_not_on")
    return flow


def _apply_recipe(ctx: OperationContext, flow: Flow, recipe: recipes.Recipe, now: dt.datetime) -> bool:
    """Writes today's recipe on ``flow`` (its name in ``ctx``'s language, trigger, steps and fingerprint);
    whether its trigger or steps changed."""
    built = recipes.build(recipe, ctx.language)
    parsed = CreateIn.model_validate(built)
    before = (flow.trigger_kind, flow.trigger_event, flow.trigger_filter, flow.schedule, flow.run_at, flow.steps)
    flow.name = parsed.name
    _apply_trigger(flow, parsed.trigger)
    flow.steps = [step.model_dump(mode="json", exclude_none=True) for step in parsed.steps]
    flow.recipe_digest = recipes.digest(recipe)
    flow.next_fire_at = _next_fire(flow, now)
    flow.language = ctx.language
    flow.updated_by = _actor(ctx)
    refresh_search_text(flow)
    return before != (flow.trigger_kind, flow.trigger_event, flow.trigger_filter, flow.schedule, flow.run_at, flow.steps)


@operation(
    "flow.recipe.enable",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE,
    input=RecipeRefIn,
    output=RecipeEnabledOut,
    ai={
        "asks": {
            "en": (
                "turn on the recipe that fills a cancelled slot",
                "activate the ready-made reminder automation",
            ),
            "es": (
                "activa la receta de recordatorio de citas",
                "enciende la receta que avisa cuando alguien cancela",
            ),
        },
        "description": "Turn on a ready-made automation an app brings (`flow.recipe.list`). The first time it is "
        "built and left on with exactly the permissions the recipe asks for; afterwards the one already built is "
        "switched on as the owner left it. Say what it will do and what it may do before turning it on.",
        "risk": "high",
    },
)
def enable_recipe(ctx: OperationContext, data: RecipeRefIn) -> dict:
    recipe = recipes.find(ctx.scope, data.recipe)
    wanted = _recipe_grants(ctx, recipe)
    now = timezone.now()
    flow = recipe_flow(recipe.ref, lock=True)
    if flow is None:
        flow = Flow(recipe=recipe.ref, grants=wanted, enabled=True, created_by=_actor(ctx))
        _apply_recipe(ctx, flow, recipe, now)
        try:
            with atomic():
                flow.save()
        except IntegrityError:
            # Turned on at the same time by someone else: theirs is the one (the unique recipe per business).
            flow = _recipe_flow(recipe.ref)
        else:
            for name in (events.FLOW_CREATED, events.FLOW_GRANTED, events.FLOW_ENABLED):
                record_event(ctx, name, {"id": str(flow.id)})
            return {"created": True, "flow": flow_row(flow)}
    if not flow.grants:
        # Left with no permission at all, it could do nothing: «on» means working, so it gets the recipe's.
        flow.grants = wanted
        flow.updated_by = _actor(ctx)
        flow.save(update_fields=["grants", "updated_by", "updated_at"])
        record_event(ctx, events.FLOW_GRANTED, {"id": str(flow.id)})
    _switch(ctx, flow, True)
    return {"created": False, "flow": flow_row(flow)}


@operation(
    "flow.recipe.disable",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE,
    input=RecipeRefIn,
    output=FlowOut,
    ai={
        "asks": {
            "en": (
                "turn off the appointment reminder recipe",
                "pause the ready-made cancellation recipe",
            ),
            "es": (
                "apaga la receta del recordatorio de citas",
                "desactiva la receta prefabricada de las cancelaciones",
            ),
        },
        "description": "Turn off a ready-made automation an app brings: it is paused, never deleted; its permissions "
        "and its history stay, and turning it on again leaves it as it was.",
        "risk": "high",
    },
)
def disable_recipe(ctx: OperationContext, data: RecipeRefIn) -> dict:
    flow = _recipe_flow(data.recipe)
    _switch(ctx, flow, False)
    return flow_row(flow)


@operation(
    "flow.recipe.restore",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE,
    input=RecipeRefIn,
    output=FlowOut,
    ai={
        "asks": {
            "en": (
                "put the reminder recipe back as its app brings it",
                "restore the original version of the cancellation recipe",
            ),
            "es": (
                "deja la receta del recordatorio como la trae su app",
                "vuelve a la versión original de la receta de cancelaciones",
            ),
        },
        "description": "Give a ready-made automation back the version its app brings today: its name, trigger, steps "
        "and exactly the recipe's permissions replace the owner's changes; it stays on or paused as it is and keeps "
        "its history. What the owner changed is lost.",
        "risk": "high",
    },
)
def restore_recipe(ctx: OperationContext, data: RecipeRefIn) -> dict:
    recipe = recipes.find(ctx.scope, data.recipe)
    wanted = _recipe_grants(ctx, recipe)
    flow = _recipe_flow(recipe.ref)
    if _apply_recipe(ctx, flow, recipe, timezone.now()):
        flow.version += 1
    granted = flow.grants != wanted
    flow.grants = wanted
    flow.save()
    record_event(ctx, events.FLOW_UPDATED, {"id": str(flow.id), "version": flow.version})
    if granted:
        record_event(ctx, events.FLOW_GRANTED, {"id": str(flow.id)})
    return flow_row(flow)


@operation(
    "flow.recipe.repair",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE,
    input=RecipeRefIn,
    output=FlowOut,
    ai={
        "asks": {
            "en": (
                "repair the old reminder recipe",
                "fix the outdated cancellation recipe with its new conditions",
            ),
            "es": (
                "arregla la receta del recordatorio de citas que se quedó vieja",
                "pon al día la receta de cancelaciones con lo que corrigió su app",
            ),
        },
        "description": "Repair a ready-made automation built from an older version that started in more cases than "
        "its app meant: only the conditions of «Only when…» its app added since are added; its name, steps, "
        "permissions and switch stay. Nothing changes when there is nothing to repair.",
        "risk": "normal",
    },
)
def repair_recipe(ctx: OperationContext, data: RecipeRefIn) -> dict:
    recipe = recipes.find(ctx.scope, data.recipe)
    flow = _recipe_flow(recipe.ref)
    missing = recipes.missing_clauses(recipe, flow)
    steps = recipes.fixed_data(flow, flow.steps)
    if missing or steps != flow.steps:
        flow.trigger_filter = {**flow.trigger_filter, **missing}
        flow.steps = steps
        flow.version += 1
        flow.updated_by = _actor(ctx)
        flow.save(update_fields=["trigger_filter", "steps", "version", "updated_by", "updated_at"])
        record_event(ctx, events.FLOW_UPDATED, {"id": str(flow.id), "version": flow.version})
    return flow_row(flow)
