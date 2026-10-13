"""Read operations of the demo app: the paginated list, the detail and the stats."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from live.errors import NotFound, PermissionDenied
from live.operations import get

from apps.demo.models import Item, ItemLine
from apps.demo.schemas import ByIdIn, ItemDetailOut, ItemListIn, ItemPage, ItemStatsIn, ItemStatsOut

from .conftest import ctx_for

pytestmark = pytest.mark.django_db


def run(name, data, role="hub_admin"):
    return get(name)(ctx_for(role), data)


def list_items(role="hub_admin", **params):
    return run("demo.item.list", ItemListIn(**params), role)


def make(name, status="open", lines=0, minutes_ago=0):
    item = Item.objects.create(name=name, status=status)
    for position in range(1, lines + 1):
        ItemLine.objects.create(item=item, text=f"line {position}", qty=Decimal("1"), position=position)
    Item.objects.filter(pk=item.pk).update(updated_at=timezone.now() - timedelta(minutes=minutes_ago))
    return Item.objects.get(pk=item.pk)


# Declarations


@pytest.mark.parametrize(
    ("name", "permission", "input", "output", "expose_api"),
    [
        ("demo.item.list", "demo.view", ItemListIn, ItemPage, True),
        ("demo.item.detail", "demo.view", ByIdIn, ItemDetailOut, False),
        ("demo.item.stats", "demo.manage", ItemStatsIn, ItemStatsOut, False),
    ],
)
def test_declarations(name, permission, input, output, expose_api):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output, op.expose_api) == ("query", permission, input, output, expose_api)


# demo.item.list


def test_empty_list():
    assert list_items().model_dump() == {"rows": [], "total": 0, "limit": 50, "offset": 0}


def test_most_recently_changed_first_with_line_count():
    old = make("Old", lines=2, minutes_ago=10)
    new = make("New", minutes_ago=1)
    page = list_items()
    assert [(row.id, row.name, row.line_count) for row in page.rows] == [(new.id, "New", 0), (old.id, "Old", 2)]
    assert page.rows[0].updated_at == new.updated_at


def test_pages_are_stable_with_id_as_tie_break():
    items = [make(f"Item {n}", lines=n % 2) for n in range(5)]
    Item.objects.update(updated_at=timezone.now())  # the same instant for all: only the id orders them
    expected = sorted(item.id for item in items)

    pages = [list_items(limit=2, offset=offset) for offset in (0, 2, 4)]

    assert [row.id for page in pages for row in page.rows] == expected
    assert [(page.total, page.limit, page.offset, len(page.rows)) for page in pages] == [(5, 2, 0, 2), (5, 2, 2, 2), (5, 2, 4, 1)]


def test_search_ignores_case_and_status_filters():
    make("Table one")
    make("TABLE two", status="done")
    make("Bar")

    assert [row.name for row in list_items(search="table").rows] == ["TABLE two", "Table one"]
    assert [row.name for row in list_items(status="done").rows] == ["TABLE two"]
    page = list_items(search="table", status="open")
    assert ([row.name for row in page.rows], page.total) == (["Table one"], 1)


def test_an_employee_may_list():
    make("Table one")
    assert list_items(role="hub_employee").total == 1


def test_a_role_without_demo_may_not_list():
    with pytest.raises(PermissionDenied):
        list_items(role="nobody")


# demo.item.detail


def test_detail_with_its_lines_in_order():
    item = make("Table one", lines=0)
    second = ItemLine.objects.create(item=item, text="Tea", qty=Decimal("2.500"), position=2)
    first = ItemLine.objects.create(item=item, text="Coffee", qty=Decimal("1"), position=1, client_line_id=uuid.uuid7())

    detail = run("demo.item.detail", ByIdIn(id=item.id), "hub_employee")

    assert (detail.id, detail.name, detail.line_count) == (item.id, "Table one", 2)
    assert [(line.id, line.text, line.qty, line.position, line.client_line_id) for line in detail.lines] == [
        (first.id, "Coffee", Decimal("1.000"), 1, first.client_line_id),
        (second.id, "Tea", Decimal("2.500"), 2, None),
    ]


def test_detail_of_a_missing_item_is_not_found():
    with pytest.raises(NotFound) as excinfo:
        run("demo.item.detail", ByIdIn(id=uuid.uuid7()))
    assert (excinfo.value.status, excinfo.value.code) == (404, "not_found")


# demo.item.stats


def test_stats():
    make("A", lines=2)
    make("B", status="done", lines=1)
    make("C")
    assert run("demo.item.stats", ItemStatsIn()).model_dump() == {"total": 3, "open": 2, "done": 1, "lines": 3}


def test_empty_stats():
    assert run("demo.item.stats", ItemStatsIn()).model_dump() == {"total": 0, "open": 0, "done": 0, "lines": 0}


def test_an_employee_may_not_see_the_stats():
    with pytest.raises(PermissionDenied):
        run("demo.item.stats", ItemStatsIn(), "hub_employee")
