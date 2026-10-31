"""The assistant's card for a write of attendance (FIX-HUB-ATTENDANCE-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is
hub#258): in Spanish, every datum it sends by the name the Time tracking screens give it, never by the title pydantic
makes up from the field («Lat», «Lng», «Accuracy M»). The card is base's (``base.assistant.card``); the names are
attendance's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog.

The record a write names by its id (FIX-HUB-ATTENDANCE-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS; base's half is hub#416):
the person clocked, whose break starts or ends or whose day is closed, and the working day corrected, by the name
the screens give them («Ana López», «Ana López · 6 oct 2026»), read as whoever asks — never by the id, and left out
when that person may not read it."""

import datetime as dt
import json
from pathlib import Path

import pytest
from django.apps import apps
from live.operations import get, registry

from apps.attendance.models import Record
from apps.staff.models import Member
from base import assistant
from base.tests.test_assistant import named_by_the_screen
from base.tests.test_assistant_card_values import AN_ID

from .conftest import ctx_for, make_member, utc

FRONTEND = Path(apps.get_app_config("attendance").path) / "frontend/locale"
SETTINGS = json.loads((FRONTEND / "es.json").read_text())["attendance"]["settings"]
SETTINGS_EN = json.loads((FRONTEND / "en.json").read_text())["attendance"]["settings"]
POSITION = {"lat": 40.4168, "lng": -3.7038, "accuracy_m": 12.0}


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def attendance_writes() -> list:
    return [
        op
        for op in registry.values()
        if op.app_label == "attendance" and op.kind == "command" and assistant.is_tool(op)
    ]


def test_no_datum_of_a_write_of_attendance_reaches_a_spanish_card_by_its_technical_name():
    """Every write of attendance the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = attendance_writes()
    # Positive control: the registry has attendance's writes, the ones that send a position among them.
    assert {"attendance.record.clock_in", "attendance.record.clock_out", "attendance.settings.update"} <= {
        op.name for op in writes
    }
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def test_the_card_names_the_position_of_a_clock_in_as_the_settings_screen_does():
    for name in ("attendance.record.clock_in", "attendance.record.clock_out"):
        op = get(name)
        assert labels(assistant.card(op, POSITION, "es")) == [
            SETTINGS["latitude"],
            SETTINGS["longitude"],
            "Precisión (m)",
        ], name
        assert labels(assistant.card(op, POSITION, "en")) == [
            SETTINGS_EN["latitude"],
            SETTINGS_EN["longitude"],
            "Accuracy (m)",
        ], name


# ── The record a write names by its id, by its name ───────────────────────────────────────────────────────────────────

#: The writes that act on a person: none named is the caller; someone else, for whoever clocks others.
CLOCKING = ("attendance.record.clock_in", "attendance.record.clock_out", "attendance.break.start", "attendance.break.end")
#: Who manages others, by the one permission each write asks for on top of «Clock in», and by the manager's role.
CLOCKS_OTHERS = frozenset({"attendance.clock", "attendance.clock_others"})
CORRECTS = frozenset({"attendance.clock", "attendance.correct"})


def values(card: dict) -> dict:
    return {field["name"]: field["value"] for field in card["fields"]}


def manager(make_user, permissions: frozenset | None):
    """Marta, who manages the team: with ``permissions`` alone, or with the manager's role when ``None``."""
    user = make_user("marta", role="hub_manager", first_name="Marta", last_name="Jefa")
    make_member("Marta", "Jefa", user=user.person)
    return ctx_for("hub_manager", actor=user, permissions=permissions)


def no_id(card: dict) -> bool:
    return not AN_ID.search(json.dumps(card, ensure_ascii=False))


@pytest.mark.django_db
@pytest.mark.parametrize("name", CLOCKING)
def test_an_employee_who_clocks_themselves_reads_their_own_name_on_the_card(name, person):
    """The most common card: an employee, with only «Clock in», clocks in or out or pauses by their own id."""
    ana, ctx = person()
    card = assistant.card(get(name), {"member_id": str(ana.id)}, "es", ctx)
    assert values(card) == {"member_id": "Ana López"}
    assert labels(card) == ["Persona"]
    assert no_id(card)
    assert labels(assistant.card(get(name), {"member_id": str(ana.id)}, "en", ctx)) == ["Person"]


