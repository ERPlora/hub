"""The assistant's cards of Appointments (APPOINTMENT-F01, F12, F14, F16): whom, when — a start and its end, or when a
series repeats, as one datum — and with what, first. A normal card's line shows only its first three
data, in the form's order: «Crear en Citas: Sofía Prieto QA · Corte de mujer · Ana» had no day nor hour, a blocked time
no end nor whose, a series no hour, service nor professional, and a series moved to Carlos did not say so
(hub#2347)."""

import json
import uuid

from live.operations import get

from base import assistant

from .conftest import HUB_DB, ctx_for

pytestmark = HUB_DB

HAIRCUT = [{"service": "Corte de mujer"}]


def fields_of(write: str, arguments: dict, language: str = "es") -> list[dict]:
    return assistant.cards.card(get(write), arguments, language, ctx_for(language=language))["fields"]


def its_line(fields: list[dict]) -> list[dict]:
    return [field for field in fields if field["kind"] != "empty"][:3]


def names(fields: list[dict]) -> list[str]:
    return [field["name"] for field in its_line(fields)]


def test_a_booking_says_whom_when_and_the_service_then_who_does_it():
    arguments = {"customer": "Sofía", "services": HAIRCUT, "staff": "Ana", "start": "2026-11-26T10:00:00+01:00"}
    fields = fields_of("appointment.appointment.create", arguments)
    line = its_line(fields)
    assert [(field["name"], field["value"]) for field in line[:2]] == [("customer", "Sofía"), ("start", "26 nov 2026, 10:00")]
    assert line[2]["name"] == "services" and "Corte de mujer" in json.dumps(line[2]["value"], ensure_ascii=False)
    assert fields[3]["name"] == "staff"


def test_a_blocked_time_says_whose_its_start_and_end_and_what():
    arguments = {
        "title": "Comida",
        "block_type": "break",
        "start": "2026-11-26T14:00:00+01:00",
        "end": "2026-11-26T15:00:00+01:00",
        "staff": "Ana",
    }
    line = its_line(fields_of("appointment.blocked_time.create", arguments))
    assert [(field["name"], field["value"]) for field in line] == [
        ("staff", "Ana"),
        ("period", "26 nov 2026, 14:00–15:00"),
        ("title", "Comida"),
    ]


def test_a_blocked_time_of_the_whole_business_starts_with_its_period():
    arguments = {"title": "Inventario", "block_type": "other", "start": "2026-11-26T14:00:00+01:00", "end": "2026-11-26T15:00:00+01:00"}
    assert names(fields_of("appointment.blocked_time.create", arguments)) == ["period", "title", "block_type"]


def test_a_series_says_whom_when_it_repeats_and_the_service():
    arguments = {
        "customer": "Lucía",
        "services": HAIRCUT,
        "staff": "Ana",
        "start_date": "2026-12-01",
        "time": "10:00",
        "frequency": "monthly",
    }
    line = its_line(fields_of("appointment.recurring.create", arguments))
    assert names(line) == ["customer", "when", "services"]
    assert line[1]["value"] == {"start_date": "1 dic 2026", "time": "10:00", "frequency": "Cada mes"}


def test_a_series_changed_says_from_when_its_new_time_and_its_new_professional():
    """«desde febrero, a las 11:00 y con Carlos»: the new professional is on the line."""
    arguments = {"id": str(uuid.uuid4()), "from_date": "2027-02-01", "time": "11:00", "staff": "Carlos"}
    line = its_line(fields_of("appointment.recurring.update", arguments))
    assert [(field["name"], field["value"]) for field in line] == [
        ("when", {"from_date": "1 feb 2027", "time": "11:00"}),
        ("staff", "Carlos"),
    ]
