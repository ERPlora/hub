"""Read operations of the combo app (``READ ONLY``), and the finders and rows services.py reuses.

A menu is named by its id or its name; a course by its id, or its name inside its menu; a choice by its
id, or by its product (SKU or name) inside its menu or course: exact first, else the only one that
contains the text; several → 409 ``*_ambiguous`` with the candidates. Inventory and Taxes are this
app's ``requires``: their products and categories are read straight from their models.

A choice is **offered** when it is available here, its product is active, not deleted and sold by
units in Inventory and, in a menu to take away, it has a rate to bill it at. A menu is **sellable** (the
till offers it) when it is on sale, has at least one choice on offer, every compulsory course has enough
of them (its minimum, or one when it may repeat) and, split per dish, some catalogue price to weigh.
``resolve_line`` is the price and VAT authority of a menu line (COMBO-F08, F09): eaten in or to take
away is the menu's setting unless Ventas says how this line is sold (its order's ``channel``).
"""

from collections import OrderedDict
from typing import Any
from uuid import UUID

from django.db.models import Count, Prefetch, Q, QuerySet
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.combo.models import ChoiceGroup, ChoiceOption, Combo
from apps.combo.schemas import (
    ComboDetailOut,
    ComboListIn,
    ComboImageSuggestIn,
    ComboImageSuggestOut,
    ComboPage,
    ComboRefIn,
    ForSaleIn,
    ResolvedOut,
    ResolveIn,
    SaleComboPage,
)
from apps.inventory.models import ProductCategory, Unit
from apps.tax.models import TaxCategory
from base import images
from base.queries import business_language, image_library

COMBO_NOT_FOUND = _("That menu does not exist in this business.")
GROUP_NOT_FOUND = _("That course does not exist in this menu.")
OPTION_NOT_FOUND = _("That choice does not exist in this menu.")
AMBIGUOUS_COMBO = _(
    "There are several menus called “%(said)s”: %(names)s. Say which one."
)
AMBIGUOUS_GROUP = _(
    "There are several courses called “%(said)s”: %(names)s. Say which one."
)
AMBIGUOUS_OPTION = _(
    "“%(said)s” is a choice of several courses: %(names)s. Say which course."
)
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
# Why a menu is not on the till (combo.combo.get «blockers»).
BLOCK_NOT_ON_SALE = _("It is not on sale.")
BLOCK_TAX_INACTIVE = _("Its tax category is not active in Taxes.")
BLOCK_NO_CHOICES = _("No course has a choice on offer.")
BLOCK_NO_CATALOG_PRICE = _(
    "Its choices cost nothing in the catalogue and are billed at different rates, so its VAT cannot be split."
)
BLOCK_GROUP_SHORT = _(
    "The course “%(group)s” has fewer choices on offer than it asks for."
)

#: To take away, the category of what is served on the premises becomes the one of a sale of goods: a
#: beer drunk at the table is a hospitality service at 10 % (art. 91.Uno.2.2 LIVA), the same beer to take
#: away a sale of goods at 21 % (art. 90). Explicit on purpose: only Taxes' factory pair is mapped; a
#: category of the business's own is billed as it is.
TAKEAWAY_CATEGORY = {"restaurant.alcohol": "retail.alcohol"}
#: Ventas' channels of an order that take the food away (its ``channel``: dine_in, takeaway, delivery).
CHANNELS_AWAY = frozenset({"takeaway", "delivery"})

#: How many candidates an ambiguous reference lists.
MAX_CANDIDATES = 5
#: The list's sort keys → model columns (the name and the id break ties).
COMBO_ORDER = {
    "sort_order": "sort_order",
    "name": "name",
    "price": "price",
    "supply_kind": "supply_kind",
    "is_active": "is_active",
    "id": "id",
}


# --- Finders -----------------------------------------------------------------------------------


def _first_match(queryset: QuerySet, lookups) -> list:
    """The rows of the first lookup that matches anything, in order of preference (at most six)."""
    for lookup in lookups:
        rows = list(queryset.filter(lookup)[: MAX_CANDIDATES + 1])
        if rows:
            return rows
    return []


def _names(rows, label) -> str:
    return ", ".join(label(row) for row in rows[:MAX_CANDIDATES])


