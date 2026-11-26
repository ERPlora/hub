"""What of Modifiers travels in an export of the business (BASE-F35): every group with its options and the products and
categories it applies to, read with Modifiers' own lists and written with its own creates. A product is named by its
code (its name without one) and a category by its name, never by an id of the business that made the file."""

from collections import defaultdict

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext

from base.blueprint.calls import (
    Dataset,
    Loaded,
    attempt,
    count_of,
    create_each,
    given,
    ids_of,
    listed,
    natural_key,
    pages,
    remover,
    text_of,
)

GROUP_FIELDS = ("name", "kitchen_name", "min_choices", "max_choices", "allow_repeat", "sort_order")
OPTION_FIELDS = ("name", "kitchen_name", "price_delta", "tax_category_key", "allergens", "is_default", "sort_order")


def _option_row(option) -> dict:
    return {name: getattr(option, name) for name in OPTION_FIELDS} | {"tax_category_key": option.tax_category_key or ""}


def _group_rows(ctx: OperationContext) -> list[dict]:
    options = defaultdict(list)
    for option in pages(ctx, "modifier.option.list"):
        options[option.group_id].append(_option_row(option))
    products, categories = defaultdict(list), defaultdict(list)
    for link in pages(ctx, "modifier.link.list"):
        if link.target_kind == "product":
            products[link.group_id].append(link.product_sku or link.product_name)
        else:
            categories[link.group_id].append(link.category_name)
    return [
        {name: getattr(group, name) for name in GROUP_FIELDS}
        | {"options": options[group.id], "products": sorted(products[group.id]), "categories": sorted(categories[group.id])}
        for group in pages(ctx, "modifier.group.list")
    ]


def _fill(ctx: OperationContext, loaded: Loaded, row: dict, pk: str) -> None:
    group = text_of(row, "name")
    for option in listed(row, "options", dict):
        attempt(ctx, loaded, f"{group} · {text_of(option, 'name')}", "modifier.option.create", group_id=pk,
                **given(option, OPTION_FIELDS))
    for product in listed(row, "products", str):
        attempt(ctx, loaded, f"{group} · {product}", "modifier.link.attach", group_id=pk, product=product)
    for category in listed(row, "categories", str):
        attempt(ctx, loaded, f"{group} · {category}", "modifier.link.attach", group_id=pk, category=category)


def _group_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    """Each group the business does not have, by its name, made with its options and hung where it was."""
    existing = {natural_key(group.name) for group in pages(ctx, "modifier.group.list")}
    create_each(ctx, rows, loaded, name="modifier.group.create", key=lambda row: natural_key(text_of(row, "name")),
                existing=existing, build=lambda row: given(row, GROUP_FIELDS), label=lambda row: text_of(row, "name"),
                after=lambda row, pk: _fill(ctx, loaded, row, pk))


DATASETS = [
    Dataset(
        key="modifier.group",
        label=_("Modifier groups"),
        rows=_group_rows,
        ids=ids_of("modifier.group.list"),
        count=count_of("modifier.group.list"),
        load=_group_load,
        remove=remover("modifier.group.delete"),
    ),
]