@pytest.mark.django_db
@pytest.mark.parametrize("permissions", [CLOCKS_OTHERS, None], ids=["clock_others", "hub_manager"])
@pytest.mark.parametrize("name", CLOCKING)
def test_who_clocks_someone_else_reads_their_name_on_the_card(name, permissions, make_user):
    """ATTENDANCE-F12 «ficha la entrada de Ana»: the card says whom, by the name, never by the id."""
    bea = make_member("Bea", "Ruiz")
    card = assistant.card(get(name), {"member_id": str(bea.id)}, "es", manager(make_user, permissions))
    assert values(card) == {"member_id": "Bea Ruiz"}
    assert no_id(card)


@pytest.mark.django_db
@pytest.mark.parametrize("name", CLOCKING)
def test_someone_else_is_left_out_of_the_card_of_who_only_clocks_themselves(name, person):
    """The write refuses it («You can only clock yourself in and out.»); the card names nobody by an id meanwhile."""
    _, ctx = person()
    bea = make_member("Bea", "Ruiz")
    card = assistant.card(get(name), {"member_id": str(bea.id)}, "es", ctx)
    assert values(card) == {}
    # Positive control: the same card names her for whoever clocks others.
    assert values(assistant.card(get(name), {"member_id": str(bea.id)}, "es", ctx_for("hub_manager"))) == {
        "member_id": "Bea Ruiz"
    }


@pytest.mark.parametrize("name", CLOCKING)
def test_a_person_named_by_their_name_is_a_person_on_the_card_too(name):
    card = assistant.card(get(name), {"member": "Bea"}, "es")
    assert (values(card), labels(card)) == ({"member": "Bea"}, ["Persona"])


def open_day(member: Member, clock_in: str = "2026-10-06T07:00", clock_out: str | None = None) -> Record:
    start = utc(clock_in)
    return Record.objects.create(
        member=member,
        clock_in_at=start,
        clock_out_at=utc(clock_out) if clock_out else None,
        status="closed" if clock_out else "open",
        work_date=dt.date(2026, 10, 6),
    )


@pytest.mark.django_db
@pytest.mark.parametrize("permissions", [CORRECTS, None], ids=["correct", "hub_manager"])
@pytest.mark.parametrize(
    ("language", "named", "label"),
    [("es", "Ana López · 6 oct 2026", "Jornada"), ("en", "Ana López · Oct 6, 2026", "Working day")],
)
def test_a_correction_names_the_working_day_by_its_person_and_its_day(language, named, label, permissions, make_user):
    """«Correct working day» (ATTENDANCE-F08, high risk): the card says which day, as the correction screen names it —
    the person and the day —, so a wrong day is seen before confirming."""
    record = open_day(make_member("Ana", "López"), clock_out="2026-10-06T15:00")
    arguments = {
        "record_id": str(record.id),
        "clock_in_at": "2026-10-06T08:00:00+02:00",
        "clock_out_at": "2026-10-06T16:00:00+02:00",
        "reason": "Forgot to clock in",
    }
    card = assistant.card(get("attendance.record.correct"), arguments, language, manager(make_user, permissions))
    assert values(card)["record_id"] == named
    assert labels(card)[0] == label
    assert no_id(card)


@pytest.mark.django_db
@pytest.mark.parametrize("permissions", [CORRECTS, None], ids=["correct", "hub_manager"])
def test_closing_the_day_of_who_was_terminated_names_them(permissions, make_user):
    """ATTENDANCE-F13 (the reaction to a termination, also the assistant's): the card says whose day it closes."""
    carlos = make_member("Carlos", "Gil", status=Member.Status.TERMINATED)
    open_day(carlos)
    card = assistant.card(
        get("attendance.record.close_for_terminated"), {"id": str(carlos.id)}, "es", manager(make_user, permissions)
    )
    assert (values(card), labels(card)) == ({"id": "Carlos Gil"}, ["Persona"])
    assert no_id(card)
