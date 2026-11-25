"""The till's reads (MODIFIER-F06 to F08): the groups of a product, its own and those of all its live categories,
and the valuation of what was chosen, the only door of a supplement's price.
"""

from django.db.models import Prefetch, Q
from django.db.models.functions import Lower
from live.context import OperationContext
from live.operations import operation

from apps.inventory.models import ProductCategory
from apps.inventory.queries.reads import find_product
from apps.modifier.models import ModifierGroup, ModifierLink, ModifierOption
from apps.modifier.schemas.till import ResolveIn, ResolveOut, TargetIn, TargetOut

from . import selection


def groups_for_product(product) -> list[ModifierGroup]:
    """The groups a live product carries: its own and those of all its live categories, each once, by
    order and name, with their options in order; a group without options has nothing to ask."""
    categories = ProductCategory.objects.filter(
        product=product, category__is_deleted=False
    ).values("category_id")
    linked = ModifierLink.objects.filter(
        Q(product=product) | Q(category_id__in=categories)
    ).values("group_id")
    options = ModifierOption.objects.select_related("tax_category").order_by(
        "sort_order", Lower("name"), "id"
    )
    groups = (
        ModifierGroup.objects.filter(pk__in=linked)
        .prefetch_related(Prefetch("options", queryset=options))
        .order_by("sort_order", Lower("name"), "id")
    )
    return [group for group in groups if group.options.all()]


def _target_option(option: ModifierOption) -> dict:
    return {
        "id": option.id,
        "name": option.name,
        "kitchen_name": option.kitchen_name,
        "price_delta": option.price_delta,
        "tax_category_key": option.tax_category.key if option.tax_category else None,
        "is_default": option.is_default,
        "allergens": option.allergens,
    }


@operation(
    "modifier.group.for_target",
    kind="query",
    permission="modifier.view",
    input=TargetIn,
    output=TargetOut,
    expose_api=True,
    ai={
        "description": "The modifier groups and options of a product (named by its id, SKU or name), its own and "
        "those of its categories: what the till asks before adding the line.",
        "asks": {
            "en": (
                "what does the till ask when selling a Margherita pizza?",
                "which add-ons does the steak sandwich carry, its category's included?",
            ),
            "es": (
                "¿qué hay que preguntar al vender una Pizza margarita?",
                "¿qué extras lleva el Bocadillo de lomo, contando los de su familia?",
            ),
        },
    },
)
def for_target(ctx: OperationContext, data: TargetIn) -> dict:
    product = find_product(data.product_id, data.product)
    groups = [
        {
            "id": group.id,
            "name": group.name,
            "kitchen_name": group.kitchen_name,
            "min_choices": group.min_choices,
            "max_choices": group.max_choices,
            "allow_repeat": group.allow_repeat,
            "is_required": group.min_choices >= 1,
            "options": [_target_option(option) for option in group.options.all()],
        }
        for group in groups_for_product(product)
    ]
    return {"product_id": product.id, "product_name": product.name, "groups": groups}


@operation(
    "modifier.selection.resolve",
    kind="query",
    permission="modifier.view",
    input=ResolveIn,
    output=ResolveOut,
    expose_api=True,
    ai={
        "description": "Check and value the options chosen for a product: that each one is offered with it and "
        "every group's minimum, maximum and repeats hold; returns each one at its catalog price, what to add to "
        "the line, what goes on a line of its own and the kitchen text.",
        "asks": {
            "en": (
                "how much is a pizza with extra cheese and barbecue sauce?",
                "what does the kitchen read for a rare steak?",
            ),
            "es": (
                "con salsa barbacoa y doble de queso, ¿cuánto cuesta la pizza?",
                "¿con qué nota llega a cocina un entrecot poco hecho?",
            ),
        },
    },
)
def resolve_selection(ctx: OperationContext, data: ResolveIn) -> dict:
    product = find_product(data.product_id, data.product)
    offered = selection.offered(groups_for_product(product), data.option_ids)
    picks = [selection.pick(*offered[option_id], product) for option_id in data.option_ids]
    return {
        "product_id": product.id,
        "picks": picks,
        "folded_delta": selection.folded_delta(product, picks),
        "own_lines": selection.own_lines(picks),
        "kitchen_text": ", ".join(pick["kitchen_name"] for pick in picks),
    }
