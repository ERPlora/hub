"""Write operations of the demo app: one operation = one transaction, with its event in the outbox.

Every write locks the item's row first, so two writes on the same item never interleave (and two
lines added at once never share a position).
"""

from uuid import UUID

from django.db.models import Max
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.demo import events
from apps.demo.models import Item, ItemLine
from apps.demo.queries import ITEM_NOT_FOUND, load_detail
from apps.demo.schemas import ByIdIn, DeletedOut, ItemDetailOut, ItemIn, ItemPatchIn, LineIn

ITEM_DONE = _("This item is closed: open it to add lines.")


@operation(
    "demo.item.create",
    kind="command",
    permission="demo.manage",
    input=ItemIn,
    output=ItemDetailOut,
    ai={
        "description": "Creates a demo item with its name (up to 120 characters) and, if given, its status («open» "
        "or «done») and a note.",
        "risk": "normal",
    },
)
def create_item(ctx: OperationContext, data: ItemIn) -> Item | None:
    item = Item.objects.create(**data.model_dump())
    record_event(ctx, events.ITEM_CREATED, {"id": str(item.id)})
    return load_detail(item.id)


@operation(
    "demo.item.update",
    kind="command",
    permission="demo.manage",
    input=ItemPatchIn,
    output=ItemDetailOut,
    ai={
        "description": "Changes a demo item, by its id, only in what is sent: its name, its status («done» closes it "
        "to new lines, «open» reopens it) or its note.",
        "risk": "normal",
    },
)
def update_item(ctx: OperationContext, data: ItemPatchIn) -> Item | None:
    """Changes only the fields sent (``null`` leaves one as it is); no change, no event."""
    item = _locked(data.id)
    sent = data.model_dump(exclude_unset=True, exclude_none=True, exclude={"id"})
    changes = {field: value for field, value in sent.items() if getattr(item, field) != value}
    if changes:
        for field, value in changes.items():
            setattr(item, field, value)
        item.save(update_fields=[*changes, "updated_at"])
        record_event(ctx, events.ITEM_UPDATED, {"id": str(item.id)})
    return load_detail(item.id)


@operation(
    "demo.item.delete",
    kind="command",
    permission="demo.manage",
    input=ByIdIn,
    output=DeletedOut,
    ai={
        "description": "Deletes a demo item, by its id, together with all its lines. It cannot be undone.",
        "risk": "high",
    },
)
def delete_item(ctx: OperationContext, data: ByIdIn) -> dict:
    _locked(data.id).delete()
    record_event(ctx, events.ITEM_DELETED, {"id": str(data.id)})
    return {"id": data.id}


@operation(
    "demo.item.add_line",
    kind="command",
    permission="demo.manage",
    input=LineIn,
    output=ItemDetailOut,
    ai={
        "description": "Adds a line (a text and a quantity above zero) at the end of an open demo item, by its id; "
        "the same client_line_id sent again does not add it twice.",
        "risk": "normal",
    },
)
def add_line(ctx: OperationContext, data: LineIn) -> Item | None:
    """Appends a line; repeating it with the same ``client_line_id`` returns the item as it is.

    The repeat is checked before the status: a retry of a line that already went in must not be
    rejected (the client would roll back a line the server has) because the item was closed since.
    """
    item = _locked(data.id)
    if data.client_line_id is not None and item.lines.filter(client_line_id=data.client_line_id).exists():
        return load_detail(item.id)
    if item.status == Item.Status.DONE:
        raise Conflict(ITEM_DONE, code="demo.item_done")
    last = item.lines.aggregate(last=Max("position"))["last"] or 0
    line = ItemLine.objects.create(
        item=item, text=data.text, qty=data.qty, position=last + 1, client_line_id=data.client_line_id
    )
    item.save(update_fields=["updated_at"])  # the item moves up the list
    record_event(ctx, events.ITEM_LINE_ADDED, {"id": str(item.id), "line_id": str(line.id)})
    return load_detail(item.id)


def _locked(item_id: UUID) -> Item:
    """The item, its row locked until the end of the command's transaction."""
    item = Item.objects.select_for_update().filter(pk=item_id).first()
    if item is None:
        raise NotFound(ITEM_NOT_FOUND)
    return item
