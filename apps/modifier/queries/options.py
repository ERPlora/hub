"""The options of the groups (MODIFIER-F04): their list and one option."""

from django.db.models.functions import Lower
from live.context import OperationContext
from live.operations import operation

from apps.modifier.models import ModifierOption
from apps.modifier.schemas.fields import Page
from apps.modifier.schemas.options import OptionDetailOut, OptionListIn, OptionOut, OptionRefIn
from base.ordering import list_order
from base.text_search import contains_text

from .reads import _option_label, _page, find_group, find_option, option_row

_OPTION_ORDER = {
    "sort_order": ["sort_order", Lower("name"), "id"],
    "name": [Lower("name"), "id"],
    "price_delta": ["price_delta", Lower("name"), "id"],
}


@operation(
    "modifier.option.list",
    kind="query",
    permission="modifier.view",
    input=OptionListIn,
    output=Page[OptionOut],
    expose_api=True,
    ai={
        "description": "List the options of a modifier group (or of every group) with their supplement in cents, "
        "their own tax category if any and whether they come chosen by default.",
        "asks": {
            "en": (
                "which sauces can people choose and what does each cost?",
                "list the choices of Doneness and which one is preselected",
            ),
            "es": (
                "¿qué salsas hay para elegir y cuánto cuesta cada una?",
                "¿qué opciones trae Punto de la carne y cuál viene por defecto?",
            ),
        },
    },
)
def list_options(ctx: OperationContext, params: OptionListIn) -> dict:
    options = ModifierOption.objects.select_related("group", "tax_category")
    by_group = ()
    if params.group_id is not None or params.group is not None:
        options = options.filter(group=find_group(params.group_id, params.group))
    elif params.sort.lstrip("-") == "sort_order":
        # The whole catalog in the till's order: by its groups' order and name, then each group's own.
        by_group = ("group__sort_order", Lower("group__name"), "group_id")
    order = list_order(
        *by_group, *_OPTION_ORDER[params.sort.removeprefix("-")], descending=params.sort.startswith("-")
    )
    if params.search:
        options = options.filter(contains_text(params.search, "name", "kitchen_name"))
    return _page(options.order_by(*order), params, option_row)


@operation(
    "modifier.option.get",
    kind="query",
    permission="modifier.view",
    input=OptionRefIn,
    output=OptionDetailOut,
    expose_api=True,
    ai={
        "description": "Get one option of a modifier group, named by its id or its name (and its group, when two "
        "groups have one with that name), with its supplement in cents and the group it belongs to.",
        "asks": {
            "en": (
                "how much is the extra cheese option?",
                "which group is the Gluten free option in?",
            ),
            "es": (
                "¿qué suplemento lleva la opción Doble de queso?",
                "¿de qué grupo es la opción Sin gluten?",
            ),
        },
    },
)
def get_option(ctx: OperationContext, data: OptionRefIn) -> dict:
    option = find_option(data.id, data.option, data.group_id, data.group)
    return {**option_row(option), "label": _option_label(option)}
