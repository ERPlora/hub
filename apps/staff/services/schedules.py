"""A person's weekly schedules: add one, edit it, switch it on or off and delete it (STAFF-F13 to F15)."""

from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.staff import events, schedule_card
from apps.staff.models import Schedule, ScheduleDay
from apps.staff.queries.reads import resolve_member
from apps.staff.queries.schedules import SCHEDULE_NOT_FOUND, load_schedule
from apps.staff.queries.settings import saved_settings
from apps.staff.schemas.fields import DeletedOut
from apps.staff.schemas.schedules import (
    SCHEDULE_RANGE,
    DayIn,
    ScheduleIn,
    ScheduleOut,
    ScheduleRefIn,
    ScheduleUpdateIn,
    SetActiveIn,
)
from apps.staff.workday import with_working_days, workday_of

from .locks import _locked_live_member

DEFAULT_SCHEDULE_NAME = _("Regular schedule")


@operation(
    "staff.schedule.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.manage_settings",
    input=ScheduleIn,
    output=ScheduleOut,
    ai={
        "asks": {
            "en": (
                "create a schedule for Lucía from Monday to Friday, 10 to 18",
                "give Pablo a weekend schedule",
                "new summer schedule for Ana with a break at 14:00",
            ),
            "es": (
                "crea un horario para Lucía de lunes a viernes de 10 a 18",
                "crea a Pablo un horario de fin de semana",
                "horario nuevo de verano para Ana con descanso a las 14:00",
            ),
        },
        "description": "Creates a weekly work schedule for a staff member (by id or by name), with the "
        "hours and break of each working day.",
        "risk": "normal",
        "summary": schedule_card.created,
    },
)
def create_schedule(ctx: OperationContext, data: ScheduleIn) -> Schedule | None:
    """STAFF-F13: a new default schedule demotes the member's others in the same transaction."""
    week = _week(data.days)
    member = resolve_member(data.member_id, data.member, lock=True)
    if data.is_default:
        member.schedules.filter(is_default=True).update(is_default=False)
    schedule = Schedule.objects.create(
        member=member,
        name=data.name or str(DEFAULT_SCHEDULE_NAME),
        is_default=data.is_default,
        effective_from=data.effective_from,
        effective_until=data.effective_until,
    )
    _write_week(schedule, week)
    record_event(
        ctx,
        events.SCHEDULE_CREATED,
        {"id": str(schedule.id), "member_id": str(member.id)},
    )
    return load_schedule(schedule.id)


@operation(
    "staff.schedule.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.manage_settings",
    input=ScheduleUpdateIn,
    output=ScheduleOut,
    ai={
        "asks": {
            "en": (
                "change Lucía's schedule so she starts at 9 on Mondays",
                "Pablo's schedule: Saturdays off from now on",
                "edit Ana's schedule to end at 20:00",
            ),
            "es": (
                "actualiza el horario de Lucía: los lunes empieza a las 9",
                "en el horario de Pablo, los sábados libres a partir de ahora",
                "edita el horario de Ana para que acabe a las 20:00",
            ),
        },
        "description": "Edits a work schedule (name, validity, default) and replaces its whole week of "
        "working hours.",
        "risk": "normal",
        "summary": schedule_card.updated,
    },
)
def update_schedule(ctx: OperationContext, data: ScheduleUpdateIn) -> Schedule | None:
    """STAFF-F14: what is not sent is kept, ``null`` clears a date, and the week is replaced."""
    week = _week(data.days)
    schedule = _locked_schedule(data.id)
    sent = data.model_dump(exclude_unset=True, exclude={"id", "days"})
    if "name" in sent:
        sent["name"] = sent["name"] or str(DEFAULT_SCHEDULE_NAME)
    if sent.get("is_default") is None:
        sent.pop("is_default", None)
    for field, value in sent.items():
        setattr(schedule, field, value)
    if (
        schedule.effective_from
        and schedule.effective_until
        and schedule.effective_until < schedule.effective_from
    ):
        raise InvalidPayload(
            str(SCHEDULE_RANGE), fields={"effective_until": str(SCHEDULE_RANGE)}
        )
    if schedule.is_default:
        Schedule.objects.filter(member_id=schedule.member_id, is_default=True).exclude(
            pk=schedule.pk
        ).update(is_default=False)
    schedule.save()
    schedule.days.all().delete()
    _write_week(schedule, week)
    record_event(
        ctx,
        events.SCHEDULE_UPDATED,
        {"id": str(schedule.id), "member_id": str(schedule.member_id)},
    )
    return load_schedule(schedule.id)


