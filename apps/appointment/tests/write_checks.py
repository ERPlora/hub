"""What the tests of the appointment app's writes share: booking Lucía's cut with Ana, the events in the outbox,
the history of an appointment, and that a refusal leaves no trace."""

import pytest
from live.errors import Conflict
from live.models import OutboxEvent

from apps.appointment.models.appointments import Appointment, History

from .conftest import MONDAY, run, wall


def book(salon, start="10:00", day=MONDAY, **extra):
    data = {
        "customer_id": str(salon.lucia.id),
        "services": [{"service_id": str(salon.cut.id)}],
        "staff_id": str(salon.ana.id),
        "start": wall(day, start),
        **extra,
    }
    return run("appointment.appointment.create", data)


def events(name: str) -> list[dict]:
    return [
        event.payload for event in OutboxEvent.objects.filter(name=name).order_by("id")
    ]


def actions(appointment_id) -> list[str]:
    return list(
        History.objects.filter(appointment_id=appointment_id)
        .order_by("at", "id")
        .values_list("action", flat=True)
    )


def refused(code: str, call, error=Conflict):
    before = (
        Appointment.objects.count(),
        History.objects.count(),
        OutboxEvent.objects.count(),
    )
    with pytest.raises(error) as caught:
        call()
    assert caught.value.code == code
    assert (
        Appointment.objects.count(),
        History.objects.count(),
        OutboxEvent.objects.count(),
    ) == before
    return caught.value
