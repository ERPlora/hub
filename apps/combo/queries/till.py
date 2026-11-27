"""The menus the till can sell now, with the choices on offer (COMBO-F07)."""

from live.context import OperationContext
from live.operations import operation

from apps.combo.models import Combo
from apps.combo.schemas.till import ForSaleIn, SaleComboPage
from base import images
from base.text_search import contains_text

from .offers import blockers, offer_status, takeaway_targets
from .rows import _page, with_tree


@operation(
    "combo.combo.for_sale",
    kind="query",
    permission="combo.view",
    input=ForSaleIn,
    output=SaleComboPage,
    expose_api=True,
    ai={
        "description": "The menus the till can sell now, with their courses and the choices on offer (product and "
        "supplement); a menu that cannot be completed or is off sale is left out.",
        "asks": {
            "en": (
                "which menus can customers choose today?",
                "which set menus are on offer at the counter today?",
            ),
            "es": (
                "¿qué menús se pueden pedir ya?",
                "¿qué menús hay hoy en el mostrador y qué ofrece cada plato?",
            ),
        },
    },
)
def list_for_sale(ctx: OperationContext, params: ForSaleIn) -> dict:
    combos = with_tree(
        Combo.objects.filter(is_active=True).order_by("sort_order", "name", "id")
    )
    if params.search:
        combos = combos.filter(contains_text(params.search, "name"))
    targets = takeaway_targets()
    sellable = [combo for combo in combos if not blockers(combo, targets)]
    urls = images.Urls(ctx.scope)
    rows = [
        _sale_row(combo, targets, urls)
        for combo in sellable[params.offset : params.offset + params.limit]
    ]
    return _page(rows, len(sellable), params)


def _sale_row(combo: Combo, targets: frozenset[str], urls: images.Urls) -> dict:
    groups = []
    for group in combo.groups.all():
        options = [
            {
                "id": option.id,
                "product_id": option.product_id,
                "product_name": option.product.name,
                "sku": option.product.sku,
                "price_delta": option.price_delta,
                "allergens": option.product.allergens,
            }
            for option in group.options.all()
            if offer_status(option, targets) == "offered"
        ]
        if options:
            groups.append(
                {
                    "id": group.id,
                    "name": group.name,
                    "min_choices": group.min_choices,
                    "max_choices": group.max_choices,
                    "allow_repeat": group.allow_repeat,
                    "options": options,
                }
            )
    return {
        "id": combo.id,
        "name": combo.name,
        "kitchen_name": combo.kitchen_name,
        "price": combo.price,
        "supply_kind": combo.supply_kind,
        "sort_order": combo.sort_order,
        "image": combo.image,
        "image_url": urls(combo.image),
        "groups": groups,
    }
