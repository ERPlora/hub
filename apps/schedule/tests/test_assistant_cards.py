"""hub#2288: the card of a write of Schedules says the hours it keeps, never «1 item» nor a line without them. A day's
intervals go by their times; a special day or a temporary change says what it is, when, and its hours or that it is
closed, first, because a normal card's line shows only its first three data; the year's holidays loaded at once go by
their day and their name, and by their hours when open (SCHEDULE-F02, SCHEDULE-F04, SCHEDULE-F05, SCHEDULE-F06).
"""

import dataclasses

import pytest
from live.assistant import NAMED
from live.operations import get

from apps.schedule.tests.conftest import HUB_DB, ctx_for
from base import assistant

THIN = " "
NARROW = " "
SUMMER = {"start_date": "2027-07-01", "end_date": "2027-08-31", "reason": "Horario de verano"}
EIGHT_TO_THREE = [{"open_time": "08:00", "close_time": "15:00"}]
SAID = {
    "es": {"summer": f"1 jul{THIN}–{THIN}31 ago 2027", "eight": "8:00", "three": "15:00", "eve": "24 dic 2027", "closed": "Cerrado"},
    "en": {
        "summer": f"Jul 1{THIN}–{THIN}Aug 31, 2027",
        "eight": f"8:00{NARROW}AM",
        "three": f"3:00{NARROW}PM",
        "eve": "Dec 24, 2027",
        "closed": "Closed",
    },
}


def drawn(write: str, arguments: dict, language: str) -> list[dict]:
    ctx = dataclasses.replace(ctx_for(), language=language)
    return assistant.cards.card(get(write), arguments, language, ctx)["fields"]


def line(write: str, arguments: dict, language: str = "en") -> list[tuple]:
    """The card's line as the chat writes a normal write (``cardLine`` of @erplora/ui): its first three data, the
    empty ones left out."""
    shown = [field for field in drawn(write, arguments, language) if field["kind"] != "empty"]
    return [(field["name"], field["value"]) for field in shown[:3]]


@HUB_DB
@pytest.mark.parametrize("language", ["en", "es"])
def test_the_hours_of_a_day_are_said_by_their_times(language):
    """The issue's card said «Sábado · Cerrado: No · 1 elemento»."""
    arguments = {"weekday": 5, "is_closed": False, "intervals": [{"open_time": "09:00", "close_time": "14:00"}]}
    intervals = {field["name"]: field for field in drawn("schedule.week.set_day", arguments, language)}["intervals"]
    nine = "9:00" if language == "es" else f"9:00{NARROW}AM"
    two = "14:00" if language == "es" else f"2:00{NARROW}PM"
    assert (intervals["value"], intervals.get(NAMED)) == ([{"open_time": nine, "close_time": two}], True)


# ── A temporary change: what, when and its hours ──────────────────────────────────────────────────────────────────────


@HUB_DB
@pytest.mark.parametrize("language", ["en", "es"])
def test_a_temporary_change_says_what_it_is_when_and_its_hours(language):
    """The issue's card said «1 jul 2027 · 31 ago 2027 · Horario de verano», without the hours it keeps."""
    words = SAID[language]
    arguments = {**SUMMER, "is_closed": False, "intervals": EIGHT_TO_THREE}
    assert line("schedule.override.create", arguments, language) == [
        ("reason", "Horario de verano"),
        ("period", words["summer"]),
        ("intervals", [{"open_time": words["eight"], "close_time": words["three"]}]),
    ]
    period = next(field for field in drawn("schedule.override.create", arguments, language) if field["name"] == "period")
    assert period["label"] == {"en": "When", "es": "Cuándo"}[language]


@HUB_DB
@pytest.mark.parametrize("language", ["en", "es"])
def test_a_change_left_closed_says_it_is_closed_and_not_the_hours_it_ignores(language):
    """Closed is the default: intervals sent without «open» are ignored by the write, so the card does not say them."""
    fields = drawn("schedule.override.create", {**SUMMER, "intervals": EIGHT_TO_THREE}, language)
    shown = [(field["name"], field["value"]) for field in fields]
    assert shown[2] == ("is_closed", True)
    assert fields[2]["label"] == SAID[language]["closed"]
    assert "intervals" not in dict(shown)
    assert {"start_date", "end_date"}.isdisjoint(dict(shown))


