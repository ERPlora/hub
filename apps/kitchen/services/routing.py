"""Routing (KITCHEN-F04): which station cooks a product or a category."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.inventory.models import Category, Product
from apps.inventory.queries.reads import held
from apps.kitchen import events
from apps.kitchen.models import CategoryRoute, ProductRoute, Station
from apps.kitchen.queries.scope import find_station
from apps.kitchen.schemas.routing import RouteOut, RoutingClearIn, RoutingSetIn
from apps.kitchen.services.catalog import CATEGORY_NOT_FOUND, PRODUCT_NOT_FOUND, find_category, find_product
from apps.kitchen.services.settling import begin
from apps.kitchen.services.writes import actor

STATION_INACTIVE = _(
    "That station is switched off: switch it on or choose another one."
)
ROUTE_NOT_FOUND = _("Nothing is routed from that product or category.")


def _held(model, row, missing, code: str):
    """``row`` read again, live and held until this write commits (``held``): Inventory's «Delete» or the
    Hub admin's waits for the write, and one deleted since it was found is not found, as one deleted
    before."""
    live = held(model.objects.filter(pk=row.pk, is_deleted=False))
    if not live:
        raise NotFound(str(missing), code=f"kitchen.{code}_not_found")
    return live[0]


def _target(data) -> tuple[Product | None, Category | None]:
    if data.product_id is not None or data.product:
        return find_product(data.product_id, data.product), None
    return None, find_category(data.category_id, data.category)


def _route_of(product: Product | None, category: Category | None):
    """The route of ``product`` or of ``category`` (or none), locked."""
    routes = (
        ProductRoute.objects.filter(product=product)
        if product
        else CategoryRoute.objects.filter(category=category)
    )
    return routes.select_for_update(of=("self",)).select_related("station").first()


def _route_out(
    product: Product | None, category: Category | None, station: Station
) -> dict:
    target = product or category
    return {
        "kind": "product" if product else "category",
        "target_id": target.id,
        "target_name": target.name,
        "station_id": station.id,
        "station_name": station.name,
    }


def _route_event(ctx: OperationContext, station: Station, product, category) -> None:
    record_event(
        ctx,
        events.ROUTING_CHANGED,
        {
            "station_id": str(station.id),
            "product_id": str(product.id) if product else None,
            "category_id": str(category.id) if category else None,
        },
    )


@operation(
    "kitchen.routing.set",
    kind="command",
    permission="kitchen.manage_station",
    input=RoutingSetIn,
    output=RouteOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "drinks go to the grill station",
                "send the desserts to the pastry station from now on",
            ),
            "es": (
                "que las bebidas vayan a la estación Barra",
                "enruta los postres a la estación Postres",
            ),
        },
        "description": "Send a product or a category of the catalogue to a station («drinks go to the bar»), "
        "replacing where it went before. Only the rounds sent from now on follow it.",
        "risk": "normal",
    },
)
def set_route(ctx: OperationContext, data: RoutingSetIn) -> dict:
    # Only the rounds sent from now on follow it: the ones not saved yet are saved first.
    begin(ctx)
    station = find_station(data.station_id, data.station)
    if not station.is_active:
        raise Conflict(str(STATION_INACTIVE), code="kitchen.station_inactive")
    product, category = _target(data)
    # The route it replaces is locked before its product or category is held: the Hub admin's «Delete» of a
    # product or a category takes its route first and the row last, so neither waits for the other in a circle.
    _route_of(product, category)
    if product is not None:
        product = _held(Product, product, PRODUCT_NOT_FOUND, "product")
    else:
        category = _held(Category, category, CATEGORY_NOT_FOUND, "category")
    who = actor(ctx)
    if product is not None:
        ProductRoute.objects.update_or_create(
            product=product, defaults={"station": station, "updated_by": who}
        )
    else:
        CategoryRoute.objects.update_or_create(
            category=category, defaults={"station": station, "updated_by": who}
        )
    _route_event(ctx, station, product, category)
    return _route_out(product, category, station)


@operation(
    "kitchen.routing.clear",
    kind="command",
    permission="kitchen.manage_station",
    input=RoutingClearIn,
    output=RouteOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "stop sending the coffee to the grill station",
                "remove the routing of the desserts",
                "delete the rule that sends the salads to the cold station",
            ),
            "es": (
                "quita el enrutado de los postres",
                "quita el enrutado del café, que vaya con su familia",
                "borra la regla que manda las ensaladas a la estación de fríos",
            ),
        },
        "description": "Take away where a product or a category goes: from now on it goes by its category, or to no "
        "station.",
        "risk": "normal",
    },
)
def clear_route(ctx: OperationContext, data: RoutingClearIn) -> dict:
    begin(ctx)
    product, category = _target(data)
    # Locked, not held: taking a route away names nothing, and the Hub admin's «Delete» of its product or
    # category (which takes the route first) waits for it, or took it already and it is not found.
    route = _route_of(product, category)
    if route is None:
        raise NotFound(str(ROUTE_NOT_FOUND), code="kitchen.route_not_found")
    station = route.station
    route.delete()
    _route_event(ctx, station, product, category)
    return _route_out(product, category, station)
