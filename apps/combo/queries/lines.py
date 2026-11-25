"""The line of a menu with what was picked: its amount, its components and how its VAT is billed (COMBO-F08, F09)."""

from collections import OrderedDict
from functools import partial
from typing import Any
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.combo.models import ChoiceOption, Combo
from apps.combo.schemas.till import ResolvedOut, ResolveIn
from apps.inventory.models import ProductCategory

from .dish_options import Dish, categories, options_amount, priced, takeaway_key, weights
from .offers import premises_key, sold_by_unit, takeaway_targets
from .reads import AMBIGUOUS_OPTION, _names, find_combo
from .rows import with_tree

NOT_ON_SALE = _("That menu is no longer on sale.")
NOTHING_PICKED = _("Pick something from the menu before adding it.")
GROUP_INCOMPLETE = _("The menu still needs a pick in “%(group)s”: pick %(min)s.")
GROUP_TOO_MANY = _("The course “%(group)s” takes %(max)s at most.")
GROUP_NO_REPEAT = _("The course “%(group)s” does not take the same choice twice.")
NOT_A_CHOICE = _("“%(product)s” is not a choice of this menu.")
UNKNOWN_CHOICE = _("That choice is not part of this menu.")
SOLD_OUT = _("“%(product)s” is sold out.")
PRODUCT_UNAVAILABLE = _(
    "“%(product)s” can no longer be sold: it is deactivated or deleted in Inventory."
)
AMOUNT_NEGATIVE = _("The menu's amount cannot be negative.")
COMPONENT_UNTAXED = _(
    "“%(product)s” has no tax category in Inventory, so this menu cannot be charged."
)
MENU_UNTAXED = _(
    "The tax category of this menu is not active in Taxes, so it cannot be charged."
)
TAKEAWAY_UNTAXED = _(
    "“%(product)s” is billed at %(category)s, which has no equivalent to take away in Taxes, so this menu "
    "cannot be sold to take away."
)
NOT_BY_UNIT = _(
    "“%(product)s” is no longer sold by units in Inventory, so it cannot be charged as a menu choice."
)
NO_CATALOG_PRICE = _(
    "The products of this menu have no catalogue price, so its VAT cannot be split."
)

#: Ventas' channels of an order that take the food away (its ``channel``: dine_in, takeaway, delivery).
CHANNELS_AWAY = frozenset({"takeaway", "delivery"})