def find_combo(
    combo_id: UUID | None, said: str | None, *, lock: bool = False, rows: QuerySet[Combo] | None = None
) -> Combo:
    """The menu named by its id, or by its name as a person says it. It comes from ``rows`` when given
    (e.g. with its tree): one read, so a deletion committed meanwhile is either not seen yet or not
    found, never a row that vanished between two reads."""
    combos = Combo.objects.order_by("name", "id")
    if combo_id is None:
        candidates = _first_match(
            combos, (Q(name__iexact=said), Q(name__icontains=said))
        )
        if len(candidates) > 1:
            names = _names(candidates, lambda combo: combo.name)
            raise Conflict(
                str(AMBIGUOUS_COMBO) % {"said": said, "names": names},
                code="combo.combo_ambiguous",
            )
        combo_id = candidates[0].pk if candidates else None
    found = (Combo.objects.all() if rows is None else rows).filter(pk=combo_id)
    combo = (found.select_for_update() if lock else found).first()
    if combo is None:
        raise NotFound(str(COMBO_NOT_FOUND))
    return combo


def find_group(
    group_id: UUID | None,
    combo_id: UUID | None,
    combo: str | None,
    said: str | None,
    *,
    lock: bool = False,
) -> ChoiceGroup:
    """The course named by its id, or by its name inside its menu."""
    if group_id is None:
        menu = find_combo(combo_id, combo)
        groups = menu.groups.order_by("sort_order", "name", "id")
        candidates = _first_match(
            groups, (Q(name__iexact=said), Q(name__icontains=said))
        )
        if len(candidates) > 1:
            names = _names(candidates, lambda group: group.name)
            raise Conflict(
                str(AMBIGUOUS_GROUP) % {"said": said, "names": names},
                code="combo.group_ambiguous",
            )
        group_id = candidates[0].pk if candidates else None
    found = ChoiceGroup.objects.filter(pk=group_id).select_related("combo")
    group = (found.select_for_update(of=("self",)) if lock else found).first()
    if group is None:
        raise NotFound(str(GROUP_NOT_FOUND))
    return group


def _product_lookups(said: str):
    return (
        Q(product__sku__iexact=said),
        Q(product__name__iexact=said),
        Q(product__name__icontains=said),
    )


def find_option(
    option_id: UUID | None,
    *,
    combo_id: UUID | None = None,
    combo: str | None = None,
    group_id: UUID | None = None,
    group: str | None = None,
    product: str | None = None,
    lock: bool = False,
) -> ChoiceOption:
    """The choice named by its id, or by its product inside its menu (and its course when told)."""
    if option_id is None:
        # The schemas ask for the menu (or the course's id) whenever a choice is named by its product.
        if group_id is not None or group is not None:
            options = ChoiceOption.objects.filter(group=find_group(group_id, combo_id, combo, group))
        else:
            options = ChoiceOption.objects.filter(group__combo=find_combo(combo_id, combo))
        options = options.select_related("group", "product").order_by(
            "group__sort_order", "sort_order", "id"
        )
        candidates = _first_match(options, _product_lookups(product))
        if len(candidates) > 1:
            names = _names(candidates, lambda option: option.group.name)
            raise Conflict(
                str(AMBIGUOUS_OPTION) % {"said": product, "names": names},
                code="combo.option_ambiguous",
            )
        option_id = candidates[0].pk if candidates else None
    found = ChoiceOption.objects.filter(pk=option_id).select_related(
        "group__combo", "product"
    )
    option = (found.select_for_update(of=("self",)) if lock else found).first()
    if option is None:
        raise NotFound(str(OPTION_NOT_FOUND))
    return option


# --- Rows --------------------------------------------------------------------------------------


def takeaway_targets() -> frozenset[str]:
    """The categories of ``TAKEAWAY_CATEGORY`` that Taxes has active: read once per operation."""
    targets = TaxCategory.objects.filter(key__in=TAKEAWAY_CATEGORY.values(), is_active=True)
    return frozenset(targets.values_list("key", flat=True))


def sold_by_unit(product) -> bool:
    """A portion: sold by units and priced per unit (the catalogue price is what one pick weighs)."""
    return product.unit == Unit.UNIT and product.pricing_unit == Unit.UNIT and product.price_quantity == 1


