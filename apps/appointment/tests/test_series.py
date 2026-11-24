"""The repeating appointments: their list, one with its next date, and the one a write answers back."""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import NotFound

from apps.appointment.queries.series import load_series

from .conftest import HUB_DB, MONDAY, as_ctx, at, employee_linked_to, make_appointment, make_series, run

pytestmark = HUB_DB


def test_the_series_a_write_answers_back_carries_its_services(salon):
    said = load_series(make_series(salon).id)
    assert (said["services"], said["service_names"]) == (
        [{"service_id": salon.cut.id, "name": "Haircut"}],
        "Haircut",
    )


def test_the_series_list_searches_and_filters(salon):
    weekly = make_series(salon)
    paused = make_series(salon, frequency="monthly", day_of_week=None, is_active=False)
    page = run("appointment.recurring.list", {"search": "haircut"})
    assert {r.id for r in page.rows} == {weekly.id, paused.id}
    assert [
        r.id for r in run("appointment.recurring.list", {"is_active": False}).rows
    ] == [paused.id]
    row = run("appointment.recurring.list", {"frequency": "weekly"}).rows[0]
    assert (row.service_names, row.day_of_week, row.time) == ("Haircut", 0, dt.time(10))


def test_a_series_says_its_next_date_and_how_many_booked_appointments_an_edit_reaches(
    salon,
):
    series = make_series(salon)
    for weeks, sale in (
        (0, None),
        (1, None),
        (2, "00000000-0000-7000-8000-000000000001"),
    ):
        day = MONDAY + dt.timedelta(weeks=weeks)
        make_appointment(
            salon.lucia,
            salon.ana,
            [salon.cut],
            at(day, "10:00"),
            recurring=series,
            occurrence_date=day,
            sale_id=sale,
        )
    detail = run(
        "appointment.recurring.get",
        {"id": str(series.id), "from_date": MONDAY + dt.timedelta(weeks=1)},
    )
    assert (detail.next_date, detail.upcoming, detail.charged) == (MONDAY, 2, 1)


def test_an_employee_reads_their_own_series_but_not_a_colleagues_nor_a_deleted_one(
    salon, make_user
):
    own = make_series(salon, staff=salon.bea)
    theirs = make_series(salon)
    gone = make_series(salon, staff=salon.bea)
    gone.deleted_at = timezone.now()
    gone.save()
    ctx = employee_linked_to(salon.bea, make_user)
    detail = as_ctx(ctx, "appointment.recurring.get", {"id": str(own.id)})
    assert (detail.id, detail.staff_id, detail.service_names) == (
        own.id,
        salon.bea.id,
        "Haircut",
    )
    for hidden in (theirs, gone):
        with pytest.raises(NotFound) as missing:
            as_ctx(ctx, "appointment.recurring.get", {"id": str(hidden.id)})
        assert missing.value.code == "appointment.recurring_not_found"
