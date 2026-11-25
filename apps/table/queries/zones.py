"""The zones of the room (``table.zone.list``, ``table.zone.get``), each with its tables in use and, of them, the free
ones right now.
"""

import datetime as dt

from django.db.models import Count, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from live.context import OperationContext
from live.operations import operation

from apps.table.models import Zone
from .floor import tables_now
from .lookups import find_zone
from .paging import _page
from apps.table.schemas import ZoneListIn, ZoneOut, ZonePage, ZoneRefIn
from base.ordering import list_order_for

ZONE_ORDER = {
    "sort_order": ("sort_order",),
    "name": ("name",),
    "color": ("color",),
    "table_count": ("table_count",),
    "available_count": ("available_count",),
    "is_active": ("is_active",),
}


def zone_rows(zones: list[Zone]) -> list[dict]:
    return [
        {
            "id": zone.id,
            "name": zone.name,
            "description": zone.description,
            "color": zone.color,
            "sort_order": zone.sort_order,
            "is_active": zone.is_active,
            "table_count": zone.table_count,
            "available_count": zone.available_count,
        }
        for zone in zones
    ]


def zones_now(now: dt.datetime):
    """The live zones with their tables in use and, of them, the free ones right now."""
    in_use = (
        tables_now(now)
        .filter(zone=OuterRef("pk"), is_active=True)
        .order_by()
        .values("zone")
    )
    count = in_use.annotate(n=Count("pk")).values("n")[:1]
    free = in_use.filter(status_now="available").annotate(n=Count("pk")).values("n")[:1]
    return Zone.objects.filter(is_deleted=False).annotate(
        table_count=Coalesce(Subquery(count, output_field=IntegerField()), 0),
        available_count=Coalesce(Subquery(free, output_field=IntegerField()), 0),
    )


@operation(
    "table.zone.list",
    kind="query",
    permission="table.view_zone",
    input=ZoneListIn,
    output=ZonePage,
    expose_api=True,
    ai={
        "description": "List the zones of the room (dining room, terrace, bar…) with their tables and how many are "
        "free.",
        "asks": {
            "en": (
                "what areas does the restaurant have?",
                "list the zones of the floor and their free tables",
            ),
            "es": (
                "¿qué zonas tiene el local?",
                "dime las zonas del restaurante y cuántas mesas libres quedan en cada una",
            ),
        },
    },
)
def list_zones(ctx: OperationContext, params: ZoneListIn) -> dict:
    zones = zones_now(timezone.now())
    for text in (params.search, params.name):
        if text and text.strip():
            zones = zones.filter(name__icontains=text.strip())
    if params.color:
        zones = zones.filter(color=params.color)
    if params.is_active is not None:
        zones = zones.filter(is_active=params.is_active)
    return _page(zones.order_by(*list_order_for(params.sort, columns=ZONE_ORDER, nulls_last=True)), params, zone_rows)


@operation(
    "table.zone.get",
    kind="query",
    permission="table.view_zone",
    input=ZoneRefIn,
    output=ZoneOut,
    expose_api=True,
    ai={
        "description": "Get one zone of the room by its id or its name, with its tables and the free ones.",
        "asks": {
            "en": (
                "how many tables are free in the terrace zone?",
                "show me the bar zone",
            ),
            "es": (
                "¿cuántas mesas libres quedan en la zona de la terraza?",
                "enséñame la zona del salón",
            ),
        },
    },
)
def get_zone(ctx: OperationContext, params: ZoneRefIn) -> dict:
    return zone_rows([find_zone(params.id, params.zone, rows=zones_now(timezone.now()))])[0]