def premises_key(product) -> str | None:
    """The product's tax category, while Taxes has it active."""
    tax = product.tax_category
    return tax.key if tax and tax.is_active else None


def away_key(product, targets: frozenset[str]) -> str | None:
    """The category the product is billed at to take away; ``None`` when it has none."""
    key = premises_key(product)
    if key in TAKEAWAY_CATEGORY:
        target = TAKEAWAY_CATEGORY[key]
        return target if target in targets else None
    return key


def offer_status(option: ChoiceOption, targets: frozenset[str]) -> str:
    """offered, or why not: the product deleted, deactivated, sold out (INVENTORY-F29) or not sold by
    units in Inventory; with no rate to bill it at in a menu to take away; or sold out here."""
    product = option.product
    if product.is_deleted:
        return "product_deleted"
    if not product.is_active:
        return "product_inactive"
    if product.is_sold_out:
        return "product_sold_out"
    if not sold_by_unit(product):
        return "not_by_unit"
    if option.group.combo.supply_kind == Combo.SupplyKind.GOODS and away_key(product, targets) is None:
        return "untaxed"
    if not option.is_available:
        return "sold_out"
    return "offered"


def with_tree(combos: QuerySet[Combo]) -> QuerySet[Combo]:
    """Menus with their category, courses and choices (each with its product) in their order."""
    options = ChoiceOption.objects.select_related("product__tax_category").order_by(
        "sort_order", "id"
    )
    groups = ChoiceGroup.objects.order_by("sort_order", "name", "id").prefetch_related(
        Prefetch("options", queryset=options)
    )
    return combos.select_related("tax_category").prefetch_related(
        Prefetch("groups", queryset=groups)
    )


def option_row(option: ChoiceOption, targets: frozenset[str]) -> dict:
    product = option.product
    return {
        "id": option.id,
        "group_id": option.group_id,
        "product_id": product.id,
        "product_name": product.name,
        "sku": product.sku,
        "catalog_price": product.price,
        "price_delta": option.price_delta,
        "is_available": option.is_available,
        "sort_order": option.sort_order,
        "status": offer_status(option, targets),
    }


def group_row(group: ChoiceGroup, targets: frozenset[str]) -> dict:
    return {
        "id": group.id,
        "combo_id": group.combo_id,
        "name": group.name,
        "min_choices": group.min_choices,
        "max_choices": group.max_choices,
        "allow_repeat": group.allow_repeat,
        "sort_order": group.sort_order,
        "options": [option_row(option, targets) for option in group.options.all()],
    }


def combo_row(combo: Combo, group_count: int, urls: images.Urls) -> dict:
    tax = combo.tax_category
    return {
        "id": combo.id,
        "name": combo.name,
        "kitchen_name": combo.kitchen_name,
        "price": combo.price,
        "supply_kind": combo.supply_kind,
        "tax_category_key": tax.key if tax else None,
        "tax_category_name": tax.display_name if tax else None,
        "sort_order": combo.sort_order,
        "is_active": combo.is_active,
        "group_count": group_count,
        "image": combo.image,
        "image_url": urls(combo.image),
        "created_at": combo.created_at,
        "updated_at": combo.updated_at,
    }


def blockers(combo: Combo, targets: frozenset[str]) -> list[dict]:
    """Why the till does not offer ``combo`` (empty: it does). Reads its prefetched tree."""
    found: list[dict] = []
    if not combo.is_active:
        found.append(
            {
                "code": "combo.not_on_sale",
                "message": str(BLOCK_NOT_ON_SALE),
                "group_id": None,
            }
        )
    if combo.supply_kind == Combo.SupplyKind.SERVICE and not (
        combo.tax_category and combo.tax_category.is_active
    ):
        found.append(
            {
                "code": "combo.tax_category_inactive",
                "message": str(BLOCK_TAX_INACTIVE),
                "group_id": None,
            }
        )
    groups = list(combo.groups.all())
    offered = {
        group.id: [o for o in group.options.all() if offer_status(o, targets) == "offered"]
        for group in groups
    }
    if not any(offered.values()):
        found.append(
            {
                "code": "combo.no_choices",
                "message": str(BLOCK_NO_CHOICES),
                "group_id": None,
            }
        )
        return found
    for group in groups:
        count = len(offered[group.id])
        if (
            group.min_choices
            and count < group.min_choices
            and not (group.allow_repeat and count)
        ):
            message = str(BLOCK_GROUP_SHORT) % {"group": group.name}
            found.append(
                {"code": "combo.group_short", "message": message, "group_id": group.id}
            )
    on_offer = [option for options in offered.values() for option in options]
    if combo.supply_kind == Combo.SupplyKind.GOODS:
        rates = {away_key(option.product, targets) for option in on_offer}
        if len(rates) > 1 and not any(option.product.price for option in on_offer):
            found.append(
                {"code": "combo.no_catalog_price", "message": str(BLOCK_NO_CATALOG_PRICE), "group_id": None}
            )
    return found


