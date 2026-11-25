"""Whether the floor plan is set up (``table.floor.status``): one table in use sets it up, and occupancy never unsets it."""

import pytest

from .conftest import HUB_DB, make_session, make_table, make_zone, run

pytestmark = [HUB_DB, pytest.mark.usefixtures("noon")]


def test_one_table_in_use_sets_the_floor_up_and_occupancy_never_unsets_it():
    # setup_status.postgres: always one answer; occupancy never unconfigures the floor.
    assert run("table.floor.status", {}).model_dump() == {
        "usable_tables": 0,
        "zones": 0,
    }
    zone = make_zone()
    make_table("1", zone=zone, is_active=False)
    assert run("table.floor.status", {}).usable_tables == 0
    table = make_table("2", zone=zone)
    make_session(table)
    assert run("table.floor.status", {}).model_dump() == {
        "usable_tables": 1,
        "zones": 1,
    }
