"""The agenda on the clock of the business, not the deployment's (hub#687): a business in the Canaries reads the same
hour in the agenda, on the assistant's card, in the question of «Ask someone first» and in a WhatsApp."""

import datetime as dt

import pytest
from live.operations import get

from apps.flow.queries import words_for
from base import assistant
from base.models import Hub
from base.tenancy.context import use_hub

from .conftest import A, make_appointment, pin_clock, run

pytestmark = pytest.mark.django_db

CANARY = "Atlantic/Canary"
#: 10:00 on the deployment's clock, 9:00 on the Canaries'.
SENT = "2026-11-02T10:00:00+01:00"


def in_canary():
    return use_hub(Hub(slug="a", timezone=CANARY))


def test_the_agenda_the_card_the_question_and_the_whatsapp_say_the_same_hour(salon):
    booked = make_appointment(salon.lucia, salon.ana, [salon.cut], dt.datetime.fromisoformat(SENT))
    with in_canary():
        agenda = run("appointment.appointment.get", {"id": str(booked.id)}, language="es")
        card = assistant.card(get("appointment.appointment.create"), {"start": SENT}, "es", ctx=None)
        words = words_for([], "es", A)("input.start", SENT)
    said = {field["name"]: field["value"] for field in card["fields"]}["start"]
    assert (agenda.start_time_label, agenda.start.isoformat()[:16]) == ("09:00", "2026-11-02T09:00")
    assert said == words == "2 nov 2026, 9:00"


def test_the_settings_say_the_businesss_zone():
    with in_canary():
        assert run("appointment.settings.get").timezone == CANARY


def test_a_time_typed_on_the_wall_is_booked_at_the_businesss_hour(salon, anytime, monkeypatch):
    pin_clock(monkeypatch, dt.datetime(2026, 10, 30, 12, 0, tzinfo=dt.UTC))
    with in_canary():
        booked = run(
            "appointment.appointment.create",
            {
                "customer_id": str(salon.lucia.id),
                "services": [{"service_id": str(salon.cut.id)}],
                "staff_id": str(salon.ana.id),
                "start": "2026-11-02T16:05",
            },
        )
    assert booked.start.astimezone(dt.UTC) == dt.datetime(2026, 11, 2, 16, 5, tzinfo=dt.UTC)