@operation(
    "staff.schedule.set_active",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.manage_settings",
    input=SetActiveIn,
    output=ScheduleOut,
    ai={
        "asks": {
            "en": (
                "deactivate Lucía's summer schedule for now",
                "turn Pablo's winter schedule back on",
                "pause Ana's schedule without deleting it",
            ),
            "es": (
                "desactiva de momento el horario de verano de Lucía",
                "vuelve a activar el horario de invierno de Pablo",
                "pausa el horario de Ana sin borrarlo",
            ),
        },
        "description": "Activates or deactivates a work schedule; an inactive schedule never governs "
        "availability.",
        "risk": "normal",
    },
)
def set_schedule_active(ctx: OperationContext, data: SetActiveIn) -> Schedule | None:
    """STAFF-F15; no change, no event."""
    schedule = _locked_schedule(data.id)
    if schedule.is_active != data.is_active:
        schedule.is_active = data.is_active
        schedule.save(update_fields=["is_active", "updated_at"])
        record_event(
            ctx,
            events.SCHEDULE_UPDATED,
            {"id": str(schedule.id), "member_id": str(schedule.member_id)},
        )
    return load_schedule(schedule.id)


@operation(
    "staff.schedule.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.manage_settings",
    input=ScheduleRefIn,
    output=DeletedOut,
    ai={
        "asks": {
            "en": (
                "delete Lucía's summer schedule",
                "remove Pablo's old schedule",
                "get rid of Ana's weekend schedule",
            ),
            "es": (
                "borra el horario de verano de Lucía",
                "elimina el horario antiguo de Pablo",
                "quita el horario de fin de semana de Ana",
            ),
        },
        "description": "Deletes a work schedule and its working hours; they stop counting for availability.",
        "risk": "high",
    },
)
def delete_schedule(ctx: OperationContext, data: ScheduleRefIn) -> dict:
    """STAFF-F15: deleting the default one does not make another one the default."""
    schedule = _locked_schedule(data.id)
    member_id = schedule.member_id
    schedule.delete()
    record_event(
        ctx, events.SCHEDULE_DELETED, {"id": str(data.id), "member_id": str(member_id)}
    )
    return {"id": data.id}


def _locked_schedule(schedule_id: UUID) -> Schedule:
    """The schedule with its member's row and its own row locked (the default flag is per member).

    The member is locked first and must still be live once locked: one terminated meanwhile (its
    termination held the lock) is ``NotFound``, never a write on a record that is gone.
    """
    member_id = Schedule.objects.filter(pk=schedule_id).values_list("member_id", flat=True).first()
    if member_id is None or _locked_live_member(member_id) is None:
        raise NotFound(str(SCHEDULE_NOT_FOUND))
    schedule = Schedule.objects.select_for_update().filter(pk=schedule_id).first()
    if schedule is None:
        raise NotFound(str(SCHEDULE_NOT_FOUND))
    return schedule


def _week(days: list[DayIn]) -> list[DayIn]:
    """The hours a day does not say are the business's default working day, as the window proposes them (STAFF-F22)."""
    return with_working_days(days, workday_of(saved_settings()))


def _write_week(schedule: Schedule, days: list[DayIn]) -> None:
    """Only the working days are stored: a weekday missing is a day off."""
    ScheduleDay.objects.bulk_create(
        ScheduleDay(
            schedule=schedule,
            weekday=day.weekday,
            start_time=day.start_time,
            end_time=day.end_time,
            break_start=day.break_start,
            break_end=day.break_end,
        )
        for day in days
        if day.is_working
    )
