"""The zones of the room (``table.zone.list``, ``table.zone.get``): each with its tables in use and, of them, the free
ones right now; searched, filtered, sorted and paged.
"""

import pytest
from django.utils import timezone

from .conftest import HUB_DB, make_session, make_table, make_zone, run

pytestmark = [HUB_DB, pytest.mark.usefixtures("noon")]


def test_the_zones_come_in_their_order_with_their_tables_and_the_free_ones():
    room = make_zone("Dining room", sort_order=1)
    terrace = make_zone("Terrace", sort_order=0)
    make_zone("Old", is_deleted=True, deleted_at=timezone.now())
    one, two = make_table("1", zone=room), make_table("2", zone=room)
    make_table("3", zone=room, is_active=False)
    make_table("4", zone=room, is_deleted=True, deleted_at=timezone.now())
    make_session(one)
    make_table("5", zone=room, blocked=True)
    del two

    rows = run("table.zone.list", {}).model_dump()["rows"]
    assert [(r["name"], r["table_count"], r["available_count"]) for r in rows] == [
        ("Terrace", 0, 0),
        ("Dining room", 3, 1),
    ]
    assert terrace.id == rows[0]["id"]


def test_the_zones_search_filter_sort_and_page():
    for index, name in enumerate(["Bar", "Terrace", "Garden", "Rooftop"]):
        make_zone(name, sort_order=index, is_active=name != "Garden")
    names = lambda **p: [r.name for r in run("table.zone.list", p).rows]  # noqa: E731
    assert names(search="ter") == ["Terrace"]
    assert names(is_active=False) == ["Garden"]
    assert names(sort="-name") == ["Terrace", "Rooftop", "Garden", "Bar"]
    page = run("table.zone.list", {"limit": 2, "offset": 2})
    assert (page.total, [r.name for r in page.rows]) == (4, ["Garden", "Rooftop"])
