"""The repeating appointments (APPOINTMENT-F12, F13): creating a series and booking its dates."""

import datetime as dt
from dataclasses import replace

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, PermissionDenied
from live.operations import operation
from live.outbox import record_event

from apps.appointment import assistant_cards
from apps.appointment import engine, events
from apps.appointment.models import Appointment, Recurring, RecurringService, Settings
from apps.appointment.queries import (
    ADD_OWN,
    SERIES_DEFAULT_WINDOW,
    business_zone,
    current_settings,
    find_series,
    lines_for,
    load_agenda,
    load_series,
    may_book_for,
    now,
    pattern_of,
    resolve_services,
    today,
    verdict_message,
)
from apps.appointment.schemas import MaterializeIn, MaterializeOut, RecurringCreateIn
from apps.appointment.services.writes import (
    BOOK_OWN_ONLY,
    _actor,
    _create,
    _lock_members,
    _locked_card,
    _member_for_booking,
)
from apps.service.models import Service

#: The most a series books in one run (the current product's 50).
MATERIALIZE_PER_RUN = 50
RECURRING_INACTIVE = _(
    "That repeating appointment is paused: reactivate it to book its appointments."
)
RECURRING_ENDED = _("This repeating appointment has no dates left to book.")
RECURRING_NO_STAFF = _(
    "This repeating appointment has no professional: edit it and choose who does it."
)


def _window(settings: Settings) -> tuple[dt.date, dt.date]:
    days = settings.max_advance_booking or SERIES_DEFAULT_WINDOW
    first = today()
    return first, first + dt.timedelta(days=days)


def _series_services(series: Recurring) -> list[Service]:
    return [
        line.service
        for line in series.lines.select_related("service").order_by("position", "id")
    ]


def _book_window(
    ctx: OperationContext,
    series: Recurring,
    *,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
) -> dict:
    """Books the series' dates of its window not booked yet (at most 50 a run); the report of what happened."""
    settings = current_settings()
    window_from, window_to = _window(settings)
    first = max(from_date or window_from, window_from, series.start_date)
    last = min(to_date or window_to, window_to)
    dates, upcoming = engine.dates(pattern_of(series), until=last)
    dates = [day for day in dates if day >= first]
    report = {
        "booked": 0,
        "already_booked": 0,
        "skipped": [],
        "next_from": None,
        "to": last,
        "upcoming_date": upcoming if not dates else None,
    }
    if not dates:
        return report
    member = series.staff
    services = _series_services(series)
    unavailable = any(
        not (service.is_active and service.is_bookable) for service in services
    )
    _lock_members(member)
    lines = lines_for(member, services)
    minutes = series.duration_minutes
    taken = set(
        Appointment.objects.filter(
            recurring=series, deleted_at__isnull=True
        ).values_list("occurrence_date", flat=True)
    )
    agenda = load_agenda(
        ctx, member, dates[0], dates[-1] + dt.timedelta(days=1), settings=settings
    )
    zone = business_zone()
    for index, day in enumerate(dates):
        if day in taken:
            report["already_booked"] += 1
            continue
        if report["booked"] >= MATERIALIZE_PER_RUN:
            report["next_from"] = day
            break
        code = "service_unavailable" if unavailable else None
        if code is None:
            try:
                start = engine.aware(dt.datetime.combine(day, series.time), zone)
            except engine.NonexistentTime:
                start, code = None, "invalid_start"
        if code is None:
            end = engine.ends_at(start, minutes)
            code = engine.verdict(agenda, start, end, now=now(), customer=True)
        if code:
            report["skipped"].append(
                {"occurrence_date": day, "code": code, "message": verdict_message(code)}
            )
            continue
        appointment = _create(
            ctx,
            customer=series.customer,
            member=member,
            lines=lines,
            start=start,
            minutes=minutes,
            source=Appointment.Source.COUNTER,
            recurring=series,
            occurrence=day,
            settings=settings,
        )
        agenda = replace(agenda, busy=[*agenda.busy, engine.Period(start, end, id=appointment.id)])
        report["booked"] += 1
    return report


