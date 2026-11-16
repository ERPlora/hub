"""Tasks on the clock of the business, not the deployment's (hub#779): at 23:30 in the Canaries, already tomorrow in
Madrid, what is due today is still due today for the screen and for the server, which must not contradict each other."""

import datetime as dt

import pytest
from django.utils import timezone
from live.operations import get

from apps.task.queries import business_today

from .conftest import HUB_DB, ctx_for, make_task

pytestmark = HUB_DB

#: 23:30 in the Canaries (UTC in November), 00:30 of the 3rd in Madrid.
NIGHT = dt.datetime(2026, 11, 2, 23, 30, tzinfo=dt.UTC)


@pytest.fixture
def in_canary_at_night(monkeypatch, in_business_a):
    """Business A in the Canaries, at night."""
    monkeypatch.setattr(timezone, "now", lambda: NIGHT)
    monkeypatch.setattr(in_business_a, "timezone", "Atlantic/Canary")


def run(name, data=None):
    op = get(name)
    return op(ctx_for(), op.input.model_validate(data or {}))


def test_today_is_the_businesss_day(in_canary_at_night):
    assert business_today() == dt.date(2026, 11, 2)


def test_what_is_due_on_the_businesss_today_is_not_late_yet(in_canary_at_night):
    make_task("Due today", due_date=dt.date(2026, 11, 2))
    make_task("Late", due_date=dt.date(2026, 11, 1))
    assert [row.title for row in run("task.task.list", {"overdue": True}).rows] == ["Late"]


def test_a_new_task_is_numbered_on_the_businesss_day(in_canary_at_night):
    assert run("task.task.create", {"title": "Order dye"}).number.startswith("TSK-20261102-")


def test_a_business_that_changes_zone_never_repeats_a_number(monkeypatch, in_business_a):
    monkeypatch.setattr(timezone, "now", lambda: NIGHT)
    numbers = []
    # The same instant is the 2nd in the Canaries and the 3rd in Madrid: going back to the 2nd carries on its count.
    for zone in ("Atlantic/Canary", "Europe/Madrid", "Atlantic/Canary"):
        monkeypatch.setattr(in_business_a, "timezone", zone)
        numbers.append(run("task.task.create", {"title": "Order dye"}).number)
    assert numbers == ["TSK-20261102-0001", "TSK-20261103-0001", "TSK-20261102-0002"]
