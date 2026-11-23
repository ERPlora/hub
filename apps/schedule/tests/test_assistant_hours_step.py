"""What the assistant reads of the step «Confirm your opening hours» once it is done (BASE-F12, SCHEDULE-F03).

Asked whether everything was ready to open, the model answered that the default week (Monday to Friday, 09:00–18:00)
was set, hours after the business had changed it: the step came done with its line on the list, which named the default
week. A step's texts say what it asks for, in every state; the week the business has is read in Schedules.
"""

import json
import re

import pytest
from django.utils import translation
from django.utils.dates import WEEKDAYS
from live import assistant as shared
from live.context import OperationContext
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get

from apps.schedule.models import WeekDay
from apps.schedule.tests.conftest import HUB_DB, A

pytestmark = HUB_DB

CLOCK_TIME = re.compile(r"\b\d{1,2}[:.]\d{2}\b")


def person(language: str) -> OperationContext:
    permissions = permissions_for_role(all_live_app_configs(), "hub_owner")
    return OperationContext(scope=A, actor="tester", permissions=permissions, language=language)


def default_open_days() -> list[int]:
    """The weekdays the default week opens, as migration 0002 planted them."""
    return list(WeekDay.objects.filter(is_closed=False).order_by("weekday").values_list("weekday", flat=True))


def change_the_week(ctx: OperationContext) -> None:
    """The bar of the report: closed on Mondays, from Tuesday to Sunday from 12:00 to 23:30."""
    set_day = get("schedule.week.set_day")
    set_day(ctx, set_day.input.model_validate({"weekday": 0, "is_closed": True}))
    for weekday in range(1, 7):
        data = {"weekday": weekday, "intervals": [{"open_time": "12:00", "close_time": "23:30"}]}
        set_day(ctx, set_day.input.model_validate(data))


def hours_step_as_the_assistant_reads_it(ctx: OperationContext) -> dict:
    outcome = shared.run_tool(ctx, get("base.setup.status"), "{}")
    assert outcome.outcome == "ok", outcome
    (step,) = [item for item in json.loads(outcome.content)["items"] if item["key"] == "schedule.hours"]
    return step


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_done_step_tells_the_assistant_nothing_of_the_default_week(language):
    ctx = person(language)
    open_days = default_open_days()
    change_the_week(ctx)

    step = hours_step_as_the_assistant_reads_it(ctx)

    assert step["state"] == "done"
    said = f"{step['title']} {step['description']}"
    assert CLOCK_TIME.findall(said) == []
    with translation.override(language):
        day_names = [str(WEEKDAYS[weekday]) for weekday in open_days]
    assert [name for name in day_names if name.lower() in said.lower()] == []