def load_detail(combo_id: UUID, scope: Scope) -> dict:
    """The detail of a menu of ``scope`` by its id. Services return it after a write, with the menu locked."""
    return detail_row(with_tree(Combo.objects.filter(pk=combo_id)).get(), images.Urls(scope))


def detail_row(combo: Combo, urls: images.Urls) -> dict:
    """The menu (with its prefetched tree), whether the till offers it and why not."""
    groups = list(combo.groups.all())
    targets = takeaway_targets()
    found = blockers(combo, targets)
    return {
        **combo_row(combo, len(groups), urls),
        "groups": [group_row(group, targets) for group in groups],
        "sellable": not found,
        "blockers": found,
    }


def _page(rows: list, total: int, params) -> dict:
    return {
        "rows": rows,
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
    }


# --- Menus (COMBO-F01, F05, F06, F12) -------------------------------------------------------------


@operation(
    "combo.combo.list",
    kind="query",
    permission="combo.view",
    input=ComboListIn,
    output=ComboPage,
    expose_api=True,
    ai={
        "description": "List the menus and combos with their closed price, how they are sold (eaten in or to "
        "take away) and whether they are on sale; search by name."
    },
)
def list_combos(ctx: OperationContext, params: ComboListIn) -> dict:
    combos = Combo.objects.select_related("tax_category").annotate(
        courses=Count("groups")
    )
    if params.search:
        combos = combos.filter(
            Q(name__icontains=params.search) | Q(kitchen_name__icontains=params.search)
        )
    if params.name:
        combos = combos.filter(name__icontains=params.name)
    if params.supply_kind:
        combos = combos.filter(supply_kind=params.supply_kind)
    if params.is_active is not None:
        combos = combos.filter(is_active=params.is_active)
    column = COMBO_ORDER[params.sort]
    sign = "-" if params.dir == "desc" else ""
    ties = [key for key in ("name", "id") if key != column]
    ordered = combos.order_by(f"{sign}{column}", *ties)
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
        "whether the till offers it and why not. Name it by id or by name («menu of the day»)."
    },
)
def get_combo(ctx: OperationContext, data: ComboRefIn) -> dict:
    return detail_row(find_combo(data.id, data.combo, rows=with_tree(Combo.objects.all())), images.Urls(ctx.scope))


@operation(
    "combo.combo.suggest_image",
    kind="query",
    permission="combo.view",
    input=ComboImageSuggestIn,
    output=ComboImageSuggestOut,
    expose_api=True,
    ai={
        "description": "Propose images of ERPlora's shared image library for a menu's photo («ponle foto al menú del "
        "día»), the menu named by its id or its name: the best matches for its name first, each with its title and its reference (catalog:<folder>/<name>). It "
        "never sets one: show them, and set the one the person picks with combo.combo.set_image."
    },
)
def suggest_image(ctx: OperationContext, data: ComboImageSuggestIn) -> dict:
    """COMBO-F14: the library searched by the menu's name in either of its languages, titled in the business's."""
    combo = find_combo(data.id, data.combo)
    language = business_language(ctx)
    found = image_library(ctx).search(combo.name, language)
    return {
        "combo_id": combo.id,
        "query": combo.name,
        "rows": [image.row(language) for image in found[: data.limit]],
    }


# --- The till (COMBO-F07, F08, F09) --------------------------------------------------------------


