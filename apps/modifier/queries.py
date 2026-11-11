"""Read operations of the modifier app, and the lookups its writes share.

The lists of the screen (groups, options, links) page by at most 100 with a stable order ending in the
id. The till reads two things (MODIFIER-F06 to F08): the groups of a product, its own and those of all
its live categories, each once; and the valuation of what was chosen, the only door of a supplement's
price. A link to a product or a category Inventory deleted is left out of every read: Inventory
deletes logically, and until its event is delivered (F09) the link is still in the table.
"""

from collections import Counter
from uuid import UUID

from django.db.models import Count, Prefetch, Q
from django.db.models.functions import Coalesce, Lower
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.inventory.models import ProductCategory, Unit
from apps.inventory.queries import find_category, find_product
from apps.modifier.models import ModifierGroup, ModifierLink, ModifierOption
from apps.modifier.schemas import (
    CategoryRefIn,
    CategoryRefOut,
    GroupListIn,
    GroupOut,
    GroupRefIn,
    LinkDetailOut,
    LinkListIn,
    LinkOut,
    LinkRefIn,
    OptionDetailOut,
    OptionListIn,
    OptionOut,
    OptionRefIn,
    Page,
    ResolveIn,
    ResolveOut,
    TargetIn,
    TargetOut,
)
from base.ordering import list_order, list_order_for

GROUP_NOT_FOUND = _("This group does not exist.")
GROUP_AMBIGUOUS = _("«%(said)s» names several groups: %(names)s. Say which one.")
OPTION_NOT_FOUND = _("This option does not exist.")
LINK_NOT_FOUND = _("This group does not apply there.")
OPTION_AMBIGUOUS = _(
    "«%(said)s» names several options: %(names)s. Say which one, or its group."
)
OPTION_NOT_OFFERED = _("This option is not offered with this product.")
CHOICE_BELOW_MIN = _("Choose at least %(min)s in «%(group)s».")
CHOICE_ABOVE_MAX = _("Choose at most %(max)s in «%(group)s».")
OPTION_REPEATED = _("«%(option)s» cannot be chosen more than once.")
PRICE_BELOW_ZERO = _("These options take the price of «%(product)s» below zero.")
PRICED_BY_MEASURE = _("«%(product)s» is sold by weight or measure: an option with a supplement cannot go with it.")

#: A link whose product or category is still alive in Inventory.
LIVE_LINK = Q(product__isnull=False, product__is_deleted=False) | Q(
    category__isnull=False, category__is_deleted=False
)
_LIVE_LINKS_OF_GROUP = Q(
    links__product__isnull=False, links__product__is_deleted=False
) | Q(links__category__isnull=False, links__category__is_deleted=False)
_GROUP_ORDER = {
    "name": [Lower("name"), "id"],
    "sort_order": ["sort_order", Lower("name"), "id"],
    "min_choices": ["min_choices", Lower("name"), "id"],
    "max_choices": ["max_choices", Lower("name"), "id"],
    "option_count": ["option_count", Lower("name"), "id"],
    "link_count": ["link_count", Lower("name"), "id"],
}
_OPTION_ORDER = {
    "sort_order": ["sort_order", Lower("name"), "id"],
    "name": [Lower("name"), "id"],
    "price_delta": ["price_delta", Lower("name"), "id"],
}


# Lookups shared with services.py


def find_group(
    group_id: UUID | None, said: str | None, *, lock: bool = False, rows=None
) -> ModifierGroup:
    """The group named by its id, or by its name as a person says it: exact (whatever the case), else
    the only one that contains it. ``NotFound`` when none; 409 ``modifier.group_ambiguous`` when several.
    The group comes from ``rows`` when given (e.g. with its counts): one read, so a deletion committed
    meanwhile is either not seen yet or not found, never a row that vanished between two reads."""
    groups = ModifierGroup.objects.all()
    if group_id is None:
        candidates = _first_match(
            groups, (Q(name__iexact=said), Q(name__icontains=said))
        )
        if len(candidates) > 1:
            names = ", ".join(group.name for group in candidates[:5])
            raise Conflict(
                str(GROUP_AMBIGUOUS) % {"said": said, "names": names},
                code="modifier.group_ambiguous",
            )
        group_id = candidates[0].pk if candidates else None
    found = (groups if rows is None else rows).filter(pk=group_id)
    group = (found.select_for_update() if lock else found).first()
    if group is None:
        raise NotFound(str(GROUP_NOT_FOUND))
    return group


