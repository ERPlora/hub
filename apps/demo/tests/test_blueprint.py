"""What of Demo travels in an export of the business (BASE-F35): its items, each with its status, its note and its lines,
read with Demo's own list and detail and written with its own create and add-line, so that loading the file brings them
back as they were. Demo is the app every other app is copied from: this is how an app says what of it travels.

Every test runs against the real apps, in business A's own database, as production does.
"""

from decimal import Decimal

from apps.demo.tests.conftest import HUB_DB, in_business_a
from base.tests.blueprint_round_trip import app_report, call, ctx, data_of, exported, loaded_back

__all__ = ["ctx", "in_business_a"]
pytestmark = HUB_DB


def some_items(ctx):
    shelf = call(ctx, "demo.item.create", name="Shelf", note="Oak")
    call(ctx, "demo.item.add_line", id=shelf.id, text="Boards", qty="4")
    call(ctx, "demo.item.add_line", id=shelf.id, text="Screws", qty="0.5")
    call(ctx, "demo.item.create", name="Lamp", status="done")


def the_items(ctx) -> list[tuple]:
    """The items as Demo reads them, with their lines, without ids."""
    rows = call(ctx, "demo.item.list", limit=100).rows
    details = [call(ctx, "demo.item.detail", id=row.id) for row in rows]
    return sorted((item.name, item.status, item.note, tuple((line.text, line.qty) for line in item.lines)) for item in details)


def emptied(ctx) -> None:
    for row in call(ctx, "demo.item.list", limit=100).rows:
        call(ctx, "demo.item.delete", id=row.id)


def items_part(report: dict) -> tuple[int, int]:
    part = next(part for part in app_report(report, "demo")["datasets"] if part["key"] == "demo.item")
    return part["created"], part["already"]


def test_a_backup_brings_the_items_back_with_their_lines(ctx):
    some_items(ctx)
    before = the_items(ctx)
    file = exported(ctx, ["demo"])
    emptied(ctx)

    report = loaded_back(ctx, file)

    assert the_items(ctx) == before
    assert items_part(report) == (2, 0)


def test_loading_the_file_again_duplicates_nothing(ctx):
    some_items(ctx)

    assert items_part(loaded_back(ctx, exported(ctx, ["demo"]))) == (0, 2)


def test_an_item_carries_its_lines_in_order_with_their_exact_quantity(ctx):
    some_items(ctx)

    shelf = next(row for row in data_of(ctx, ["demo"])["demo.item"] if row["name"] == "Shelf")

    assert [(line["text"], Decimal(line["qty"])) for line in shelf["lines"]] == [("Boards", 4), ("Screws", Decimal("0.5"))]
