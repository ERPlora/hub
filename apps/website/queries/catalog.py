"""The catalog (``read_catalog``, each item as ``catalog_items`` makes it): Inventory's products on sale (with their
photo, description and allergens; only those it shows on the website) or Services' offered services, read by their
operations' names with a context that may read them (as ``apps.flow`` does), only while that app is on in the hub
(``base.apps_on.active_apps``, the website's own guard); an app that is off or not there leaves the catalog empty,
never an error.
"""

from dataclasses import replace
from typing import Any

from live.context import OperationContext, Scope

from apps.website.catalog_items import product_item, service_item
from apps.website.schemas import CatalogSection
from base.apps_on import active_apps
from base.catalog_groups import Group, every_row, in_order, product_groups

#: Each source (its app's label) and what the delegated context may read of it.
SOURCES = {
    "service": frozenset({"service.view_service", "service.view_category"}),
    "inventory": frozenset({"inventory.view_product", "inventory.view_category"}),
}


def read_catalog(ctx: OperationContext, section: CatalogSection) -> dict[str, Any]:
    """The snapshot of ``section``'s source: ``{source, show_prices, groups: [{name, items}]}``.

    Read by the source's operations with ``ctx`` allowed to read it (and nothing else); empty when the section has
    no source or the source's app is not on in the hub.
    """
    snapshot: dict[str, Any] = {"source": section.source, "show_prices": section.show_prices, "groups": []}
    if section.source is None or not _source_on(ctx.scope, section.source):
        return snapshot
    reader = replace(ctx, permissions=ctx.permissions | SOURCES[section.source])
    wanted = {str(category_id) for category_id in section.category_ids}
    groups = _service_groups(reader) if section.source == "service" else _product_groups(reader)
    snapshot["groups"] = [
        {"name": name, "items": items}
        for category_id, name, items in groups
        if items and (not wanted or category_id in wanted)
    ]
    return snapshot


def _source_on(scope: Scope, source: str) -> bool:
    """Whether the catalog's ``source`` (an app's label) is on in ``scope``'s hub, as the website's own guard asks."""
    return source in active_apps(scope)


def _service_categories(ctx: OperationContext) -> list[Any]:
    return list(every_row(ctx, "service.category.list", sort="sort_order"))


def _service_groups(ctx: OperationContext) -> list[Group]:
    """Services' offered services by category, in the categories' order; those without one last."""
    order = {str(row.id): position for position, row in enumerate(_service_categories(ctx))}
    grouped: dict[str, tuple[str, list[dict]]] = {}
    for row in every_row(ctx, "service.service.list_for_sale"):
        category_id = str(row.category_id) if row.category_id else ""
        grouped.setdefault(category_id, (row.category_name or "", []))[1].append(service_item(row))
    return in_order(grouped, order)


def _product_groups(ctx: OperationContext) -> list[Group]:
    """Inventory's products on sale that it shows on the website, by category in their order; without one, last."""
    products = every_row(ctx, "inventory.product.list_for_sale", show_on_website=True)
    return product_groups(ctx, products, product_item)
