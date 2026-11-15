"""Read operations of the demo app: the paginated list, the detail and the stats."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from live.context import Scope
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import get

from apps.demo.models import Item, ItemLine
from apps.demo.schemas import ItemCountOut, ItemDetailOut, ItemListIn, ItemPage, ItemRefIn, ItemStatsIn, ItemStatsOut
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

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
        ("demo.item.detail", "demo.view", ItemRefIn, ItemDetailOut, False),
        ("demo.item.stats", "demo.manage", ItemStatsIn, ItemStatsOut, False),
        ("demo.item.open_count", "demo.view", ItemStatsIn, ItemCountOut, False),
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

    detail = run("demo.item.detail", ItemRefIn(id=item.id), "hub_employee")

    assert (detail.id, detail.name, detail.line_count) == (item.id, "Table one", 2)
    assert [(line.id, line.text, line.qty, line.position, line.client_line_id) for line in detail.lines] == [
        (first.id, "Coffee", Decimal("1.000"), 1, first.client_line_id),
        (second.id, "Tea", Decimal("2.500"), 2, None),
    ]


def test_detail_of_a_missing_item_is_not_found():
    with pytest.raises(NotFound) as excinfo:
        run("demo.item.detail", ItemRefIn(id=uuid.uuid7()))
    assert (excinfo.value.status, excinfo.value.code) == (404, "not_found")


# An item by its name (hub#1162): the same name, in any case, before one that contains it; the first that fits decides.


def named(said: str, role: str = "hub_employee"):
    return run("demo.item.detail", ItemRefIn(called=said), role)


def test_detail_by_its_name_whatever_its_case():
    item = make("Autumn trial", lines=2)
    make("Bar")
    detail = named("autumn TRIAL")
    assert (detail.id, detail.name, len(detail.lines)) == (item.id, "Autumn trial", 2)


def test_detail_by_a_part_of_its_name_when_only_one_has_it():
    item = make("Autumn trial")
    make("Bar")
    assert named("autumn").id == item.id


def test_the_same_name_comes_before_one_that_contains_it():
    trial = make("Trial", minutes_ago=5)
    make("Trial 2", minutes_ago=1)  # more recently changed, and it contains «Trial» too
    assert named("trial").id == trial.id


def test_the_id_wins_over_the_name():
    bar = make("Bar")
    make("Autumn trial")
    assert run("demo.item.detail", ItemRefIn(id=bar.id, called="Autumn trial")).id == bar.id


def test_two_items_called_the_same_are_a_conflict_that_names_them():
    """Item names are not unique: whoever asks is told which ones fit, never handed one of them."""
    make("Autumn trial")
    make("Autumn trial", status="done")
    with pytest.raises(Conflict) as excinfo:
        named("autumn trial")
    assert (excinfo.value.status, excinfo.value.code) == (409, "demo.item_ambiguous")


def test_several_that_contain_what_is_said_are_named_in_the_conflict():
    make("Trial 1")
    make("Trial 2")
    make("Bar")
    with pytest.raises(Conflict) as excinfo:
        named("trial")
    assert excinfo.value.code == "demo.item_ambiguous"
    said = str(excinfo.value)
    assert "Trial 1" in said and "Trial 2" in said and "Bar" not in said


def test_a_name_that_fits_many_items_names_the_five_changed_last():
    for number in range(1, 8):
        make(f"Trial {number}", minutes_ago=number)
    with pytest.raises(Conflict) as excinfo:
        named("trial")
    said = str(excinfo.value)
    assert [f"Trial {number}" in said for number in range(1, 8)] == [True] * 5 + [False] * 2


def test_a_name_no_item_has_is_not_found():
    make("Bar")
    with pytest.raises(NotFound) as excinfo:
        named("Autumn trial")
    assert (excinfo.value.status, excinfo.value.code) == (404, "not_found")


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_name_of_another_business_names_nothing_here(hub_a, hub_b):
    """Each business in its own database, as production: an item of A is not found by its name in B."""
    in_a = ctx_for("hub_employee", Scope("host", hub_a.slug))
    in_b = ctx_for("hub_employee", Scope("host", hub_b.slug))
    with use_hub(hub_a):
        item = Item.objects.create(name="Autumn trial")
        assert get("demo.item.detail")(in_a, ItemRefIn(called="Autumn trial")).id == item.id  # positive control
    with use_hub(hub_b):
        with pytest.raises(NotFound):
            get("demo.item.detail")(in_b, ItemRefIn(called="Autumn trial"))


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


# demo.item.open_count (the bell's example counter)


def test_the_open_items_for_the_bell():
    make("A")
    make("B", status="done")
    make("C")
    assert run("demo.item.open_count", ItemStatsIn(), "hub_employee").model_dump() == {"count": 2}


def test_no_open_item_is_a_zero():
    make("A", status="done")
    assert run("demo.item.open_count", ItemStatsIn()).model_dump() == {"count": 0}
