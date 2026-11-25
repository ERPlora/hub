"""The hold a reservation keeps on its table (``table.hold.by_reservation``), found while it holds it."""

import uuid

import pytest
from live.errors import NotFound

from .conftest import HUB_DB, make_hold, make_table, make_zone, run

pytestmark = [HUB_DB, pytest.mark.usefixtures("noon")]


def test_a_reservation_is_found_by_the_hold_it_keeps_on_its_table():
    """Tables knows a reservation of Reservations only by its hold: the name it paints on the table, while it holds."""
    booking, released, manual = uuid.uuid7(), uuid.uuid7(), uuid.uuid7()
    table = make_table("2", zone=make_zone("Terrace"))
    make_hold(table, source="reservation", ref=str(booking), label="Pedro")
    make_hold(table, source="reservation", ref=str(released), label="", status="released")
    make_hold(table, source="manual", ref=str(manual), label="Luis")
    held = run("table.hold.by_reservation", {"reservation_id": str(booking)})
    assert (held.label, held.table_id, held.source, held.status) == ("Pedro", table.id, "reservation", "held")
    for gone in (released, manual, uuid.uuid7()):
        with pytest.raises(NotFound) as missing:
            run("table.hold.by_reservation", {"reservation_id": str(gone)})
        assert missing.value.code == "table.hold_not_found"


def test_a_hold_whose_time_is_over_holds_nothing_even_before_the_sweep():
    booking = uuid.uuid7()
    make_hold(make_table("2"), source="reservation", ref=str(booking), label="Pedro", starts_in=-180, lasts=60)
    with pytest.raises(NotFound):
        run("table.hold.by_reservation", {"reservation_id": str(booking)})
