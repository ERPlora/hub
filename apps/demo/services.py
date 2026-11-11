"""Write operations of the demo app: one operation = one transaction, with its event in the outbox.

Every write locks the item's row first, so two writes on the same item never interleave (and two
lines added at once never share a position).
"""

from django.db.models import Max
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.demo import events
from apps.demo.models import Item, ItemLine
from apps.demo.queries import find_item, load_detail
from apps.demo.schemas import DeletedOut, ItemDetailOut, ItemIn, ItemPatchIn, ItemRefIn, LineIn

ITEM_DONE = _("This item is closed: open it to add lines.")


@operation(
    "demo.item.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="demo.manage",
    input=ItemIn,
    output=ItemDetailOut,
    ai={
        "description": "Creates a demo item with its name (up to 120 characters) and, if given, its status («open» "
        "or «done») and a note.",
        "risk": "normal",
        "asks": {
            "en": (
                "create a demo item called Autumn trial",
                "add a new item to Demo named Trial 2 with the note «call the technician»",
            ),
            "es": (
                "crea el elemento «Ensayo de otoño» en la app Demo",
                "nuevo elemento de demo: Ensayo 2, con la nota «llamar al técnico»",
            ),
        },
    },
)
def create_item(ctx: OperationContext, data: ItemIn) -> Item | None:
    item = Item.objects.create(**data.model_dump())
    record_event(ctx, events.ITEM_CREATED, {"id": str(item.id)})
    return load_detail(item.id)


@operation(
    "demo.item.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="demo.manage",
    input=ItemPatchIn,
    output=ItemDetailOut,
    ai={
        "description": "Changes a demo item, by its id or its name, only in what is sent: its name, its status "
        "(«done» closes it to new lines, «open» reopens it) or its note.",
        "risk": "normal",
        "check": "demo.item.detail",
        "asks": {
            "en": (
                "rename the demo item Trial 2 to «Winter trial»",
                "set the status of the demo item Autumn trial to done",
            ),
            "es": (
                "cambia el nombre del elemento «Ensayo 2» de Demo a «Ensayo de invierno»",
                "da por hecho el elemento Ensayo de otoño de la demo y pon en su nota «visto»",
            ),
        },
    },
)
def update_item(ctx: OperationContext, data: ItemPatchIn) -> Item | None:
    """Changes only the fields sent (``null`` leaves one as it is); no change, no event."""
    item = find_item(data, lock=True)
    sent = data.model_dump(exclude_unset=True, exclude_none=True, exclude={"id", "item"})
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="demo.manage",
    input=ItemRefIn,
    output=DeletedOut,
    ai={
        "description": "Deletes a demo item, by its id or its name, together with all its lines. It cannot be undone.",
        "risk": "high",
        "check": "demo.item.detail",
        "asks": {
            "en": (
                "delete the demo item Trial 2 and its lines",
                "remove Autumn trial from Demo for good",
            ),
            "es": (
                "borra el elemento «Ensayo 2» de Demo con sus líneas",
                "quita de la demo el elemento Ensayo de otoño para siempre",
            ),
        },
    },
)
def delete_item(ctx: OperationContext, data: ItemRefIn) -> dict:
    item = find_item(data, lock=True)
    item_id = item.id  # ``delete()`` leaves the instance without its primary key
    item.delete()
    record_event(ctx, events.ITEM_DELETED, {"id": str(item_id)})
    return {"id": item_id}


@operation(
    "demo.item.add_line",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="demo.manage",
    input=LineIn,
    output=ItemDetailOut,
    ai={
        "description": "Adds a line (a text and a quantity above zero) at the end of an open demo item, by its id or "
        "its name; the same client_line_id sent again does not add it twice.",
        "risk": "normal",
        "check": "demo.item.detail",
        "asks": {
            "en": (
                "add a line «screws» with quantity 3 to the demo item Trial 2",
                "put a line «new cables», 4 of them, on Autumn trial in Demo",
            ),
            "es": (
                "añade una línea «tornillos» con cantidad 3 al elemento Ensayo 2 de Demo",
                "mete en el elemento Ensayo de otoño una línea «cables nuevos» con cantidad 4",
            ),
        },
    },
)
def add_line(ctx: OperationContext, data: LineIn) -> Item | None:
    """Appends a line; repeating it with the same ``client_line_id`` returns the item as it is.

    The repeat is checked before the status: a retry of a line that already went in must not be
    rejected (the client would roll back a line the server has) because the item was closed since.
    """
    item = find_item(data, lock=True)
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