def find_option(
    option_id: UUID | None,
    said: str | None,
    group_id: UUID | None = None,
    group_said: str | None = None,
    *,
    lock: bool = False,
) -> ModifierOption:
    """The option named by its id, or by its name (exact, else the only one that contains it), within its
    group when one is said. 409 ``modifier.option_ambiguous`` lists «Option (Group)» when several match."""
    options = ModifierOption.objects.select_related("group")
    if group_id is not None or group_said is not None:
        options = options.filter(group=find_group(group_id, group_said))
    if option_id is None:
        candidates = _first_match(
            options, (Q(name__iexact=said), Q(name__icontains=said))
        )
        if len(candidates) > 1:
            names = ", ".join(_option_label(option) for option in candidates[:5])
            raise Conflict(
                str(OPTION_AMBIGUOUS) % {"said": said, "names": names},
                code="modifier.option_ambiguous",
            )
        option_id = candidates[0].pk if candidates else None
    found = options.filter(pk=option_id)
    option = (found.select_for_update(of=("self",)) if lock else found).first()
    if option is None:
        raise NotFound(str(OPTION_NOT_FOUND))
    return option


def _option_label(option: ModifierOption) -> str:
    return f"{option.name} ({option.group.name})"


def _first_match(queryset, lookups) -> list:
    """The rows of the first lookup that matches anything (in order of preference), at most six."""
    for lookup in lookups:
        rows = list(queryset.filter(lookup).order_by(Lower("name"), "id")[:6])
        if rows:
            return rows
    return []


def groups_with_counts():
    return ModifierGroup.objects.annotate(
        option_count=Count("options", distinct=True),
        default_count=Count(
            "options", filter=Q(options__is_default=True), distinct=True
        ),
        link_count=Count("links", filter=_LIVE_LINKS_OF_GROUP, distinct=True),
    )


def group_row(group: ModifierGroup) -> dict:
    return {
        "id": group.id,
        "name": group.name,
        "kitchen_name": group.kitchen_name,
        "min_choices": group.min_choices,
        "max_choices": group.max_choices,
        "allow_repeat": group.allow_repeat,
        "is_required": group.min_choices >= 1,
        "sort_order": group.sort_order,
        "option_count": group.option_count,
        "default_count": group.default_count,
        "link_count": group.link_count,
        "created_at": group.created_at,
        "updated_at": group.updated_at,
    }


def load_group(group_id: UUID) -> dict:
    return group_row(groups_with_counts().get(pk=group_id))


def option_row(option: ModifierOption) -> dict:
    tax = option.tax_category
    return {
        "id": option.id,
        "group_id": option.group_id,
        "group_name": option.group.name,
        "name": option.name,
        "kitchen_name": option.kitchen_name,
        "price_delta": option.price_delta,
        "tax_category_key": tax.key if tax else None,
        "tax_category_name": tax.display_name if tax else None,
        "is_default": option.is_default,
        "sort_order": option.sort_order,
        "created_at": option.created_at,
        "updated_at": option.updated_at,
    }


def load_option(option_id: UUID) -> dict:
    return option_row(
        ModifierOption.objects.select_related("group", "tax_category").get(pk=option_id)
    )


