"""What of Kitchen travels in an export of the business (BASE-F35): its stations, each with the products and the
categories of Inventory routed to it, read with Kitchen's own lists and written with its own creates. The tickets, the
day's numbers and the kitchen's history never travel.

Every test runs against the real apps (Kitchen, Inventory, Taxes), in business A's own database, as production does.
"""

import pytest

from apps.kitchen.tests.conftest import HUB_DB, in_business_a
from base.tenancy.tests.business import A
from base.tests.blueprint_round_trip import app_report, call, data_of, loaded_back, owner_of
from base.tests.blueprint_round_trip import exported as exported_apps

__all__ = ["in_business_a"]
pytestmark = HUB_DB

GRILL = {"name": "Grill", "color": "#AA3300", "destination": "both", "printer_usage": "kitchen", "printer_name": "",
         "sort_order": 1, "is_active": True}  # fmt: skip
BAR = {"name": "Bar", "color": "#0033AA", "destination": "printer", "printer_usage": "bar", "printer_name": "",
       "sort_order": 2, "is_active": True}  # fmt: skip


@pytest.fixture
def ctx():
    return owner_of(A, "olga")


def a_kitchen(ctx):
    call(ctx, "inventory.category.create", name="Drinks")
    call(ctx, "inventory.product.create", name="Ribeye", sku="RIB", price=2400, tax_category_key="restaurant.food")
    for station in (GRILL, BAR):
        call(ctx, "kitchen.station.create", **station)
    call(ctx, "kitchen.routing.set", station="Grill", product="Ribeye")
    call(ctx, "kitchen.routing.set", station="Bar", category="Drinks")


def the_kitchen(ctx) -> dict:
    stations = sorted(tuple(getattr(row, name) for name in GRILL) for row in call(ctx, "kitchen.station.list", limit=100).rows)
    routes = sorted((row.kind, row.target_name, row.station_name) for row in call(ctx, "kitchen.routing.list", limit=100).rows)
    return {"stations": stations, "routes": routes}


def test_a_backup_brings_the_stations_back_with_what_goes_to_each(ctx):
    a_kitchen(ctx)
    before = the_kitchen(ctx)
    file = exported_apps(ctx, ["kitchen"])
    for route in call(ctx, "kitchen.routing.list", limit=100).rows:
        call(ctx, "kitchen.routing.clear", **{f"{route.kind}_id": route.target_id})
    for row in call(ctx, "kitchen.station.list", limit=100).rows:
        call(ctx, "kitchen.station.delete", station_id=row.id)

    report = loaded_back(ctx, file)

    assert the_kitchen(ctx) == before
    assert [(part["created"], part["already"]) for part in app_report(report, "kitchen")["datasets"]] == [(2, 0)]


def test_loading_the_file_again_duplicates_nothing(ctx):
    a_kitchen(ctx)

    report = loaded_back(ctx, exported_apps(ctx, ["kitchen"]))

    assert [(part["created"], part["already"]) for part in app_report(report, "kitchen")["datasets"]] == [(0, 2)]


def test_only_the_stations_travel(ctx):
    a_kitchen(ctx)

    assert set(data_of(ctx, ["kitchen"])) == {"kitchen.station"}


def test_undoing_the_load_takes_away_the_stations_it_brought_with_their_routes(ctx):
    a_kitchen(ctx)
    file = exported_apps(ctx, ["kitchen"])
    for route in call(ctx, "kitchen.routing.list", limit=100).rows:
        call(ctx, "kitchen.routing.clear", **{f"{route.kind}_id": route.target_id})
    for row in call(ctx, "kitchen.station.list", limit=100).rows:
        call(ctx, "kitchen.station.delete", station_id=row.id)
    load = call(ctx, "base.blueprint.import", file_base64=file)

    call(ctx, "base.import.undo", id=load.id)

    assert the_kitchen(ctx) == {"stations": [], "routes": []}
