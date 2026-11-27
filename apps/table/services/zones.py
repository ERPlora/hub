"""The zones of the room (TABLE-F01, F06)."""

from django.db import IntegrityError
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import atomic, operation
from live.outbox import record_event

from apps.table import events
from apps.table.models import Table, Zone
from apps.table.queries.lookups import find_zone
from apps.table.queries.zones import zone_rows, zones_now
from apps.table.schemas.fields import DeletedOut
from apps.table.schemas.zones import ZoneIn, ZoneOut, ZonePatchIn, ZoneRefIn
from apps.table.services.writes import _stamp

ZONE_NAME_TAKEN = _("There is already a zone with that name.")
ZONE_HAS_TABLES = _(
    "That zone still has tables. Move them to another zone or delete them first."
)


def _zone_name_taken(name: str, *, except_id=None) -> bool:
    rows = Zone.objects.filter(is_deleted=False, name__iexact=name.strip())
    return rows.exclude(pk=except_id).exists() if except_id else rows.exists()


def _save_zone(zone: Zone) -> None:
    """Saves a zone; the database's unique name is the net under two writes at once (a 409, never a 500)."""
    try:
        with atomic():
            zone.save()
    except IntegrityError:
        raise Conflict(str(ZONE_NAME_TAKEN), code="table.zone_name_taken") from None


def _zone_out(zone: Zone) -> dict:
    return zone_rows([zones_now(timezone.now()).get(pk=zone.pk)])[0]


@operation(
    "table.zone.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.add_zone",
    input=ZoneIn,
    output=ZoneOut,
    expose_api=True,
    ai={
        "description": "Create a zone of the room (dining room, terrace, bar…); it goes last unless told its order.",
        "risk": "normal",
        "asks": {
            "en": (
                "add a terrace zone",
                "create a new area called Upstairs",
            ),
            "es": (
                "crea la zona Terraza",
                "añade una zona nueva para el salón de arriba",
            ),
        },
    },
)
def create_zone(ctx: OperationContext, data: ZoneIn) -> dict:
    if _zone_name_taken(data.name):
        raise Conflict(str(ZONE_NAME_TAKEN), code="table.zone_name_taken")
    order = data.sort_order
    if order is None:
        last = Zone.objects.filter(is_deleted=False).aggregate(last=Max("sort_order"))[
            "last"
        ]
        order = 0 if last is None else last + 1
    zone = Zone(
        name=data.name, description=data.description, color=data.color, sort_order=order
    )
    _stamp(zone, ctx, created=True)
    _save_zone(zone)
    record_event(ctx, events.ZONE_CREATED, {"id": str(zone.pk)})
    return _zone_out(zone)


@operation(
    "table.zone.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.change_zone",
    input=ZonePatchIn,
    output=ZoneOut,
    expose_api=True,
    ai={
        "description": "Rename a zone or change its description, colour, order or whether it is in service (an "
        "inactive zone leaves the service view). Only what is sent changes.",
        "risk": "normal",
        "asks": {
            "en": (
                "rename the terrace zone to Patio",
                "make the bar zone blue",
                "take the terrace out of service, it's raining",
            ),
            "es": (
                "cambia el nombre de la zona Terraza a Patio",
                "pon la zona de la barra en azul",
                "modifica la zona de la terraza, hoy no la usamos",
            ),
        },
    },
)
def update_zone(ctx: OperationContext, data: ZonePatchIn) -> dict:
    zone = find_zone(data.id, data.zone, lock=True)
    if data.name is not None and _zone_name_taken(data.name, except_id=zone.pk):
        raise Conflict(str(ZONE_NAME_TAKEN), code="table.zone_name_taken")
    for field in ("name", "description", "color", "sort_order", "is_active"):
        value = getattr(data, field)
        if value is not None:
            setattr(zone, field, value)
    _stamp(zone, ctx)
    _save_zone(zone)
    record_event(ctx, events.ZONE_UPDATED, {"id": str(zone.pk)})
    return _zone_out(zone)


@operation(
    "table.zone.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.delete_zone",
    input=ZoneRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete an empty zone (a zone with tables is refused: move or delete them first).",
        "risk": "high",
        "asks": {
            "en": (
                "delete the patio zone, it's empty",
                "remove the upstairs area",
            ),
            "es": (
                "borra la zona Patio, ya no tiene mesas",
                "elimina la zona de arriba",
            ),
        },
    },
)
def delete_zone(ctx: OperationContext, data: ZoneRefIn) -> dict:
    zone = find_zone(data.id, data.zone, lock=True)
    if Table.objects.filter(zone=zone, is_deleted=False).exists():
        raise Conflict(str(ZONE_HAS_TABLES), code="table.zone_has_tables")
    zone.is_deleted, zone.is_active, zone.deleted_at = True, False, timezone.now()
    _stamp(zone, ctx)
    zone.save()
    record_event(ctx, events.ZONE_DELETED, {"id": str(zone.pk)})
    return {"id": zone.pk}