def split_amount(total: int, weights: list[int]) -> list[int]:
    """``total`` cents shared in proportion to ``weights``: each gets its floor, and the cents left go one
    each to the largest remainders (a tie, to the earlier one). The parts add up to ``total`` exactly."""
    whole = sum(weights)
    if whole == 0:
        return [0] * len(weights)
    shares = [total * weight // whole for weight in weights]
    remainders = [total * weight % whole for weight in weights]
    left = total - sum(shares)
    for index in sorted(range(len(weights)), key=lambda i: (-remainders[i], i))[:left]:
        shares[index] += 1
    return shares


def _picked(combo: Combo, data: ResolveIn) -> tuple["OrderedDict[UUID, int]", dict[UUID, list]]:
    """Each choice picked → how many times, in the order first picked, and the options of Modifiers it carries (those of
    every pick naming it); refused when it is not this menu's."""
    options = {
        option.id: option
        for group in combo.groups.all()
        for option in group.options.all()
    }
    picks: OrderedDict[UUID, int] = OrderedDict()
    extras: dict[UUID, list] = {}
    for choice in data.choices:
        if choice.option_id is not None:
            if choice.option_id not in options:
                raise Conflict(str(UNKNOWN_CHOICE), code="combo.option_not_in_combo")
            option_id = choice.option_id
        else:
            option_id = _named_pick(options.values(), choice.product, choice.group)
        picks[option_id] = picks.get(option_id, 0) + choice.quantity
        extras[option_id] = [*extras.get(option_id, []), *choice.options]
    return picks, extras


def _named_pick(options, said: str, group: str | None) -> UUID:
    """The choice whose product is ``said`` (SKU, exact name, else the only name containing it)."""
    pool = [
        o
        for o in options
        if group is None or o.group.name.casefold() == group.casefold()
    ]
    text = said.casefold()
    for match in (
        lambda o: o.product.sku.casefold() == text,
        lambda o: o.product.name.casefold() == text,
        lambda o: text in o.product.name.casefold(),
    ):
        found = [o for o in pool if match(o)]
        if len(found) > 1:
            names = _names(found, lambda option: option.group.name)
            raise Conflict(
                str(AMBIGUOUS_OPTION) % {"said": said, "names": names},
                code="combo.option_ambiguous",
            )
        if found:
            return found[0].id
    raise Conflict(
        str(NOT_A_CHOICE) % {"product": said}, code="combo.option_not_in_combo"
    )


def _check_groups(combo: Combo, picks: dict[UUID, int]) -> None:
    for group in combo.groups.all():
        counts = [picks[o.id] for o in group.options.all() if o.id in picks]
        total = sum(counts)
        if total < group.min_choices:
            message = str(GROUP_INCOMPLETE) % {
                "group": group.name,
                "min": group.min_choices,
            }
            raise Conflict(message, code="combo.group_incomplete")
        if group.max_choices and total > group.max_choices:
            message = str(GROUP_TOO_MANY) % {
                "group": group.name,
                "max": group.max_choices,
            }
            raise Conflict(message, code="combo.group_too_many")
        if not group.allow_repeat and any(count > 1 for count in counts):
            raise Conflict(
                str(GROUP_NO_REPEAT) % {"group": group.name},
                code="combo.group_no_repeat",
            )


def _first_categories(product_ids: list[UUID]) -> dict[UUID, UUID]:
    """Each product's first live category (by name, as Inventory lists them): the kitchen routes by it."""
    links = ProductCategory.objects.filter(
        product_id__in=product_ids, category__is_deleted=False
    ).order_by("category__name", "category_id")
    first: dict[UUID, UUID] = {}
    for product_id, category_id in links.values_list("product_id", "category_id"):
        first.setdefault(product_id, category_id)
    return first


def _billing(combo: Combo, data: ResolveIn) -> tuple[str, bool]:
    """How this line is billed: ``service`` (one line at the menu's rate) or ``goods`` (per dish), and
    whether it leaves the premises. Ventas' ``channel`` wins over the menu's setting; a menu without a rate
    of its own is billed per dish even on the premises, at the dishes' own (premises) rates."""
    away = data.channel in CHANNELS_AWAY if data.channel else combo.supply_kind == Combo.SupplyKind.GOODS
    if not away and combo.tax_category is not None:
        return Combo.SupplyKind.SERVICE, False
    return Combo.SupplyKind.GOODS, away


def _component_key(name: str, key: str | None, supply: str, away: bool, targets: frozenset[str]) -> str | None:
    """The category a dish, or an option of a line of its own, billed at ``key`` on the premises is billed at in this
    line; refused when a line billed per dish has none."""
    if supply == Combo.SupplyKind.SERVICE:
        return key
    if key is None:
        raise Conflict(str(COMPONENT_UNTAXED) % {"product": name}, code="combo.tax_category_missing")
    target = takeaway_key(key, targets) if away else key
    if target is None:
        message = str(TAKEAWAY_UNTAXED) % {"product": name, "category": key}
        raise Conflict(message, code="combo.tax_category_takeaway")
    return target


def _dish(option: ChoiceOption, quantity: int, extras: list, keyed) -> Dish:
    """A dish picked ``quantity`` times in one menu with its options, as the split reads it (``keyed`` bills each)."""
    product = option.product
    own = [keyed(extra.name, extra.tax_category_key) if extra.own_line else None for extra in extras]
    return Dish(keyed(product.name, premises_key(product)), product.price, quantity, extras, own)


def _shares(amount: int, dishes: list[Dish]) -> list[int]:
    """``amount`` split by the weights of the dishes and of their options of a line of their own."""
    by = weights(dishes)
    if not any(by):
        raise Conflict(str(NO_CATALOG_PRICE), code="combo.no_catalog_price")
    return split_amount(amount, by)


def _check_offer(option: ChoiceOption, charging: bool) -> None:
    """A dish must still be a portion; a new order also needs it on offer (a check being charged was
    ordered when it was, and the last flan served and marked sold out does not stop the table paying)."""
    product = option.product
    if not sold_by_unit(product):
        raise Conflict(str(NOT_BY_UNIT) % {"product": product.name}, code="combo.product_not_by_unit")
    if charging:
        return
    if product.is_deleted or not product.is_active:
        raise Conflict(str(PRODUCT_UNAVAILABLE) % {"product": product.name}, code="combo.product_unavailable")
    # Sold out here, or in Inventory for every menu that offers it (INVENTORY-F29).
    if not option.is_available or product.is_sold_out:
        raise Conflict(str(SOLD_OUT) % {"product": product.name}, code="combo.option_sold_out")


def resolve_line(combo: Combo, data: ResolveIn, targets: frozenset[str]) -> dict[str, Any]:
    """The line of ``combo`` (with its prefetched tree) for what was picked: amount, components and split.

    With ``amount`` (an open check being charged) availability is not asked again: only the courses, the
    portions and the tax data, which decide what the ticket says.
    """
    charging = data.amount is not None
    supply, away = _billing(combo, data)
    if not charging and not combo.is_active:
        raise Conflict(str(NOT_ON_SALE), code="combo.not_on_sale")
    if supply == Combo.SupplyKind.SERVICE and not combo.tax_category.is_active:
        raise Conflict(str(MENU_UNTAXED), code="combo.tax_category_missing")
    picks, extras = _picked(combo, data)
    if not picks:
        raise Conflict(str(NOTHING_PICKED), code="combo.nothing_picked")
    chosen = [(group, o) for group in combo.groups.all() for o in group.options.all() if o.id in picks]
    order = list(picks)
    chosen.sort(key=lambda pair: (pair[0].sort_order, pair[0].name, pair[0].id, order.index(pair[1].id)))
    for _group, option in chosen:
        _check_offer(option, charging)
    _check_groups(combo, picks)
    supplements = sum(option.price_delta * picks[option.id] for _group, option in chosen)
    amount = data.amount if charging else combo.price + supplements + options_amount(picks, extras)
    if amount < 0:
        raise Conflict(str(AMOUNT_NEGATIVE), code="combo.amount_negative")
    keyed = partial(_component_key, supply=supply, away=away, targets=targets)
    dishes = [_dish(option, picks[option.id], extras.get(option.id, []), keyed) for _group, option in chosen]
    split = supply == Combo.SupplyKind.GOODS and len(categories(dishes)) > 1
    shares = _shares(amount, dishes) if split else None
    line_key = combo.tax_category.key if supply == Combo.SupplyKind.SERVICE else (None if split else dishes[0].key)
    first = _first_categories([option.product_id for _group, option in chosen])
    components = [
        {
            "option_id": option.id,
            "group_id": group.id,
            "group_name": group.name,
            "product_id": option.product_id,
            "product_name": option.product.name,
            "sku": option.product.sku,
            "category_id": first.get(option.product_id),
            "is_service": option.product.product_type == "service",
            "quantity": picks[option.id],
            "price_delta": option.price_delta,
            "catalog_price": option.product.price,
            **parts,
        }
        for (group, option), parts in zip(chosen, priced(dishes, shares), strict=True)
    ]
    return {
        "combo_id": combo.id,
        "name": combo.name,
        "kitchen_name": combo.kitchen_name,
        "supply_kind": supply,
        "price": combo.price,
        "supplements": supplements,
        "amount": amount,
        "split": split,
        "tax_category_key": line_key,
        "components": components,
    }


@operation(
    "combo.combo.resolve",
    kind="query",
    permission="combo.view",
    input=ResolveIn,
    output=ResolvedOut,
    expose_api=True,
    ai={
        "description": "Price a menu line with what the customer picked («menu of the day with lentils, hake and "
        "water»): checks each course, adds the supplements and says how its VAT is billed — one line, or one "
        "line per dish with the amount split. It saves nothing; the till charges with it.",
        "asks": {
            "en": (
                "how much is the tasting menu with the steak and water?",
                "work out the kids' menu with pasta and juice, without charging it",
            ),
            "es": (
                "¿cuánto sale el menú degustación con el entrecot y agua?",
                "calcula el menú infantil con macarrones y zumo, sin cobrarlo",
            ),
        },
    },
)
def resolve(ctx: OperationContext, data: ResolveIn) -> dict:
    try:
        combo = find_combo(data.id, data.combo, rows=with_tree(Combo.objects.all()))
    except NotFound as missing:
        # The till's 409: a 404 also means «this app is not active here», which is another fix.
        raise Conflict(missing.message, code="combo.combo_missing") from None
    return resolve_line(combo, data, takeaway_targets())
