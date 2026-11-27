"""The stations and the routing (KITCHEN-F01 to F04): the stations with what each has in progress, one station,
and the routes.
"""

from collections import defaultdict
from uuid import UUID

from django.db.models import Count, Q
from live.context import OperationContext
from live.operations import INTERNAL, operation

from apps.kitchen.models import CategoryRoute, KitchenSettings, ProductRoute, Station
from apps.kitchen.queries.reads import COOKING, current_settings
from apps.kitchen.queries.routing import category_routes, product_routes
from apps.kitchen.queries.scope import ALL, find_scope, find_station
from apps.kitchen.queries.state import in_flight_views
from apps.kitchen.schemas.fields import StationRefIn
from apps.kitchen.schemas.routing import RoutingListIn, RoutingPage
from apps.kitchen.schemas.stations import StationListIn, StationOut, StationPage
from base.text_search import contains_text


def in_progress_by_station(settings: KitchenSettings) -> dict[UUID | None, int]:
    counts: dict[UUID | None, int] = defaultdict(int)
    for view in in_flight_views(settings):
        if view.status in COOKING:
            for item in view.items:
                if item.to_do:
                    counts[item.station_id] += 1
    return counts


def station_row(station: Station, in_progress: int, routes: int) -> dict:
    return {
        "id": station.id,
        "name": station.name,
        "color": station.color,
        "destination": station.destination,
        "printer_usage": station.printer_usage,
        "printer_name": station.printer_name,
        "sort_order": station.sort_order,
        "is_active": station.is_active,
        "in_progress": in_progress,
        "routes": routes,
    }


@operation(
    "kitchen.station.list",
    kind="query",
    permission="kitchen.view_ticket",
    input=StationListIn,
    output=StationPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which stations do we have?",
                "list the stations and what goes to each",
            ),
            "es": (
                "¿qué estaciones tenemos?",
                "lista las estaciones y lo que va a cada una",
            ),
        },
        "description": "List the kitchen stations (grill, bar…) with their destination, printer, dishes in "
        "progress and how many products and categories go to them, searching by name."
    },
)
def list_stations(ctx: OperationContext, params: StationListIn) -> dict:
    stations = Station.objects.filter(is_deleted=False).annotate(
        product_count=Count(
            "product_routes",
            filter=Q(product_routes__product__is_deleted=False),
            distinct=True,
        ),
        category_count=Count(
            "category_routes",
            filter=Q(category_routes__category__is_deleted=False),
            distinct=True,
        ),
    )
    if params.search:
        stations = stations.filter(contains_text(params.search, "name"))
    if params.is_active is not None:
        stations = stations.filter(is_active=params.is_active)
    counts = in_progress_by_station(current_settings())
    rows = [
        station_row(
            station,
            counts.get(station.id, 0),
            station.product_count + station.category_count,
        )
        for station in stations
    ]
    field_name = params.sort.lstrip("-")
    rows.sort(
        key=lambda row: (row[field_name], row["name"].casefold(), row["id"]),
        reverse=params.sort.startswith("-"),
    )
    return {
        "rows": rows[params.offset : params.offset + params.limit],
        "total": len(rows),
        "limit": params.limit,
        "offset": params.offset,
    }


@operation(
    "kitchen.station.get",
    kind="query",
    permission="kitchen.view_ticket",
    input=StationRefIn,
    output=StationOut,
    ai=INTERNAL,
)
def get_station(ctx: OperationContext, params: StationRefIn) -> dict:
    """One station by its id or its name, for the assistant's card (``schemas.A_STATION``): the screens and the model read
    the stations from their list, so it is no tool of the assistant nor a route of the API."""
    station = find_station(params.station_id, params.station)
    routes = (
        ProductRoute.objects.filter(station=station, product__is_deleted=False).count()
        + CategoryRoute.objects.filter(station=station, category__is_deleted=False).count()
    )
    return station_row(station, in_progress_by_station(current_settings()).get(station.id, 0), routes)


@operation(
    "kitchen.routing.list",
    kind="query",
    permission="kitchen.view_ticket",
    input=RoutingListIn,
    output=RoutingPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "where do the drinks go?", "which station gets the desserts?",
                "which products and categories go to each station?",
            ),
            "es": (
                "¿a qué estación van las bebidas?", "enséñame el enrutado de los postres",
                "¿qué productos y categorías van a cada estación?",
            ),
        },
        "description": "Which products and categories go to which station («where do the drinks go»), for every "
        "station or one, searching by the product's or category's name."
    },
)
def list_routing(ctx: OperationContext, params: RoutingListIn) -> dict:
    scope = find_scope(params.station)
    live = {"station__is_deleted": False}
    rows = [
        {
            "kind": "category",
            "target_id": route.category_id,
            "target_name": route.category.name,
            "station_id": route.station_id,
            "station_name": route.station.name,
        }
        for route in category_routes(**live).select_related(
            "category", "station"
        )
    ] + [
        {
            "kind": "product",
            "target_id": route.product_id,
            "target_name": route.product.name,
            "station_id": route.station_id,
            "station_name": route.station.name,
        }
        for route in product_routes(**live).select_related(
            "product", "station"
        )
    ]
    if scope is not ALL:
        rows = [row for row in rows if row["station_id"] == scope]
    if params.search:
        text = params.search.casefold()
        rows = [row for row in rows if text in row["target_name"].casefold()]
    rows.sort(
        key=lambda row: (row["kind"], row["target_name"].casefold(), row["target_id"])
    )
    return {
        "rows": rows[params.offset : params.offset + params.limit],
        "total": len(rows),
        "limit": params.limit,
        "offset": params.offset,
    }
