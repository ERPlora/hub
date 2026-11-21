"""The valuation of the options chosen for a product (``modifier.selection.resolve``): each one offered with it, every
group's minimum, maximum and repeats held, and each pick at its catalog price with its tax category and its allergens,
the ones on a line of their own counted apart."""

from collections import Counter

from django.utils.translation import gettext_lazy as _
from live.errors import Conflict

from apps.inventory.models import Unit

OPTION_NOT_OFFERED = _("This option is not offered with this product.")
CHOICE_BELOW_MIN = _("Choose at least %(min)s in «%(group)s».")
CHOICE_ABOVE_MAX = _("Choose at most %(max)s in «%(group)s».")
OPTION_REPEATED = _("«%(option)s» cannot be chosen more than once.")
PRICE_BELOW_ZERO = _("These options take the price of «%(product)s» below zero.")
PRICED_BY_MEASURE = _("«%(product)s» is sold by weight or measure: an option with a supplement cannot go with it.")

#: What a pick that taxes differently carries to its own line, besides how many.
OWN_LINE_FIELDS = ("option_id", "group_id", "name", "kitchen_name", "tax_category_key", "price_delta")


def offered(groups, option_ids: list) -> dict:
    """Every option of ``groups`` by id, with its group, once ``option_ids`` are all among them and every group's
    minimum, maximum and repeats hold; a 409 on ``option_ids`` otherwise."""
    options = {option.id: (option, group) for group in groups for option in group.options.all()}
    if any(option_id not in options for option_id in option_ids):
        raise _refuse("modifier.option_not_offered", str(OPTION_NOT_OFFERED))
    chosen = Counter(option_ids)
    for group in groups:
        _check_group(group, chosen)
    return options


def _check_group(group, chosen: Counter) -> None:
    picked = {option.id: chosen[option.id] for option in group.options.all() if chosen[option.id]}
    repeated = [option for option in group.options.all() if picked.get(option.id, 0) > 1]
    if repeated and not group.allow_repeat:
        raise _refuse("modifier.option_repeated", str(OPTION_REPEATED) % {"option": repeated[0].name})
    count = sum(picked.values())
    if group.max_choices and count > group.max_choices:
        raise _refuse(
            "modifier.choice_above_max", str(CHOICE_ABOVE_MAX) % {"max": group.max_choices, "group": group.name}
        )
    if count < group.min_choices:
        raise _refuse(
            "modifier.choice_below_min", str(CHOICE_BELOW_MIN) % {"min": group.min_choices, "group": group.name}
        )


def pick(option, group, product) -> dict:
    """One choice at its catalog price, with what the kitchen reads and its allergens; on a line of its own when it
    taxes differently from ``product``."""
    return {
        "option_id": option.id,
        "group_id": group.id,
        "group_name": group.name,
        "name": option.name,
        "kitchen_name": option.kitchen_name or option.name,
        "price_delta": option.price_delta,
        "tax_category_key": option.tax_category.key if option.tax_category else None,
        "own_line": option.tax_category_id is not None and option.tax_category_id != product.tax_category_id,
        "allergens": option.allergens,
    }


def folded_delta(product, picks: list[dict]) -> int:
    """The cents the picks not on a line of their own add to ``product``'s unit price; a 409 when a supplement goes
    with a product not sold by the unit, or the dish would cost less than nothing."""
    if any(one["price_delta"] for one in picks) and not _sold_by_unit(product):
        # Sales prices such a line by its quantity (0.350 kg): a supplement would be scaled with it.
        raise _refuse("modifier.priced_by_measure", str(PRICED_BY_MEASURE) % {"product": product.name})
    folded = sum(one["price_delta"] for one in picks if not one["own_line"])
    if product.price + folded < 0:
        raise _refuse("modifier.price_below_zero", str(PRICE_BELOW_ZERO) % {"product": product.name})
    return folded


def own_lines(picks: list[dict]) -> list[dict]:
    """One child line per option that taxes differently, with how many times it was chosen per unit of the dish."""
    lines: dict = {}
    for one in picks:
        if one["own_line"]:
            line = lines.setdefault(one["option_id"], {key: one[key] for key in OWN_LINE_FIELDS} | {"quantity": 0})
            line["quantity"] += 1
    return list(lines.values())


def _sold_by_unit(product) -> bool:
    """Its price is for one unit: what a supplement per unit of the dish can be added to."""
    return product.unit == Unit.UNIT and product.pricing_unit == Unit.UNIT and product.price_quantity == 1


def _refuse(code: str, message: str) -> Conflict:
    return Conflict(message, code=code, fields={"option_ids": message})