def _bookable_series(series: Recurring) -> None:
    if not series.is_active:
        raise Conflict(str(RECURRING_INACTIVE), code="appointment.recurring_inactive")
    if series.staff is None:
        raise Conflict(str(RECURRING_NO_STAFF), code="appointment.recurring_no_staff")


def _materialize_out(series: Recurring, report: dict) -> dict:
    return {"recurring": load_series(series.id), **report}


@operation(
    "appointment.recurring.create",
    kind="command",
    permission=ADD_OWN,
    input=RecurringCreateIn,
    output=MaterializeOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "book Teresa every Tuesday at 6 pm from next week",
                "book Carmen in every other Thursday at noon",
            ),
            "es": (
                "cita fija para Teresa todos los martes a las 18:00",
                "crea una cita que se repita los jueves para Carmen",
            ),
        },
        "description": "Create a repeating appointment (every day, week, two weeks or month) for a customer, services "
        "and a professional (all by name) at a wall-clock time, from a date, optionally until a date or for a number "
        "of appointments; it books the dates of the booking window at once and lists the dates that did not fit with "
        "their reason.",
        "risk": "normal",
        "summary": assistant_cards.series,
    },
)
def create_series(ctx: OperationContext, data: RecurringCreateIn) -> dict:
    customer = _locked_card(ctx, data)
    services = resolve_services(data.services)
    member = _member_for_booking(ctx, data.staff_id, data.staff, services)
    minutes = data.duration_minutes or sum(
        line["duration_minutes"] for line in lines_for(member, services)
    )
    weekly = data.frequency in ("weekly", "biweekly")
    series = Recurring.objects.create(
        customer=customer,
        customer_name=customer.name,
        staff=member,
        staff_name=member.full_name,
        frequency=data.frequency,
        day_of_week=(
            data.day_of_week
            if data.day_of_week is not None
            else data.start_date.weekday()
        )
        if weekly
        else None,
        time=data.time.replace(second=0, microsecond=0),
        duration_minutes=minutes,
        start_date=data.start_date,
        end_date=data.end_date,
        max_occurrences=data.max_occurrences,
        created_by=_actor(ctx),
    )
    RecurringService.objects.bulk_create(
        RecurringService(recurring=series, service=service, position=position)
        for position, service in enumerate(services)
    )
    record_event(
        ctx,
        events.RECURRING_CREATED,
        {"id": str(series.id), "customer_id": str(customer.id)},
    )
    return _materialize_out(series, _book_window(ctx, series))


@operation(
    "appointment.recurring.materialize",
    kind="command",
    permission=ADD_OWN,
    input=MaterializeIn,
    output=MaterializeOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "fill in the dates still missing in Teresa's weekly appointment",
                "generate the next appointments of every repeating one",
            ),
            "es": (
                "reserva las fechas que faltan de la cita fija de Teresa",
                "rellena las próximas fechas de las citas que se repiten",
            ),
        },
        "description": "Book the dates of a repeating appointment's window not booked yet (at most 50 a run; run it "
        "again from next_from until there is none). A date that does not fit is skipped and listed with its reason; a "
        "date cancelled by hand is never booked again.",
        "risk": "normal",
    },
)
def materialize(ctx: OperationContext, data: MaterializeIn) -> dict:
    series = find_series(ctx, data.id, lock=True)
    if not may_book_for(ctx, series.staff_id):
        raise PermissionDenied(str(BOOK_OWN_ONLY))
    _bookable_series(series)
    remaining, upcoming = engine.dates(
        pattern_of(series), until=_window(current_settings())[1]
    )
    if not [day for day in remaining if day >= today()] and upcoming is None:
        raise Conflict(str(RECURRING_ENDED), code="appointment.recurring_ended")
    return _materialize_out(
        series,
        _book_window(ctx, series, from_date=data.from_date, to_date=data.to_date),
    )
