"""Appointments with the real Services app: the catalog, who performs each service (with their own price
and length) and archiving a service are Services', written by its own operations.
"""

import pytest
from live.errors import Conflict

from apps.appointment.models import Appointment

from .conftest import MONDAY, make_customer, make_member, make_tax, run, wall

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anytime")]


@pytest.fixture
def cast(db):
    tax = make_tax()
    run("service.service.create", {"name": "Haircut", "price": 2000, "duration_minutes": 30, "tax_category_key": tax.key})
    run("service.service.create", {"name": "Colour", "price": 4500, "duration_minutes": 60, "tax_category_key": tax.key})
    make_customer("Lucía Pérez")
    make_member("Ana", "López")
    make_member("Bea", "Ruiz")


def book(services, staff="Ana", start="10:00"):
    return run(
        "appointment.appointment.create",
        {"customer": "Lucía Pérez", "services": [{"service": name} for name in services], "staff": staff, "start": wall(MONDAY, start)},
    )


def test_who_performs_a_service_and_their_own_price_and_length_come_from_services(cast):
    run("service.assignment.assign", {"service": "Colour", "member": "Bea Ruiz", "custom_price": 5000, "custom_duration": 75})
    with pytest.raises(Conflict) as refused:
        book(["Colour"], staff="Ana")
    assert refused.value.code == "appointment.staff_not_eligible"
    out = book(["Haircut", "Colour"], staff="Bea")
    assert (out.total, out.duration_minutes) == (7000, 105)
    slots = run("appointment.availability.slots", {"date": MONDAY, "services": ["Colour"]})
    assert all(slot.staff_ids for slot in slots.slots)
    assert {staff for slot in slots.slots for staff in slot.staff_ids} == {out.staff_id}


def test_an_archived_service_is_not_booked_again_but_what_was_booked_keeps_it(cast):
    booked = book(["Haircut"])
    count = run("appointment.appointment.count_active_for_service", {"service": "Haircut"})
    assert count.count == 1
    run("service.service.archive", {"service": "Haircut"})
    with pytest.raises(Conflict) as refused:
        book(["Haircut"], start="12:00")
    assert refused.value.code == "appointment.service_not_bookable"
    kept = run("appointment.appointment.get", {"id": str(booked.id)})
    assert (kept.service_names, kept.total, kept.status) == ("Haircut", 2000, "confirmed")


def test_a_series_skips_its_dates_once_its_service_is_archived(cast):
    series = run(
        "appointment.recurring.create",
        {"customer": "Lucía Pérez", "services": [{"service": "Haircut"}], "staff": "Ana", "frequency": "weekly", "start_date": MONDAY.isoformat(), "time": "10:00", "max_occurrences": 1},
    )
    Appointment.objects.filter(recurring_id=series.recurring.id).delete()
    run("service.service.archive", {"service": "Haircut"})
    out = run("appointment.recurring.materialize", {"id": str(series.recurring.id)})
    assert (out.booked, [skip.code for skip in out.skipped]) == (0, ["service_unavailable"])
