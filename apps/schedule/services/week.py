"""The usual week (SCHEDULE-F02, F03): the hours of one day, and the confirmation of the week as it is saved."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.schedule import events
from apps.schedule.models import WeekDay, WeekDayInterval
from apps.schedule.queries import week_out
from apps.schedule.schemas.fields import NoParamsIn
from apps.schedule.schemas.week import SetDayIn, WeekOut

from .writes import _locked_settings, _write_intervals

NO_WEEK = _("There are no weekly opening hours to confirm.")


@operation(
    "schedule.week.set_day",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="schedule.change",
    input=SetDayIn,
    output=WeekOut,
    ai={
        "description": "Sets the opening hours of one day of the usual week (by number, 0 = Monday, or by name): "
        "closed, or its intervals (split shifts, past midnight, 00:00–00:00 for 24 hours). Replaces what the day had.",
        "risk": "normal",
        "asks": {
            "en": (
                "set the usual Saturday to 10:00 to 14:00",
                "we stay closed on Mondays from now on",
            ),
            "es": (
                "los sábados quedan de 10:00 a 14:00 desde ya",
                "los lunes no abrimos, déjalos de descanso",
                "los martes hacemos jornada partida, de 9 a 13 y de 16 a 20, y sustituye lo que había",
            ),
        },
    },
)
def set_day(ctx: OperationContext, data: SetDayIn) -> dict:
    """SCHEDULE-F02: the day's intervals are replaced, and whoever saves a day has seen the week."""
    settings = _locked_settings()
    day, _created = WeekDay.objects.select_for_update().get_or_create(
        weekday=data.weekday
    )
    day.is_closed = data.is_closed
    day.save()
    _write_intervals(WeekDayInterval, {"day": day}, data.intervals)
    if not settings.hours_confirmed:
        settings.hours_confirmed = True
        settings.save(update_fields=["hours_confirmed", "updated_at"])
    record_event(ctx, events.WEEK_UPDATED, {"weekday": data.weekday})
    return week_out()


@operation(
    "schedule.week.confirm",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="schedule.change",
    input=NoParamsIn,
    output=WeekOut,
    ai={
        "description": "Confirms the usual week as it is saved (the default one set up for the business) without "
        "changing any hour.",
        "risk": "normal",
        "asks": {
            "en": (
                "the default opening is fine, confirm it as it is",
                "confirm the default opening as it is, without changing a thing",
            ),
            "es": (
                "lo que propusiste para abrir me vale, confírmalo tal cual",
                "da por buena la apertura por defecto sin cambiar nada",
            ),
        },
    },
)
def confirm_week(ctx: OperationContext, data: NoParamsIn) -> dict:
    """SCHEDULE-F03: no hour travels; confirming twice says nothing."""
    settings = _locked_settings()
    if not WeekDay.objects.exists():
        raise Conflict(str(NO_WEEK), code="schedule.no_week")
    if not settings.hours_confirmed:
        settings.hours_confirmed = True
        settings.save(update_fields=["hours_confirmed", "updated_at"])
        record_event(ctx, events.WEEK_UPDATED, {})
    return week_out()
