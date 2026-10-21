"""Read operations of the demo app (``READ ONLY``); the three of them can be followed live (live.py)."""

from uuid import UUID

from django.db.models import Count, Q
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.demo.models import Item, ItemLine
from apps.demo.schemas import ByIdIn, ItemDetailOut, ItemListIn, ItemPage, ItemStatsIn, ItemStatsOut

ITEM_NOT_FOUND = _("This item no longer exists.")


@operation(
    "demo.item.list",
    kind="query",
    permission="demo.view",
    input=ItemListIn,
    output=ItemPage,
    expose_api=True,
    ai={
        "description": "Lists the demo items, most recently changed first, with their status («open» or «done») "
        "and how many lines each has; searches by a piece of the name and filters by status, a page at a time."
    },
)
def list_items(ctx: OperationContext, params: ItemListIn) -> dict:
    """Most recently changed first, ``id`` as the tie-break so that pages never overlap."""
    items = Item.objects.all()
    if params.search:
        items = items.filter(name__icontains=params.search)
    if params.status:
        items = items.filter(status=params.status)
    rows = items.annotate(line_count=Count("lines")).order_by("-updated_at", "id")
    return {
        "rows": list(rows[params.offset : params.offset + params.limit]),
        "total": items.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


@operation(
    "demo.item.detail",
    kind="query",
    permission="demo.view",
    input=ByIdIn,
    output=ItemDetailOut,
    ai={
        "description": "Returns one demo item by its id: its name, status and note, and its lines (text and "
        "quantity) in the order they were added."
    },
)
def item_detail(ctx: OperationContext, data: ByIdIn) -> Item:
    item = load_detail(data.id)
    if item is None:
        raise NotFound(ITEM_NOT_FOUND)
    return item


@operation(
    "demo.item.stats",
    kind="query",
    permission="demo.manage",
    input=ItemStatsIn,
    output=ItemStatsOut,
    ai={"description": "Counts the demo items: how many there are, how many are open and done, and their lines."},
)
def item_stats(ctx: OperationContext, data: ItemStatsIn) -> dict:
    counts = Item.objects.aggregate(
        total=Count("id"),
        open=Count("id", filter=Q(status=Item.Status.OPEN)),
        done=Count("id", filter=Q(status=Item.Status.DONE)),
    )
    return {**counts, "lines": ItemLine.objects.count()}


def load_detail(item_id: UUID) -> Item | None:
    """The item with its line count and its lines (an ``ItemDetailOut``), or ``None``.

    Not an operation: ``services.py`` returns it after a write, in the command's own transaction.
    """
    return Item.objects.annotate(line_count=Count("lines")).prefetch_related("lines").filter(pk=item_id).first()
