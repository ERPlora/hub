"""The agenda on the clock of the business, not the deployment's (hub#687): a business in the Canaries reads the same
hour in the agenda, on the assistant's card, in the question of «Ask someone first» and in a WhatsApp."""

import datetime as dt

import pytest
from live.operations import get

from apps.flow.queries import words_for
from base import assistant

from .conftest import A, HUB_DB, make_appointment, pin_clock, run

pytestmark = [HUB_DB, pytest.mark.usefixtures("in_canary")]

CANARY = "Atlantic/Canary"
#: 10:00 on the deployment's clock, 9:00 on the Canaries'.
SENT = "2026-11-02T10:00:00+01:00"


@pytest.fixture
def in_canary(monkeypatch, in_business_a):
    """Business A in the Canaries, an hour behind the deployment's clock."""
    monkeypatch.setattr(in_business_a, "timezone", CANARY)


def test_the_agenda_the_card_the_question_and_the_whatsapp_say_the_same_hour(salon):
    booked = make_appointment(salon.lucia, salon.ana, [salon.cut], dt.datetime.fromisoformat(SENT))
    agenda = run("appointment.appointment.get", {"id": str(booked.id)}, language="es")
    card = assistant.card(get("appointment.appointment.create"), {"start": SENT}, "es", ctx=None)
    words = words_for([], "es", A)("input.start", SENT)
    said = {field["name"]: field["value"] for field in card["fields"]}["start"]
    assert (agenda.start_time_label, agenda.start.isoformat()[:16]) == ("09:00", "2026-11-02T09:00")
    assert said == words == "2 nov 2026, 9:00"


def test_the_settings_say_the_businesss_zone():
    assert run("appointment.settings.get").timezone == CANARY


def test_a_time_typed_on_the_wall_is_booked_at_the_businesss_hour(salon, anytime, monkeypatch):
    pin_clock(monkeypatch, dt.datetime(2026, 10, 30, 12, 0, tzinfo=dt.UTC))
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