@HUB_DB
def test_a_change_the_write_refuses_keeps_its_card_as_it_came():
    """Open without hours, or ending before it starts: the write refuses it, and the card makes up no hours."""
    for arguments in ({**SUMMER, "is_closed": False}, {**SUMMER, "end_date": "2027-06-01"}):
        assert [name for name, _ in line("schedule.override.create", arguments)] == ["start_date", "end_date", "reason"]


# ── A special day: what, when and its hours ───────────────────────────────────────────────────────────────────────────


@HUB_DB
@pytest.mark.parametrize("language", ["en", "es"])
def test_a_special_day_open_says_its_name_its_day_and_its_hours(language):
    words = SAID[language]
    arguments = {"date": "2027-12-24", "name": "Nochebuena", "is_closed": False, "intervals": EIGHT_TO_THREE}
    assert line("schedule.special_day.create", arguments, language) == [
        ("name", "Nochebuena"),
        ("date", words["eve"]),
        ("intervals", [{"open_time": words["eight"], "close_time": words["three"]}]),
    ]


@HUB_DB
def test_a_special_day_closed_says_it_is_closed():
    arguments = {"date": "2027-12-25", "name": "Navidad", "recurring_yearly": True}
    assert line("schedule.special_day.create", arguments) == [
        ("name", "Navidad"),
        ("date", "Dec 25, 2027"),
        ("is_closed", True),
    ]


# ── The year's holidays at once ───────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
@pytest.mark.parametrize("language", ["en", "es"])
def test_the_special_days_loaded_at_once_are_said_by_their_day_and_name(language):
    """The issue's card said «Crear en Horarios: 10 elementos». A closed day says nothing more; an open one, its hours
    as the list of special days says them, and the hours a closed day ignores are not said."""
    days = [
        {"date": "2027-01-01", "name": "Año Nuevo", "is_closed": True, "recurring_yearly": True},
        {"date": "2027-01-06", "name": "Epifanía del Señor", "intervals": EIGHT_TO_THREE},
        {"date": "2027-12-24", "name": "Nochebuena", "is_closed": False, "intervals": [*EIGHT_TO_THREE, *EIGHT_TO_THREE]},
    ]
    special = {field["name"]: field for field in drawn("schedule.special_day.bulk_create", {"special_days": days}, language)}
    words = SAID[language]
    hours = f"{words['eight']}{'–' if language == 'es' else f'{THIN}–{THIN}'}{words['three']}"
    new_year = {"es": "1 ene 2027", "en": "Jan 1, 2027"}[language]
    epiphany = {"es": "6 ene 2027", "en": "Jan 6, 2027"}[language]
    assert special["special_days"]["value"] == [
        {"date": new_year, "name": "Año Nuevo"},
        {"date": epiphany, "name": "Epifanía del Señor"},
        {"date": words["eve"], "name": "Nochebuena", "hours": f"{hours}, {hours}"},
    ]
    assert special["special_days"].get(NAMED) is True


@HUB_DB
def test_an_automations_card_says_the_days_by_the_mark_of_their_name():
    """With nobody at hand (an automation's card) no summary runs: the name the person wrote still names each day."""
    days = [{"date": "2027-01-01", "name": "Año Nuevo"}]
    card = assistant.cards.card(get("schedule.special_day.bulk_create"), {"special_days": days}, "es")
    special = next(field for field in card["fields"] if field["name"] == "special_days")
    assert (special["value"], special.get(NAMED)) == ([{"date": "1 ene 2027", "name": "Año Nuevo"}], True)


@HUB_DB
def test_special_days_the_write_refuses_keep_their_card_as_it_came():
    """A date that is none: the whole list is refused, and the card counts it."""
    days = [{"date": "2027-02-30", "name": "Nunca"}]
    special = {field["name"]: field for field in drawn("schedule.special_day.bulk_create", {"special_days": days}, "en")}
    assert special["special_days"].get(NAMED) is None
