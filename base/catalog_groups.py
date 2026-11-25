"""A catalog read from the app that owns it, by its operations' names, so an app that does not require it can show it:
every row of a list, page by page, and Inventory's products grouped by their categories in the categories' order, those
without one last. The website's catalog and a table's menu read it this way, each with a context that may read it."""

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from live.context import OperationContext
from live.operations import get, registry

#: The most rows a catalog reads of a list.
MAX_ITEMS = 200
#: The page size of the other apps' lists.
PAGE = 100

#: A category's id (``""`` for none), its name and its items.
Group = tuple[str, str, list[dict]]


def every_row(
    ctx: OperationContext, name: str, limit: int = MAX_ITEMS, page_size: int | None = None, **params: Any
) -> Iterator[Any]:
    """Every row of the list operation ``name`` (page by page, ``PAGE`` rows or the list's own ``page_size``), up to
    ``limit``; none when no installed app gives it."""
    if name not in registry:
        return
    op = get(name)
    size = page_size or PAGE
    offset = 0
    while offset < limit:
        page = op(ctx, op.input(limit=min(size, limit - offset), offset=offset, **params))
        yield from page.rows
        offset += len(page.rows)
        if not page.rows or offset >= page.total:
            return


def product_categories(ctx: OperationContext) -> list[Any]:
    """Inventory's categories in their order, those of the same order by name."""
    return sorted(every_row(ctx, "inventory.category.list"), key=lambda row: (row.order, row.name.lower()))


def product_groups(ctx: OperationContext, products: Iterable[Any], item: Callable[[Any], dict]) -> list[Group]:
    """``products`` (rows of ``inventory.product.list_for_sale``), each as ``item`` makes it, under every category of
    Inventory it is in, by the categories' order; a product in none of them, last."""
    categories = product_categories(ctx)
    order = {str(row.id): position for position, row in enumerate(categories)}
    names = {str(row.id): row.name for row in categories}
    links: dict[str, list[str]] = {}
    for link in every_row(ctx, "inventory.product_category.list", limit=MAX_ITEMS * 5):
        links.setdefault(str(link.product_id), []).append(str(link.category_id))
    grouped: dict[str, tuple[str, list[dict]]] = {}
    for row in products:
        made = item(row)
        for category_id in [cid for cid in links.get(str(row.id), []) if cid in names] or [""]:
            grouped.setdefault(category_id, (names.get(category_id, ""), []))[1].append(made)
    return in_order(grouped, order)


def in_order(grouped: dict[str, tuple[str, list[dict]]], order: dict[str, int]) -> list[Group]:
    """The groups in their categories' order; one whose category is unknown (none, or past the list) last."""
    ranked = sorted(grouped.items(), key=lambda entry: (entry[0] == "", order.get(entry[0], len(order)), entry[1][0]))
    return [(category_id, name, items) for category_id, (name, items) in ranked]