def link_row(link: ModifierLink) -> dict:
    product, category = link.product, link.category
    return {
        "id": link.id,
        "group_id": link.group_id,
        "group_name": link.group.name,
        "target_kind": link.target_kind,
        "product_id": link.product_id,
        "product_name": product.name if product else None,
        "product_sku": product.sku if product else None,
        "category_id": link.category_id,
        "category_name": category.name if category else None,
        "created_at": link.created_at,
    }


def load_link(link_id: UUID) -> dict:
    return link_row(
        ModifierLink.objects.select_related("group", "product", "category").get(
            pk=link_id
        )
    )


def _page(queryset, params, row) -> dict:
    total = queryset.count()
    rows = [
        row(item) for item in queryset[params.offset : params.offset + params.limit]
    ]
    return {
        "rows": rows,
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
    }


# The groups (MODIFIER-F01, F03)


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
                "¿qué grupos de suplementos tengo montados?",
                "enséñame los extras que se pueden pedir con los platos",
            ),
        },
    },
)
def list_groups(ctx: OperationContext, params: GroupListIn) -> dict:
    groups = groups_with_counts()
    if params.search:
        groups = groups.filter(
            Q(name__icontains=params.search) | Q(kitchen_name__icontains=params.search)
        )
    if params.name:
        groups = groups.filter(name__icontains=params.name)
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
                "which category is Pizzas when it takes add-ons?",
                "find the Sandwiches category the extras apply to",
            ),
            "es": (
                "¿cuál es la familia Pizzas que lleva suplementos?",
                "¿qué familia de suplementos es Bocadillos?",
            ),
        },
    },
)
def get_category(ctx: OperationContext, data: CategoryRefIn) -> dict:
    category = find_category(data.id, data.category)
    return {"id": category.id, "name": category.name}


# The options (MODIFIER-F04)


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
        options = options.filter(Q(name__icontains=params.search) | Q(kitchen_name__icontains=params.search))
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


# The links (MODIFIER-F05)


@operation(
    "modifier.link.list",
    kind="query",
    permission="modifier.view",
    input=LinkListIn,
    output=Page[LinkOut],
    expose_api=True,
    ai={
        "description": "List what modifier groups apply to: the products and categories of a group, or the groups "
        "of a product or of a category.",
        "asks": {
            "en": (
                "which dishes ask for the doneness?",
                "what products is the Sauces group on?",
            ),
            "es": (
                "¿a qué platos se les pregunta el punto de la carne?",
                "¿qué productos llevan el grupo Salsas?",
            ),
        },
    },
)
def list_links(ctx: OperationContext, params: LinkListIn) -> dict:
    links = ModifierLink.objects.filter(LIVE_LINK).select_related(
        "group", "product", "category"
    )
    if params.group_id is not None or params.group is not None:
        links = links.filter(group=find_group(params.group_id, params.group))
    if params.product_id is not None:
        links = links.filter(product_id=params.product_id)
    if params.category_id is not None:
        links = links.filter(category_id=params.category_id)
    links = links.annotate(
        target_name=Lower(Coalesce("product__name", "category__name"))
    ).order_by("target_name", "id")
    return _page(links, params, link_row)


# The till's reads (MODIFIER-F06 to F08)


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


@operation(
    "modifier.link.get",
    kind="query",
    permission="modifier.view",
    input=LinkRefIn,
    output=LinkDetailOut,
    expose_api=True,
    ai={
        "description": "Get one link between a modifier group and what it applies to: by the link's id, or by the "
        "group and the product (id, SKU or name) or category (id or name). One to something deleted is not there.",
        "asks": {
            "en": (
                "does the Margherita pizza carry the Sauces group?",
                "is Extras attached to the fries?",
            ),
            "es": (
                "¿tiene la Pizza margarita enganchado el grupo Salsas?",
                "¿qué asignación hay entre el grupo Extras y las patatas bravas?",
            ),
        },
    },
)
def get_link(ctx: OperationContext, data: LinkRefIn) -> dict:
    links = ModifierLink.objects.filter(LIVE_LINK).select_related("group", "product", "category")
    if data.id is not None:
        link = links.filter(pk=data.id).first()
    else:
        group = find_group(data.group_id, data.group)
        if data.product_id is not None or data.product is not None:
            link = links.filter(group=group, product=find_product(data.product_id, data.product)).first()
        else:
            link = links.filter(group=group, category=find_category(data.category_id, data.category)).first()
    if link is None:
        raise NotFound(str(LINK_NOT_FOUND))
    row = link_row(link)
    return {**row, "label": f"{row['group_name']} · {row['product_name'] or row['category_name']}"}