@operation(
    "combo.combo.for_sale",
    kind="query",
    permission="combo.view",
    input=ForSaleIn,
    output=SaleComboPage,
    expose_api=True,
    ai={
        "description": "The menus the till can sell now, with their courses and the choices on offer (product and "
        "supplement); a menu that cannot be completed or is off sale is left out."
    },
)
def list_for_sale(ctx: OperationContext, params: ForSaleIn) -> dict:
    combos = with_tree(
        Combo.objects.filter(is_active=True).order_by("sort_order", "name", "id")
    )
    if params.search:
        combos = combos.filter(name__icontains=params.search)
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


def _picked(combo: Combo, data: ResolveIn) -> "OrderedDict[UUID, int]":
    """Each choice picked → how many times, in the order first picked; refused when it is not this menu's."""
    options = {
        option.id: option
        for group in combo.groups.all()
        for option in group.options.all()
    }
    picks: OrderedDict[UUID, int] = OrderedDict()
    for choice in data.choices:
        if choice.option_id is not None:
            if choice.option_id not in options:
                raise Conflict(str(UNKNOWN_CHOICE), code="combo.option_not_in_combo")
            option_id = choice.option_id
        else:
            option_id = _named_pick(options.values(), choice.product, choice.group)
        picks[option_id] = picks.get(option_id, 0) + choice.quantity
    return picks


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


def _component_key(option: ChoiceOption, supply: str, away: bool, targets: frozenset[str]) -> str | None:
    """The category a dish is billed at; refused when a line billed per dish has none."""
    product = option.product
    key = premises_key(product)
    if supply == Combo.SupplyKind.SERVICE:
        return key
    if key is None:
        raise Conflict(str(COMPONENT_UNTAXED) % {"product": product.name}, code="combo.tax_category_missing")
    if not away:
        return key
    target = away_key(product, targets)
    if target is None:
        message = str(TAKEAWAY_UNTAXED) % {"product": product.name, "category": key}
        raise Conflict(message, code="combo.tax_category_takeaway")
    return target


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
    picks = _picked(combo, data)
    if not picks:
        raise Conflict(str(NOTHING_PICKED), code="combo.nothing_picked")
    chosen = [(group, o) for group in combo.groups.all() for o in group.options.all() if o.id in picks]
    order = list(picks)
    chosen.sort(key=lambda pair: (pair[0].sort_order, pair[0].name, pair[0].id, order.index(pair[1].id)))
    for _group, option in chosen:
        _check_offer(option, charging)
    _check_groups(combo, picks)
    supplements = sum(option.price_delta * picks[option.id] for _group, option in chosen)
    amount = data.amount if charging else combo.price + supplements
    if amount < 0:
        raise Conflict(str(AMOUNT_NEGATIVE), code="combo.amount_negative")
    keys = [_component_key(option, supply, away, targets) for _group, option in chosen]
    split = supply == Combo.SupplyKind.GOODS and len(set(keys)) > 1
    shares: list[int | None] = [None] * len(chosen)
    if split:
        weights = [option.product.price * picks[option.id] for _group, option in chosen]
        if not any(weights):
            raise Conflict(str(NO_CATALOG_PRICE), code="combo.no_catalog_price")
        shares = split_amount(amount, weights)
    if supply == Combo.SupplyKind.SERVICE:
        line_key = combo.tax_category.key
    else:
        line_key = None if split else keys[0]
    categories = _first_categories([option.product_id for _group, option in chosen])
    components = [
        {
            "option_id": option.id,
            "group_id": group.id,
            "group_name": group.name,
            "product_id": option.product_id,
            "product_name": option.product.name,
            "sku": option.product.sku,
            "category_id": categories.get(option.product_id),
            "is_service": option.product.product_type == "service",
            "quantity": picks[option.id],
            "price_delta": option.price_delta,
            "catalog_price": option.product.price,
            "tax_category_key": key,
            "amount": share,
        }
        for (group, option), key, share in zip(chosen, keys, shares, strict=True)
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
        "line per dish with the amount split. It saves nothing; the till charges with it."
    },
)
def resolve(ctx: OperationContext, data: ResolveIn) -> dict:
    try:
        combo = find_combo(data.id, data.combo, rows=with_tree(Combo.objects.all()))
    except NotFound as missing:
        # The till's 409: a 404 also means «this app is not active here», which is another fix.
        raise Conflict(missing.message, code="combo.combo_missing") from None
    return resolve_line(combo, data, takeaway_targets())
