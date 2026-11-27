"""What of Taxes travels in an export of the business (BASE-F35): the tax categories the business made, each with its
rules and their components (the equivalence surcharge), read and written through Taxes' own operations. The factory
catalogue never travels, and a file never touches it: a category whose key the business already has is left as it is,
rules included, and no file makes a factory one. What a load brings stays, like the rest of the business's settings:
a tax category is never deleted and a rule is only deactivated, so undoing a load and resetting leave it."""

import datetime as dt
from collections import defaultdict
from decimal import Decimal
from typing import Any

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext

from base.blueprint.calls import (
    Dataset,
    Loaded,
    attempt,
    count_of,
    create_each,
    given,
    listed,
    natural_key,
    pages,
    text_of,
)

CATEGORY_FIELDS = ("key", "name", "description")
RULE_FIELDS = (
    "country_code", "region_code", "rate_pct", "tax_type", "operation_class", "exempt_reason", "regime_key",
    "valid_from", "valid_to", "component_label",
)  # fmt: skip


def _cell(value: Any) -> Any:
    """A rule's value as the file keeps it: a rate or a date as text, nothing as empty."""
    if value is None:
        return ""
    return str(value) if isinstance(value, Decimal | dt.date) else value


def _rule_row(rule) -> dict:
    return {name: _cell(getattr(rule, name)) for name in RULE_FIELDS}


def _category_rows(ctx: OperationContext) -> list[dict]:
    rows = []
    for category in pages(ctx, "tax.category.list", is_system=False):
        rules = list(pages(ctx, "tax.rule.list", tax_category_key=category.key))
        components = defaultdict(list)
        for rule in rules:
            if rule.parent_id is not None:
                components[rule.parent_id].append(_rule_row(rule))
        roots = [_rule_row(rule) | {"components": components[rule.id]} for rule in rules if rule.parent_id is None]
        rows.append({name: getattr(category, name) for name in CATEGORY_FIELDS} | {"rules": roots})
    return rows


def _fill(ctx: OperationContext, loaded: Loaded, row: dict) -> None:
    key = text_of(row, "key")
    for rule in listed(row, "rules", dict):
        label = " · ".join(part for part in (key, text_of(rule, "country_code"), text_of(rule, "region_code")) if part)
        made = attempt(ctx, loaded, label, "tax.rule.create", **given(rule, RULE_FIELDS), tax_category_key=key)
        if made is None:
            continue
        for component in listed(rule, "components", dict):
            attempt(ctx, loaded, f"{label} · {text_of(component, 'component_label') or text_of(component, 'tax_type')}",
                    "tax.rule.create", **given(component, RULE_FIELDS), tax_category_key=key, parent_id=made.id)


def _category_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    """Each category the business does not have, by its key, made as one of its own with its rules."""
    existing = {natural_key(category.key) for category in pages(ctx, "tax.category.list")}
    create_each(ctx, rows, loaded, name="tax.category.create", key=lambda row: natural_key(text_of(row, "key")),
                existing=existing, build=lambda row: given(row, CATEGORY_FIELDS),
                label=lambda row: text_of(row, "name") or text_of(row, "key"), after=lambda row, pk: _fill(ctx, loaded, row))


DATASETS = [
    Dataset(
        key="tax.category",
        label=_("Own tax categories"),
        rows=_category_rows,
        count=count_of("tax.category.list", is_system=False),
        load=_category_load,
    ),
]
