"""What the assistant reads of a schedule names each working day as the screens do, in the person's language.

The model never sees a result's schema: a day it reads only as a number it counts from Monday = 1. A schedule from
Tuesday to Saturday (stored 1 to 5, Monday = 0) reached the person as «de lunes a jueves sigue de 10:00 a 19:00».
"""

import json

import pytest
from django.utils import translation
from live.operations import get

from base import assistant
from base.weekdays import weekday_name

from .conftest import HUB_DB, ctx_for, make_member, make_schedule

pytestmark = HUB_DB

TUESDAY_TO_SATURDAY = {day: ("10:00", "19:00", "14:00", "15:00") for day in range(1, 6)}
SATURDAY_MORNING = {"weekday": 5, "start_time": "09:00", "end_time": "14:00"}


def told(name: str, arguments: dict, language: str) -> str:
    """What the model reads back from the tool ``name`` run with ``arguments`` for an administrator who speaks
    ``language``."""
    with translation.override(language):
        outcome = assistant.tools.run(
            ctx_for("hub_admin", language=language), get(name), json.dumps(arguments)
        )
    assert outcome.outcome == "ok", outcome.content
    return outcome.content


def days_said(content: str, language: str) -> list[str]:
    return [name for name in (weekday_name(day, language) for day in range(7)) if name in content]


def arguments_for(name: str, ana, schedule) -> dict:
    if name == "staff.schedule.list":
        return {"member_id": str(ana.id)}
    if name == "staff.schedule.detail":
        return {"id": str(schedule.id)}
    tuesday_to_friday = [
        {"weekday": day, "start_time": "10:00", "end_time": "19:00", "break_start": "14:00", "break_end": "15:00"}
        for day in range(1, 5)
    ]
    return {"id": str(schedule.id), "days": [*tuesday_to_friday, SATURDAY_MORNING]}


@pytest.mark.parametrize("language", ["es", "en"])
@pytest.mark.parametrize("name", ["staff.schedule.list", "staff.schedule.detail", "staff.schedule.update"])
def test_the_model_reads_each_working_day_of_a_schedule_by_its_name(name, language):
    ana = make_member("Ana")
    schedule = make_schedule(ana, TUESDAY_TO_SATURDAY)

    content = told(name, arguments_for(name, ana, schedule), language)

    assert days_said(content, language) == [weekday_name(day, language) for day in range(1, 6)]
