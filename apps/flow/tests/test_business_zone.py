"""Automations on the clock of the business, not the deployment's (hub#687; FLOW-F28, F29, F31 and its schedules)."""

import datetime as dt

import pytest

from apps.flow.models import Flow, FlowRun, Question
from base.models import Hub
from base.tenancy.context import use_hub

from .conftest import make_flow, run

pytestmark = pytest.mark.django_db

CANARY = "Atlantic/Canary"


def in_canary():
    return use_hub(Hub(slug="a", timezone=CANARY))


def test_a_question_says_an_instant_at_the_businesss_hour():
    steps = [{"id": "s1", "kind": "ask", "title": "Visit {{input.at}}?"}]
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=steps, language="es")
    with in_canary():
        ran = run("flow.flow.run", {"id": str(flow.id), "input": {"at": "2026-11-02T10:00:00+01:00"}})
    assert ran.status == FlowRun.Status.ASKING, ran
    assert Question.objects.get(run_id=ran.id).title == "Visit 2 nov 2026, 9:00?"


def test_a_schedule_fires_at_its_time_on_the_businesss_clock(clock):
    clock(dt.datetime(2026, 11, 2, 12, 0, tzinfo=dt.UTC))
    with in_canary():
        daily = run("flow.flow.create", {"trigger": {"kind": "schedule", "every": "day", "time": "09:00"}})
        daily = run("flow.flow.set_enabled", {"id": str(daily.id), "enabled": True})
    assert daily.next_fire_at == dt.datetime(2026, 11, 3, 9, 0, tzinfo=dt.UTC)
