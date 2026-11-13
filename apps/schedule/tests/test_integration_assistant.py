"""The assistant's confirmation card names each datum of a write of Schedules by a name of the app's own (base's half is
hub#258): in Spanish, never by the title pydantic makes up from the field («Intervals», «Special Days»), nor by a word
another app's catalog happens to lend. The card is base's (``base.assistant.card``); the names are schedule's: the
titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog, as its screens (the
week's hours, the special days and the temporary changes) say them."""

import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen, technical_names

APP = Path(apps.get_app_config("schedule").path)
SCREENS = json.loads((APP / "frontend/locale/es.json").read_text())["schedule"]
SCREENS_EN = json.loads((APP / "frontend/locale/en.json").read_text())["schedule"]

#: The writes of Schedules the assistant calls, by name.
TOOLS = sorted(
    name
    for name, op in registry.items()
    if op.app_label == "schedule" and op.kind == "command" and assistant.is_tool(op)
)

#: The writes that send a day's opening intervals.
WITH_INTERVALS = (
    "schedule.week.set_day",
    "schedule.special_day.create",
    "schedule.special_day.update",
    "schedule.override.create",
    "schedule.override.update",
)


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


@pytest.fixture
def named(monkeypatch):
    """Every record a write names by its id comes out named, as a person who may read it sees it: this test is about
    what the card calls each datum, and a record nobody names is left out of it (hub#675)."""
    monkeypatch.setattr(assistant, "_reference", lambda value, prop, words: "Navidad")


def schedule_writes() -> list:
    return [get(name) for name in TOOLS]


def named_by_schedule(op, name: str, title: str | None) -> bool:
    """Whether schedule itself names the datum ``name`` of ``op``: by its schema's own title, by the ``verbose_name``
    of one of its models, or by its own catalog. A title pydantic made up that another app's catalog happens to
    translate is not a name of Schedules: it changes if that app's text changes."""
    made_up = assistant._generated_title(name)
    with (APP / "locale/es/LC_MESSAGES/django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    return (
        bool(title and title != made_up)
        or assistant._verbose_name("schedule", op.name.split(".")[1], name) is not None
        or own.gettext(made_up) != made_up
    )


def test_no_datum_of_a_write_of_schedule_reaches_a_spanish_card_by_its_technical_name(named):
    """Every write of schedule the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up."""
    writes = schedule_writes()
    assert len(writes) >= 10  # positive control: the registry has schedule's writes
    assert technical_names(writes) == {}


def test_no_datum_of_a_write_of_schedule_borrows_its_name_from_another_apps_catalog(named):
    """``technical_names`` sees only a title nobody translates; one that another app's catalog happens to translate
    passes it and is still no name of Schedules: it changes if that app's text changes. So each datum is also named by
    schedule itself, by where the name comes from, not by the word (kept in hub#675)."""
    screen = named_by_the_screen()
    borrowed: dict[str, list[str]] = {}
    for op in schedule_writes():
        props = assistant._schema(op).get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            datum = field["name"]
            if datum not in screen and not named_by_schedule(op, datum, props[datum].get("title")):
                borrowed.setdefault(op.name, []).append(datum)
    assert borrowed == {}


def test_the_card_names_the_intervals_as_the_hours_form():
    """A day of the week, a special day or a temporary change: its opening intervals, «Tramos horarios», as the legend
    of the hours form says them."""
    assert set(WITH_INTERVALS) <= set(TOOLS)
    for name in WITH_INTERVALS:
        op = get(name)
        assert labels(assistant.card(op, {"intervals": []}, "es")) == [SCREENS["intervals"]["legend"]], name
        assert labels(assistant.card(op, {"intervals": []}, "en")) == [SCREENS_EN["intervals"]["legend"]], name


@pytest.mark.parametrize(
    ("write", "list_"),
    [
        ("schedule.special_day.delete", "specialDays"),
        ("schedule.special_day.update", "specialDays"),
        ("schedule.override.delete", "overrides"),
        ("schedule.override.update", "overrides"),
    ],
)
def test_the_card_names_the_record_of_a_write_as_its_list_calls_one(named, write, list_):
    """The special day or temporary change a write acts on, titled with the word its list on «Special days» calls one
    of them, in each language («Día especial», «Override»): never «Registro» (hub#675)."""
    op = get(write)
    for screens, language in ((SCREENS, "es"), (SCREENS_EN, "en")):
        one = screens[list_]["entity"]["one"]
        assert labels(assistant.card(op, {"id": "0192f0b2-3333-7000-8000-000000000003"}, language)) == [
            one[:1].upper() + one[1:]
        ], (write, language)


def test_the_card_names_the_special_days_of_a_bulk_as_their_tab():
    bulk = get("schedule.special_day.bulk_create")
    arguments = {"special_days": [{"date": "2026-12-25", "name": "Navidad"}]}
    assert labels(assistant.card(bulk, arguments, "es")) == [SCREENS["specialDays"]["heading"]]
    assert labels(assistant.card(bulk, arguments, "en")) == [SCREENS_EN["specialDays"]["heading"]]
