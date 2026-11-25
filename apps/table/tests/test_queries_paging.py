"""The pages of the room's lists: a descending list is the ascending one read backwards, ties included, and its pages
neither repeat nor lose rows.
"""

import pytest

from base.tests.ordering import assert_reads_backwards, listed_with

from .conftest import HUB_DB, make_session, make_table, make_zone, run

pytestmark = [HUB_DB, pytest.mark.usefixtures("noon")]


def _tied_zones():
    return [make_zone(f"Zone {n}", color="primary").id for n in range(4)]


def _tied_tables():
    return [make_table(str(n), capacity=2).id for n in range(4)]


def _tied_table_sessions():
    return [make_session(make_table(str(n)), guests_count=2).id for n in range(4)]


@pytest.mark.parametrize(
    ("operation", "tied", "column"),
    [
        ("table.zone.list", _tied_zones, "color"),
        ("table.table.list", _tied_tables, "capacity"),
        ("table.session.list", _tied_table_sessions, "guests_count"),
    ],
)
def test_ties_go_by_id_in_the_lists_own_direction(operation, tied, column):
    """hub#768: a descending list is the ascending one read backwards, ties included, and its
    pages neither repeat nor lose rows."""
    assert_reads_backwards(listed_with(run, operation, column), sorted(tied()))
