"""The list of menus, and one menu with its courses and choices (COMBO-F01, F05, F06, F12)."""

from django.db.models import Count
from live.context import OperationContext
from live.operations import operation

from apps.combo.models import Combo
from apps.combo.schemas.menus import ComboDetailOut, ComboListIn, ComboPage
from apps.combo.schemas.references import ComboRefIn
from base import images
from base.ordering import list_order
from base.text_search import contains_text

from .reads import find_combo
from .rows import _page, combo_row, detail_row, with_tree


@operation(
    "combo.combo.list",
    kind="query",
    permission="combo.view",
    input=ComboListIn,
    output=ComboPage,
    expose_api=True,
    ai={
        "description": "List the menus and combos with their closed price, how they are sold (eaten in or to "
        "take away) and whether they are on sale; search by name.",
        "asks": {
            "en": (
                "which set menus do we have?",
                "list all our combos and how much each one costs",
            ),
            "es": (
                "¿qué menús tenemos montados?",
                "dime los combos que tenemos y cuánto vale cada uno",
            ),
        },
    },
)
def list_combos(ctx: OperationContext, params: ComboListIn) -> dict:
    combos = Combo.objects.select_related("tax_category").annotate(
        courses=Count("groups")
    )
    if params.search:
        combos = combos.filter(contains_text(params.search, "name", "kitchen_name"))
    if params.name:
        combos = combos.filter(contains_text(params.name, "name"))
    if params.supply_kind:
        combos = combos.filter(supply_kind=params.supply_kind)
    if params.is_active is not None:
        combos = combos.filter(is_active=params.is_active)
    ordered = combos.order_by(*list_order(params.sort, "name", descending=params.dir == "desc"))
    page = ordered[params.offset : params.offset + params.limit]
    urls = images.Urls(ctx.scope)
    return _page(
        [combo_row(combo, combo.courses, urls) for combo in page], combos.count(), params
    )


@operation(
    "combo.combo.get",
    kind="query",
    permission="combo.view",
    input=ComboRefIn,
    output=ComboDetailOut,
    expose_api=True,
    ai={
        "description": "One menu with its courses and the choices of each (product, supplement, sold out or not), "
        "whether the till offers it and why not. Name it by id or by name («menu of the day»).",
        "asks": {
            "en": (
                "what does the kids' menu come with?",
                "show me the vegan menu with its courses, choices and supplements",
            ),
            "es": (
                "¿qué lleva el menú infantil?",
                "enséñame el menú vegano con sus platos, elecciones y suplementos",
            ),
        },
    },
)
def get_combo(ctx: OperationContext, data: ComboRefIn) -> dict:
    return detail_row(find_combo(data.id, data.combo, rows=with_tree(Combo.objects.all())), images.Urls(ctx.scope))
