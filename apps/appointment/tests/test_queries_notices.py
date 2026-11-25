"""What the team is told as it happens: what customers booked and cancelled themselves."""

import datetime as dt

from django.utils import timezone

from apps.appointment.models import Appointment
from apps.appointment.queries.notices import notices
from apps.appointment.schemas.appointments import NoticesIn

from .conftest import (
    HUB_DB,
    MONDAY,
    TUESDAY,
    as_ctx,
    at,
    ctx_for,
    employee_linked_to,
    make_appointment,
    make_customer,
    run,
)

pytestmark = HUB_DB


def test_a_booking_older_than_the_window_is_told_only_when_asked_from_before_it(salon):
    booked = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), source="whatsapp")
    made = timezone.now() - dt.timedelta(hours=24, minutes=1)
    Appointment.objects.filter(pk=booked.id).update(created_at=made)
    assert notices(ctx_for(), NoticesIn()).rows == []
    since = made - dt.timedelta(minutes=1)
    assert [notice.id for notice in notices(ctx_for(), NoticesIn(since=since)).rows] == [booked.id]


# APPOINTMENT-F28 — what the hub tells the team as it happens: a booking or a
# cancellation the customer made herself (WhatsApp, the online booking), newest first, with what the notice says
# (who, which services, the day and the hour ready to say, with whom). One given or cancelled at the front desk is
# not told (who did it knows); an employee hears only her own agenda's; nothing older than the window.
def test_the_notices_are_the_customers_own_bookings_and_cancellations(salon, make_user):
    booked = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), source="whatsapp"
    )
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "11:00"))
    make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(MONDAY, "12:00"),
        status="cancelled",
        cancelled_at=timezone.now(),
    )
    cancelled = make_appointment(
        make_customer("Pepa Gil"),
        salon.bea,
        [salon.colour],
        at(TUESDAY, "16:00"),
        source="online",
        status="cancelled",
        cancelled_by_customer=True,
        cancelled_at=timezone.now() + dt.timedelta(seconds=1),
    )
    page = run("appointment.appointment.notices", language="es")
    assert [(notice.kind, notice.id) for notice in page.rows] == [
        ("cancelled", cancelled.id),
        ("booked", cancelled.id),
        ("booked", booked.id),
    ]
    first = page.rows[0]
    assert (first.number, first.customer_name, first.service_names, first.staff_name) == (
        cancelled.number,
        "Pepa Gil",
        "Colour",
        "Bea Ruiz",
    )
    assert (first.start_time_label, first.start_date_label.split(",")[0]) == ("16:00", "martes")
    assert first.at == cancelled.cancelled_at
    own = employee_linked_to(salon.ana, make_user)
    assert [notice.id for notice in as_ctx(own, "appointment.appointment.notices").rows] == [booked.id]
    later = (timezone.now() + dt.timedelta(minutes=5)).isoformat()
    assert run("appointment.appointment.notices", {"since": later}).rows == []
