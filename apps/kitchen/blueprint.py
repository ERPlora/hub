"""What of Kitchen travels in an export of the business (BASE-F35): its stations, by their name, each with the products
(by name) and the categories (by name) of Inventory routed to it, read with Kitchen's own lists and written with its own
creates. The tickets, the day's numbers and the kitchen's history never travel."""

from collections import defaultdict

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext

from base.blueprint.calls import Dataset, Loaded, attempt, call, count_of, create_each, given, ids_of, listed
from base.blueprint.calls import natural_key, pages, text_of

STATION_FIELDS = ("name", "color", "destination", "printer_usage", "printer_name", "sort_order", "is_active")
#: A route's kind and the key of a station's row that lists its targets.
ROUTED = {"product": "products", "category": "categories"}


def _station_rows(ctx: OperationContext) -> list[dict]:
    routed = defaultdict(lambda: {"products": [], "categories": []})
    for route in pages(ctx, "kitchen.routing.list"):
        routed[route.station_id][ROUTED[route.kind]].append(route.target_name)
    return [
        {name: getattr(row, name) for name in STATION_FIELDS}
        | {kind: sorted(names) for kind, names in routed[row.id].items()}
        for row in pages(ctx, "kitchen.station.list")
    ]


def _route(ctx: OperationContext, loaded: Loaded, row: dict, pk: str) -> None:
    station = text_of(row, "name")
    for kind, key in ROUTED.items():
        for name in listed(row, key, str):
            attempt(ctx, loaded, f"{station} · {name}", "kitchen.routing.set", station_id=pk, **{kind: name})


def _station_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {natural_key(row.name) for row in pages(ctx, "kitchen.station.list")}
    create_each(ctx, rows, loaded, name="kitchen.station.create", key=lambda row: natural_key(text_of(row, "name")),
                existing=existing, build=lambda row: given(row, STATION_FIELDS), label=lambda row: text_of(row, "name"),
                after=lambda row, pk: _route(ctx, loaded, row, pk))


def _station_remove(ctx: OperationContext, pk: str) -> None:
    """A station goes with what is routed to it: Kitchen refuses to delete one that still has routes."""
    for route in pages(ctx, "kitchen.routing.list", station=pk):
        call(ctx, "kitchen.routing.clear", **{f"{route.kind}_id": route.target_id})
    call(ctx, "kitchen.station.delete", station_id=pk)


DATASETS = [
    Dataset(
        key="kitchen.station",
        label=_("Stations"),
        rows=_station_rows,
        ids=ids_of("kitchen.station.list"),
        count=count_of("kitchen.station.list"),
        load=_station_load,
        remove=_station_remove,
        models=("Station", "ProductRoute", "CategoryRoute"),
    ),
]
