"""The assistant's card for a person's weekly schedule (STAFF-F13, STAFF-F14): whose it is and its week first, each run of
days with the same hours on one line with those hours, as the write keeps them. A day asked for without its hours
shows the business's default working day it takes (Staff › Settings). «A Bea ponle su horario: trabaja de martes a
sábado.» drew «Crear en Personal: Por defecto: Sí · Semana: 5 elementos · Miembro del personal: Bea», with 09:00–18:00
behind it (hub#2716): a normal card's line shows only its first three data."""

from live.assistant import NAMED
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get

from apps.staff.models import StaffSettings
from base import assistant
from base.assistant.card_period import period

from .conftest import HUB_DB, ctx_for, make_member, make_schedule, t

pytestmark = HUB_DB

CREATE = "staff.schedule.create"
UPDATE = "staff.schedule.update"
THIN = "\u2009"
TUESDAY_TO_SATURDAY = [{"weekday": day} for day in range(1, 6)]


def salon_working_day():
    StaffSettings.objects.create(default_work_start=t("10:00"), default_work_end=t("19:00"), default_break_duration=60)


def its_data(name: str, arguments: dict, language: str = "es", ctx=None) -> list[dict]:
    card = assistant.cards.card(get(name), arguments, language, ctx or ctx_for(language=language))
    return [field for field in card["fields"] if field["kind"] != "empty"]


def its_line(name: str, arguments: dict, language: str = "es", ctx=None) -> list[tuple[str, object]]:
    return [(field["name"], field["value"]) for field in its_data(name, arguments, language, ctx)[:3]]


def its_week(name: str, arguments: dict, language: str = "es", ctx=None) -> list[dict]:
    week = next(field for field in its_data(name, arguments, language, ctx) if field["name"] == "days")
    assert week.get(NAMED) is True
    return week["value"]


def test_whose_and_the_week_go_first_with_the_business_working_day():
    salon_working_day()
    make_member("Bea")
    arguments = {"member": "Bea", "days": TUESDAY_TO_SATURDAY}
    assert its_line(CREATE, arguments)[:2] == [
        ("member", "Bea"),
        ("days", [{"days": f"Martes{THIN}–{THIN}Sábado", "hours": "10:00–14:00, 15:00–19:00"}]),
    ]
    # In English, as every card says an hour: the language's own clock.
    assert its_week(CREATE, arguments, "en") == [
        {"days": f"Tuesday{THIN}–{THIN}Saturday", "hours": f"{period(t('10:00'), t('14:00'), 'en')}, {period(t('15:00'), t('19:00'), 'en')}"}
    ]


def test_each_run_of_days_with_the_same_hours_is_one_line_and_a_day_off_is_not_said():
    make_member("Bea")
    days = [
        *({"weekday": day, "start_time": "10:00", "end_time": "19:00"} for day in (0, 1, 3)),
        {"weekday": 5, "start_time": "10:00", "end_time": "14:00"},
        {"weekday": 6, "is_working": False},
    ]
    assert its_week(CREATE, {"member": "Bea", "days": days}) == [
        {"days": f"Lunes{THIN}–{THIN}Martes", "hours": "10:00–19:00"},
        {"days": "Jueves", "hours": "10:00–19:00"},
        {"days": "Sábado", "hours": "10:00–14:00"},
    ]


def test_without_saved_settings_it_is_the_settings_own_working_day():
    make_member("Bea")
    assert its_week(CREATE, {"member": "Bea", "days": [{"weekday": 0}]}) == [
        {"days": "Lunes", "hours": "9:00–13:00, 14:00–18:00"}
    ]


def test_who_cannot_read_the_settings_sees_the_days_and_no_hours_made_up():
    salon_working_day()
    make_member("Bea")
    blind = ctx_for(permissions=permissions_for_role(all_live_app_configs(), "hub_admin") - {"staff.view"})
    assert its_week(CREATE, {"member": "Bea", "days": TUESDAY_TO_SATURDAY}, ctx=blind) == [{"days": f"Martes{THIN}–{THIN}Sábado"}]


def test_an_edited_schedule_says_which_it_is_and_its_week():
    salon_working_day()
    schedule = make_schedule(make_member("Bea"))
    line = its_line(UPDATE, {"id": str(schedule.id), "days": [{"weekday": 5}]})
    assert line[1] == ("days", [{"days": "Sábado", "hours": "10:00–14:00, 15:00–19:00"}])
    assert line[0][0] == "id"


def test_data_the_write_refuses_keep_the_card_as_they_came():
    make_member("Bea")
    arguments = {"member": "Bea", "days": [{"weekday": 6, "is_working": False}]}
    assert NAMED not in next(field for field in its_data(CREATE, arguments) if field["name"] == "days")
