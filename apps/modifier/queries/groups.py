"""The groups (MODIFIER-F01, F03): their list, one group, and the Inventory category a group applies to."""

from django.db.models.functions import Lower
from live.context import OperationContext
from live.operations import operation

from apps.inventory.queries.reads import find_category
from apps.modifier.schemas.fields import Page
from apps.modifier.schemas.groups import GroupListIn, GroupOut, GroupRefIn
from apps.modifier.schemas.links import CategoryRefIn, CategoryRefOut
from base.ordering import list_order_for
from base.text_search import contains_text

from .reads import _page, find_group, group_row, groups_with_counts

_GROUP_ORDER = {
    "name": [Lower("name"), "id"],
    "sort_order": ["sort_order", Lower("name"), "id"],
    "min_choices": ["min_choices", Lower("name"), "id"],
    "max_choices": ["max_choices", Lower("name"), "id"],
    "option_count": ["option_count", Lower("name"), "id"],
    "link_count": ["link_count", Lower("name"), "id"],
}


@operation(
    "modifier.group.list",
    kind="query",
    permission="modifier.view",
    input=GroupListIn,
    output=Page[GroupOut],
    expose_api=True,
    ai={
        "description": "List the modifier groups (sauces, doneness, extras…) with their rule, how many options "
        "they have and how many products and categories they apply to; a minimum of 1 or more means required.",
        "asks": {
            "en": (
                "which modifier groups have we set up?",
                "what add-ons and extras do we offer with the dishes?",
            ),
            "es": (
                "¿qué grupos de suplementos usamos?",
                "enséñame los extras que se pueden pedir con los platos",
            ),
        },
    },
)
def list_groups(ctx: OperationContext, params: GroupListIn) -> dict:
    groups = groups_with_counts()
    if params.search:
        groups = groups.filter(contains_text(params.search, "name", "kitchen_name"))
    if params.name:
        groups = groups.filter(contains_text(params.name, "name"))
    if params.required is not None:
        groups = (
            groups.filter(min_choices__gte=1)
            if params.required
            else groups.filter(min_choices=0)
        )
    return _page(
        groups.order_by(*list_order_for(params.sort, columns=_GROUP_ORDER)), params, group_row
    )


@operation(
    "modifier.group.get",
    kind="query",
    permission="modifier.view",
    input=GroupRefIn,
    output=GroupOut,
    expose_api=True,
    ai={
        "description": "Get one modifier group, named by its id or its name (e.g. «group Sauces»), with its rule.",
        "asks": {
            "en": (
                "how many sauces can be picked in the Sauces group?",
                "what are the minimum and maximum of the Doneness group?",
            ),
            "es": (
                "¿cuántas salsas se pueden elegir en el grupo Salsas?",
                "dime el mínimo y el máximo del grupo Punto de la carne",
            ),
        },
    },
)
def get_group(ctx: OperationContext, data: GroupRefIn) -> dict:
    return group_row(find_group(data.id, data.group, rows=groups_with_counts()))


@operation(
    "modifier.category.get",
    kind="query",
    permission="modifier.view",
    input=CategoryRefIn,
    output=CategoryRefOut,
    expose_api=True,
    ai={
        "description": "Name by its id, or find by its name, the Inventory category a modifier group applies to, as "
        "the list of what a group applies to names it.",
        "asks": {
            "en": (
                "how is Pizzas named when it takes add-ons?",
                "find Sandwiches to hang extras on it",
            ),
            "es": (
                "¿cómo se identifica Bocadillos al colgarle suplementos?",
                "busca Pizzas, la de los extras",
            ),
        },
    },
)
def get_category(ctx: OperationContext, data: CategoryRefIn) -> dict:
    category = find_category(data.id, data.category)
    return {"id": category.id, "name": category.name}
