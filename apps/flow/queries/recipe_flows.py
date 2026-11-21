"""The ready-made automations the apps bring (``flow.recipe.list``, FLOW-F33 to F36), and the one this
business built from each."""

from django.utils import translation
from live.context import OperationContext
from live.operations import operation

from apps.flow import document, recipes
from apps.flow.models import Flow
from apps.flow.schemas.recipe_flows import RecipeListIn, RecipeListOut

from .flows import live_flows
from .reads import VIEW


def recipe_flow(ref: str, *, lock: bool = False) -> Flow | None:
    """The automation (not deleted) this business built from the recipe ``ref``, if any."""
    found = live_flows().filter(recipe=ref)
    return (found.select_for_update() if lock else found).first()


@operation(
    "flow.recipe.list",
    kind="query",
    permission=VIEW,
    input=RecipeListIn,
    output=RecipeListOut,
    ai={
        "asks": {
            "en": (
                "which ready-made automations can I turn on?",
                "show me the recipes the apps bring",
            ),
            "es": (
                "¿qué recetas de automatización traen mis apps?",
                "enséñame las automatizaciones listas para usar",
            ),
        },
        "description": "The ready-made automations the active apps bring («fill the gap when a customer cancels»), "
        "with what each one does, the permissions it asks for and why, and, when it was turned on here, its "
        "automation, whether it is on, whether its app brings a newer version and what a repair would add; "
        "and the ones this business cannot use, with why."
    },
)
def list_recipes(ctx: OperationContext, data: RecipeListIn) -> dict:
    offered, set_aside = recipes.shelf(ctx.scope)
    mine = {flow.recipe: flow for flow in live_flows().exclude(recipe="")}
    rows = []
    with translation.override(ctx.language):
        for recipe in offered:
            built = recipes.build(recipe, ctx.language)
            reasons = recipes.reasons(recipe, ctx.language)
            flow = mine.get(recipe.ref)
            required = document.required_grants(flow.steps) if flow else []
            rows.append(
                {
                    "ref": recipe.ref,
                    "app": recipe.app.label,
                    "app_name": str(recipe.app.verbose_name),
                    "icon": recipe.app.icon,
                    "id": recipe.id,
                    **recipes.words(recipe, ctx.language),
                    "trigger": built["trigger"],
                    "steps": built["steps"],
                    "grants": [{"operation": name, "reason": reasons[name]} for name in recipes.grants(recipe)],
                    "installed": (
                        {
                            "flow_id": flow.id,
                            "name": flow.name,
                            "enabled": flow.enabled,
                            "outdated": flow.recipe_digest != recipes.digest(recipe),
                            "missing_grants": [name for name in required if name not in flow.grants],
                            "repair": recipes.missing_clauses(recipe, flow),
                        }
                        if flow
                        else None
                    ),
                }
            )
        aside = [
            {
                "ref": item.ref,
                "app": item.app.label,
                "app_name": str(item.app.verbose_name),
                "name": recipes.words(item, ctx.language)["name"],
                "code": item.code,
                "message": item.message,
                "apps": list(item.apps),
            }
            for item in set_aside
        ]
    return {"recipes": rows, "set_aside": aside}
