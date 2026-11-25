"""The default working day a new schedule proposes (STAFF-F22)."""

from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import operation
from live.outbox import record_event

from apps.staff import events
from apps.staff.models import StaffSettings
from apps.staff.queries.settings import settings_out
from apps.staff.schemas.settings import SettingsIn, SettingsOut


@operation(
    "staff.settings.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.manage_settings",
    input=SettingsIn,
    output=SettingsOut,
    ai={
        "asks": {
            "en": (
                "change the default start and end of new schedules to 9 and 17",
                "set the default break of new schedules to 45 minutes",
                "change the default working day to 10 to 19",
            ),
            "es": (
                "que los horarios nuevos empiecen a las 9 y acaben a las 17",
                "cambia el descanso por defecto de los horarios nuevos a 45 minutos",
                "cambia la jornada por defecto a de 10 a 19",
            ),
        },
        "description": "Changes the default working day that a new schedule proposes (start, end and "
        "break); only what is sent.",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsIn) -> dict:
    """STAFF-F22: the first save creates the row; hours are stored without seconds. The resulting day
    must be a schedule's day: a problem goes under the field that caused it (a start sent alone that
    falls after the saved end, under the start)."""
    row = StaffSettings.objects.select_for_update().first()
    created = False
    if row is None:
        row, created = StaffSettings.objects.get_or_create(slot=1)
    sent = data.model_dump(exclude_unset=True, exclude_none=True)
    for field in ("default_work_start", "default_work_end"):
        if field in sent:
            sent[field] = sent[field].replace(second=0, microsecond=0)
    changes = {field: value for field, value in sent.items() if getattr(row, field) != value}
    if changes:
        for field, value in changes.items():
            setattr(row, field, value)
        problems = row.workday_errors()
        if "default_work_end" in problems and "default_work_end" not in sent:
            problems = {"default_work_start": problems["default_work_end"]}
        if problems:
            raise InvalidPayload(next(iter(problems.values())), fields=problems)
        row.save()
    if changes or created:
        record_event(ctx, events.SETTINGS_UPDATED, {})
    return settings_out(row)
