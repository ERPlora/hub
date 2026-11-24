"""How a menu is read with its courses and choices, what the rows of each say and how a list pages."""

from uuid import UUID

from django.db.models import Prefetch, QuerySet
from live.context import Scope

from apps.combo.models import ChoiceGroup, ChoiceOption, Combo
from base import images

from .offers import blockers, offer_status, takeaway_targets


def _options() -> Prefetch:
    """A course's choices, each with its product, in their order."""
    options = ChoiceOption.objects.select_related("product__tax_category").order_by(
        "sort_order", "id"
    )
    return Prefetch("options", queryset=options)


def with_tree(combos: QuerySet[Combo]) -> QuerySet[Combo]:
    """Menus with their category, courses and choices (each with its product) in their order."""
    groups = ChoiceGroup.objects.order_by("sort_order", "name", "id").prefetch_related(
        _options()
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
