"""What of Demo travels in an export of the business (BASE-F35): its items, each with its status, its note and its lines
in order, read with Demo's own list and detail and written with its own create and add-line. An item is named by its
name. Every app says what of it travels the same way: a list of parts, each read with the app's own reads and written
with its own writes, and the models whose rows it carries."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext

from base.blueprint.calls import Dataset, Loaded, attempt, call, count_of, create_each, given, ids_of, listed
from base.blueprint.calls import natural_key, pages, remover, text_of

ITEM_FIELDS = ("name", "status", "note")


def _item_rows(ctx: OperationContext) -> list[dict]:
    items = [call(ctx, "demo.item.detail", id=row.id) for row in pages(ctx, "demo.item.list")]
    return [
        {
            **{name: getattr(item, name) for name in ITEM_FIELDS},
            "lines": [{"text": line.text, "qty": format(line.qty.normalize(), "f")} for line in item.lines],
        }
        for item in items
    ]


def _item_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {natural_key(row.name) for row in pages(ctx, "demo.item.list")}

    def add_lines(row: dict, pk: str) -> None:
        for line in listed(row, "lines", dict):
            attempt(ctx, loaded, text_of(row, "name"), "demo.item.add_line", id=pk, **given(line, ("text", "qty")))

    create_each(ctx, rows, loaded, name="demo.item.create", key=lambda row: natural_key(text_of(row, "name")),
                existing=existing, build=lambda row: given(row, ITEM_FIELDS), label=lambda row: text_of(row, "name"),
                after=add_lines)  # fmt: skip


DATASETS = [
    Dataset(
        key="demo.item",
        label=_("Items"),
        rows=_item_rows,
        ids=ids_of("demo.item.list"),
        count=count_of("demo.item.list"),
        load=_item_load,
        remove=remover("demo.item.delete"),
        models=("Item", "ItemLine"),
    ),
]