def _target_option(option: ModifierOption) -> dict:
    return {
        "id": option.id,
        "name": option.name,
        "kitchen_name": option.kitchen_name,
        "price_delta": option.price_delta,
        "tax_category_key": option.tax_category.key if option.tax_category else None,
        "is_default": option.is_default,
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


def _sold_by_unit(product) -> bool:
    """Its price is for one unit: what a supplement per unit of the dish can be added to."""
    return product.unit == Unit.UNIT and product.pricing_unit == Unit.UNIT and product.price_quantity == 1


def _refuse(code: str, message: str) -> Conflict:
    return Conflict(message, code=code, fields={"option_ids": message})


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
    groups = groups_for_product(product)
    offered = {
        option.id: (option, group) for group in groups for option in group.options.all()
    }
    for option_id in data.option_ids:
        if option_id not in offered:
            raise _refuse("modifier.option_not_offered", str(OPTION_NOT_OFFERED))
    chosen = Counter(data.option_ids)
    for group in groups:
        picked = {
            option.id: chosen[option.id]
            for option in group.options.all()
            if chosen[option.id]
        }
        if not group.allow_repeat:
            for option in group.options.all():
                if picked.get(option.id, 0) > 1:
                    raise _refuse(
                        "modifier.option_repeated",
                        str(OPTION_REPEATED) % {"option": option.name},
                    )
        count = sum(picked.values())
        if group.max_choices and count > group.max_choices:
            raise _refuse(
                "modifier.choice_above_max",
                str(CHOICE_ABOVE_MAX) % {"max": group.max_choices, "group": group.name},
            )
        if count < group.min_choices:
            raise _refuse(
                "modifier.choice_below_min",
                str(CHOICE_BELOW_MIN) % {"min": group.min_choices, "group": group.name},
            )
    picks = []
    for option_id in data.option_ids:
        option, group = offered[option_id]
        own_line = option.tax_category_id is not None and option.tax_category_id != product.tax_category_id
        picks.append(
            {
                "option_id": option.id,
                "group_id": group.id,
                "group_name": group.name,
                "name": option.name,
                "kitchen_name": option.kitchen_name or option.name,
                "price_delta": option.price_delta,
                "tax_category_key": option.tax_category.key if option.tax_category else None,
                "own_line": own_line,
            }
        )
    if any(pick["price_delta"] for pick in picks) and not _sold_by_unit(product):
        # Sales prices such a line by its quantity (0.350 kg): a supplement would be scaled with it.
        raise _refuse("modifier.priced_by_measure", str(PRICED_BY_MEASURE) % {"product": product.name})
    folded_delta = sum(pick["price_delta"] for pick in picks if not pick["own_line"])
    if product.price + folded_delta < 0:
        raise _refuse("modifier.price_below_zero", str(PRICE_BELOW_ZERO) % {"product": product.name})
    own_lines: dict = {}
    for pick in picks:
        if pick["own_line"]:
            line = own_lines.setdefault(
                pick["option_id"],
                {key: pick[key] for key in ("option_id", "group_id", "name", "kitchen_name", "tax_category_key", "price_delta")}
                | {"quantity": 0},
            )
            line["quantity"] += 1
    return {
        "product_id": product.id,
        "picks": picks,
        "folded_delta": folded_delta,
        "own_lines": list(own_lines.values()),
        "kitchen_text": ", ".join(pick["kitchen_name"] for pick in picks),
    }
