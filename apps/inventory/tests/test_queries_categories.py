"""How ``inventory.category.list`` orders the categories by the position the business gives them (the till's strip)."""

from live.operations import get

from apps.inventory.models import Category
from apps.inventory.schemas.categories import CategoryListIn
from base.tests.ordering import assert_reads_backwards, listed_with

from .conftest import HUB_DB, ctx_for

pytestmark = HUB_DB


def run(name, data, role="hub_employee"):
    return get(name)(ctx_for(role), data)


def _menu():
    """A restaurant's menu in the order it is served, which is not the alphabetical one, with a tie at 2 and two
    categories nobody placed (0)."""
    for name, order in (
        ("Starters", 4),
        ("Mains", 5),
        ("Desserts", 6),
        ("Drinks", 1),
        ("Wine and beer", 2),
        ("Beer on tap", 2),
        ("Coffees", 3),
        ("Specials", 0),
        ("Bakery", 0),
    ):
        Category.objects.create(name=name, order=order)


def test_by_position_the_list_follows_the_order_the_business_gave_ties_by_name():
    _menu()

    page = run("inventory.category.list", CategoryListIn(sort="order"))

    assert [row.name for row in page.rows] == [
        "Bakery",
        "Specials",
        "Drinks",
        "Beer on tap",
        "Wine and beer",
        "Coffees",
        "Starters",
        "Mains",
        "Desserts",
    ]


def test_by_position_descending_reads_the_same_list_backwards():
    _menu()
    ascending = [row.id for row in run("inventory.category.list", CategoryListIn(sort="order")).rows]

    assert_reads_backwards(listed_with(run, "inventory.category.list", "order", schema=CategoryListIn), ascending)
