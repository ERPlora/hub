"""The assistant's card for time off (``staff.time_off.create``, STAFF-F17): whose it is, what kind and its days, as
one period. «Ana se coge vacaciones del 21 al 31 de diciembre» drew «Crear en Personal: Vacaciones · 21 dic 2026 · 31
dic 2026», without whose (hub#2347): a normal card's line shows only its first three data, in the form's order."""

from live.operations import get

from base import assistant

from .conftest import HUB_DB, ctx_for

pytestmark = HUB_DB

TIME_OFF = "staff.time_off.create"
THIN = " "


def its_line(arguments: dict, language: str = "es") -> list[tuple[str, object]]:
    fields = assistant.cards.card(get(TIME_OFF), arguments, language, ctx_for(language=language))["fields"]
    return [(field["name"], field["value"]) for field in fields if field["kind"] != "empty"][:3]


def test_whose_what_and_its_days_go_first():
    arguments = {"leave_type": "vacation", "start_date": "2026-12-21", "end_date": "2026-12-31", "member": "Ana"}
    assert its_line(arguments) == [("member", "Ana"), ("leave_type", "Vacaciones"), ("period", "21–31 dic 2026")]
    assert its_line(arguments, "en")[2] == ("period", f"Dec 21{THIN}–{THIN}31, 2026")


def test_a_part_of_a_day_says_its_hours():
    arguments = {
        "leave_type": "personal",
        "start_date": "2026-12-03",
        "end_date": "2026-12-03",
        "is_full_day": False,
        "start_time": "09:00",
        "end_time": "11:30",
        "member": "Ana",
    }
    assert its_line(arguments)[2] == ("period", "3 dic 2026, 9:00–11:30")


def test_data_the_write_refuses_keep_the_card_as_they_came():
    arguments = {"leave_type": "vacation", "start_date": "2026-12-31", "end_date": "2026-12-21", "member": "Ana"}
    assert [name for name, _ in its_line(arguments)] == ["leave_type", "start_date", "end_date"]
