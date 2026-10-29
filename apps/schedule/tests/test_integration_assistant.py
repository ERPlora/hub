"""The assistant's confirmation card names each datum of a write of Schedules by a name of the app's own
(FIX-HUB-SCHEDULE-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258): in Spanish, never by the title pydantic
makes up from the field («Intervals», «Special Days»), nor by a word another app's catalog happens to lend. The card is
base's (``base.assistant.card``); the names are schedule's: the titles of its schemas and the ``verbose_name`` of its
models, with their Spanish in its catalog, as its screens (the week's hours, the special days and the temporary
changes) say them."""

import gettext
import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

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


def test_no_datum_of_a_write_of_schedule_reaches_a_spanish_card_by_its_technical_name():
    """Every write of schedule the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up. By where the name comes from, not by the word."""
    screen = named_by_the_screen()
    assert len(TOOLS) >= 10  # positive control: the registry has schedule's writes
    technical: dict[str, list[str]] = {}
    for name in TOOLS:
        op = get(name)
        props = assistant._schema(op).get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            datum = field["name"]
            if datum not in screen and not named_by_schedule(op, datum, props[datum].get("title")):
                technical.setdefault(name, []).append(datum)
    assert technical == {}


def test_the_card_names_the_intervals_as_the_hours_form():
    """A day of the week, a special day or a temporary change: its opening intervals, «Tramos horarios», as the legend
    of the hours form says them."""
    assert set(WITH_INTERVALS) <= set(TOOLS)
    for name in WITH_INTERVALS:
        op = get(name)
        assert labels(assistant.card(op, {"intervals": []}, "es")) == [SCREENS["intervals"]["legend"]], name
        assert labels(assistant.card(op, {"intervals": []}, "en")) == [SCREENS_EN["intervals"]["legend"]], name


def test_the_card_names_the_special_days_of_a_bulk_as_their_tab():
    bulk = get("schedule.special_day.bulk_create")
    arguments = {"special_days": [{"date": "2026-12-25", "name": "Navidad"}]}
    assert labels(assistant.card(bulk, arguments, "es")) == [SCREENS["specialDays"]["heading"]]
    assert labels(assistant.card(bulk, arguments, "en")) == [SCREENS_EN["specialDays"]["heading"]]
