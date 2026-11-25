"""The time clock settings: attendance.settings.update."""

from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import operation
from live.outbox import record_event

from apps.attendance import events
from apps.attendance.models import AttendanceSettings
from apps.attendance.queries.reads import settings_values
from apps.attendance.schemas import BOTH_COORDINATES, SettingsIn, SettingsOut
from base.services.sessions import acting_hub_user

#: Settings that cannot be empty: a ``null`` leaves them as they are.
REQUIRED_SETTINGS = ("require_location", "geofence_radius_m", "auto_close_after_hours")


@operation(
    "attendance.settings.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="attendance.manage_settings",
    input=SettingsIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "ask for the location when someone clocks in from their own phone",
                "set the allowed radius to 500 metres",
                "flag forgotten days after 10 hours",
            ),
            "es": (
                "exige estar en el local para fichar desde el teléfono",
                "cambia el radio permitido a 500 metros",
                "cambia a 10 horas el aviso de jornada olvidada",
            ),
        },
        "description": "Changes the time clock settings (only the fields sent): whether a personal device "
        "must be within the workplace radius to clock in, the radius, the workplace coordinates and after "
        "how many hours a forgotten day is flagged for review.",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsIn) -> dict:
    row, created = AttendanceSettings.objects.get_or_create(slot=1)
    row = AttendanceSettings.objects.select_for_update().get(pk=row.pk)
    changed = created
    for field in data.model_fields_set:
        value = getattr(data, field)
        if value is None and field in REQUIRED_SETTINGS:
            continue
        if getattr(row, field) != value:
            setattr(row, field, value)
            changed = True
    if (row.workplace_lat is None) != (row.workplace_lng is None):
        missing = "workplace_lat" if row.workplace_lat is None else "workplace_lng"
        raise InvalidPayload(
            str(BOTH_COORDINATES), fields={missing: str(BOTH_COORDINATES)}
        )
    if changed:
        row.updated_by = acting_hub_user(ctx)
        row.save()
        record_event(ctx, events.SETTINGS_UPDATED, {})
    return settings_values(row)
