"""The kitchen's stations and the rules the database itself keeps for them (the last net under a race)."""

from .conftest import HUB_DB, make_station, refused

pytestmark = HUB_DB


def test_a_new_station_goes_to_screen_and_paper_by_the_kitchen_printer():
    station = make_station("Grill")
    assert (
        station.color,
        station.destination,
        station.printer_usage,
        station.printer_name,
        station.is_active,
        station.is_deleted,
        station.sort_order,
    ) == ("#F97316", "both", "kitchen", "", True, False, 0)
    assert str(station) == "Grill"


def test_two_live_stations_never_share_a_name_whatever_the_case():
    make_station("Grill")
    assert refused(lambda: make_station("grill"))


def test_a_deleted_station_frees_its_name():
    old = make_station("Grill")
    old.is_deleted = True
    old.save()
    assert not refused(lambda: make_station("Grill"))


def test_a_station_destination_and_printer_usage_are_closed_lists():
    assert refused(lambda: make_station("A", destination="fax"))
    assert refused(lambda: make_station("B", printer_usage="receipt"))
    assert refused(lambda: make_station("C", color="orange"))
