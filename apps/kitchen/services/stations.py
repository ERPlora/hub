"""Stations (KITCHEN-F01 to F03)."""

from django.db import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import atomic, operation
from live.outbox import record_event

from apps.kitchen import events
from apps.kitchen.models import Station
from apps.kitchen.queries.reads import current_settings
from apps.kitchen.queries.routing import category_routes, product_routes
from apps.kitchen.queries.scope import STATION_NOT_FOUND, find_station
from apps.kitchen.queries.stations import in_progress_by_station, station_row
from apps.kitchen.schemas import DeletedOut, StationIn, StationOut, StationPatchIn, StationRefIn
from apps.kitchen.services.settling import begin
from apps.kitchen.services.writes import actor, locked_row

STATION_NAME_TAKEN = _(
    "There is already a station with that name. Choose a different name."
)
STATION_IN_USE = _(
    "This station cannot be deleted: products or categories are routed to it, or it has dishes to cook. "
    "Move them to another station first."
)


def _locked_station(data: StationRefIn) -> Station:
    """The station ``data`` names, locked until the end of the write (not found if deleted since it was found)."""
    station = locked_row(Station, find_station(data.station_id, data.station).pk)
    if station is None:
        raise NotFound(str(STATION_NOT_FOUND), code="kitchen.station_not_found")
    return station


def _station_out(station: Station) -> dict:
    routes = product_routes(station=station).count() + category_routes(station=station).count()
    in_progress = in_progress_by_station(current_settings()).get(station.id, 0)
    return station_row(station, in_progress, routes)


def _name_free(name: str, but=None) -> None:
    taken = Station.objects.filter(is_deleted=False, name__iexact=name)
    if but is not None:
        taken = taken.exclude(pk=but.pk)
    if taken.exists():
        raise Conflict(str(STATION_NAME_TAKEN), code="kitchen.station_name_taken")


def _save_station(station: Station, **save) -> None:
    try:
        with atomic():
            station.save(**save)
    except IntegrityError:
        raise Conflict(
            str(STATION_NAME_TAKEN), code="kitchen.station_name_taken"
        ) from None


@operation(
    "kitchen.station.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="kitchen.manage_station",
    input=StationIn,
    output=StationOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "add a desserts station",
                "create a pastry station that prints on paper",
            ),
            "es": (
                "crea la estación Postres",
                "añade una estación de barra que imprima en papel",
            ),
        },
        "description": "Create a kitchen station (grill, bar, desserts) with its colour, whether it goes to the "
        "screen, to paper or both, and its printer (the kitchen or bar function, or a printer by its name). A new "
        "station gets nothing until products or categories are routed to it: whatever has no route goes to «No "
        "station». So after creating one, say that nothing goes to it yet and offer to route the products or "
        "categories it should get.",
        "risk": "normal",
    },
)
def create_station(ctx: OperationContext, data: StationIn) -> dict:
    _name_free(data.name)
    station = Station(**data.model_dump(), created_by=actor(ctx), updated_by=actor(ctx))
    _save_station(station)
    record_event(ctx, events.STATION_CREATED, {"station_id": str(station.id)})
    return _station_out(station)


@operation(
    "kitchen.station.update",
    kind="command",
    permission="kitchen.manage_station",
    input=StationPatchIn,
    output=StationOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "rename the grill station to Barbecue",
                "make the desserts station screen only",
            ),
            "es": (
                "deja la estación Barra solo en pantalla",
                "cambia el nombre de la estación de postres",
            ),
        },
        "description": "Change a station, named by its id or its name: its name, colour, destination, printer, "
        "position, or switch it off (new dishes then go by their category, or to no station).",
        "risk": "normal",
    },
)
def update_station(ctx: OperationContext, data: StationPatchIn) -> dict:
    # What was sent keeps the station it went to: the rounds not saved yet are saved first.
    begin(ctx)
    station = _locked_station(data)
    changes = data.model_dump(exclude_unset=True, exclude={"station_id", "station"})
    changes = {name: value for name, value in changes.items() if value is not None}
    if "name" in changes:
        _name_free(changes["name"], but=station)
    for name, value in changes.items():
        setattr(station, name, value)
    station.updated_by = actor(ctx)
    _save_station(station)
    record_event(ctx, events.STATION_UPDATED, {"station_id": str(station.id)})
    return _station_out(station)


@operation(
    "kitchen.station.delete",
    kind="command",
    permission="kitchen.manage_station",
    input=StationRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "delete the desserts station",
                "remove the old pastry station",
            ),
            "es": (
                "elimina la estación de postres",
                "borra la estación Barra, ya no la usamos",
            ),
        },
        "description": "Delete a station (it leaves the lists; the tickets already sent keep its name). Refused while "
        "products or categories are routed to it or it has dishes to cook.",
        "risk": "high",
    },
)
def delete_station(ctx: OperationContext, data: StationRefIn) -> dict:
    settings = begin(ctx)
    station = _locked_station(data)
    routed = product_routes(station=station).exists() or category_routes(station=station).exists()
    busy = in_progress_by_station(settings).get(station.id, 0) > 0
    if routed or busy:
        raise Conflict(str(STATION_IN_USE), code="kitchen.station_in_use")
    station.is_deleted, station.deleted_at = True, timezone.now()
    station.updated_by = actor(ctx)
    station.save(update_fields=["is_deleted", "deleted_at", "updated_by", "updated_at"])
    record_event(ctx, events.STATION_DELETED, {"station_id": str(station.id)})
    return {"id": station.id}
