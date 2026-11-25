"""The tables of the room (``table.table.list``): in natural order (2 before 10), filtered by zone, status, search and
service, each named by its number with its zone.
"""

import random

import pytest
from django.utils import timezone, translation

from .conftest import HUB_DB, make_session, make_table, make_zone, run

pytestmark = [HUB_DB, pytest.mark.usefixtures("noon")]


def tables(**params) -> list[dict]:
    return [
        row.model_dump()
        for row in run("table.table.list", {"limit": 100, **params}).rows
    ]


NATURAL_ORDER = [
    ["S1", "S2", "S3", "S9", "S10", "S11", "S12"],
    ["1", "2", "3", "10", "21"],
    ["Barra 1 Bis", "Barra 2 Bis", "Barra 10 Bis"],
    ["Sala 2 Mesa 2", "Sala 2 Mesa 10", "Sala 10 Mesa 1"],
    ["Barra", "Terraza A", "Terraza B"],
    ["Barra 2 Bis", "Barra 10 Bis", "S1", "S2", "S10", "Terraza A"],
]


@pytest.mark.parametrize("expected", NATURAL_ORDER)
def test_the_tables_come_in_natural_order(expected):
    # Every run of digits is a number wherever it sits; the rest is text.
    zone = make_zone()
    for number in random.Random(7).sample(expected, len(expected)):
        make_table(number, zone=zone)
    assert [row["number"] for row in tables()] == expected
    assert [row["number"] for row in tables(sort="-number")] == expected[::-1]


def test_the_tables_filter_by_zone_status_search_and_service():
    room, terrace = make_zone("Dining room"), make_zone("Terrace", is_active=False)
    one = make_table("1", zone=room, name="Window")
    make_table("2", zone=room, blocked=True)
    make_table("3", zone=room, is_active=False)
    make_table("4", zone=terrace)
    make_table("5", zone=room, is_deleted=True, deleted_at=timezone.now())
    make_session(one)
    numbers = lambda **p: [row["number"] for row in tables(**p)]  # noqa: E731
    assert numbers() == ["1", "2", "3", "4"]
    assert numbers(zone_id=str(room.id)) == ["1", "2", "3"]
    assert numbers(zone="terrace") == ["4"]
    assert numbers(status="occupied") == ["1"]
    assert numbers(status="blocked") == ["2"]
    assert numbers(search="wind") == ["1"]
    assert numbers(in_service=True) == ["1", "2"]
    assert numbers(is_active=False) == ["3"]


def test_a_table_says_its_number_with_its_zone_in_the_language_of_whoever_reads_it():
    """The number of a table repeats across zones: its label says which one («5 (Terrace)»), as the room's lists do."""
    five, seven = make_table("5", zone=make_zone("Terrace")), make_table("7")
    assert [run("table.table.get", {"id": str(t.id)}).label for t in (five, seven)] == ["5 (Terrace)", "7 (no zone)"]
    assert sorted(row["label"] for row in tables()) == ["5 (Terrace)", "7 (no zone)"]
    with translation.override("es"):
        assert run("table.table.get", {"id": str(seven.id)}).label == "7 (sin zona)"
