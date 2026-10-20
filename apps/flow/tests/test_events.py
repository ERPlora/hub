"""The flow app's events (``flow.<entity>.<fact>``) and its reaction to every other app's events.

There is no outbox relay yet (phase 2 runs it in the worker); the reaction is tested by handing ``react``
(or ``deliver``) a real event of the outbox, made by another app's real operation, as the relay will.
"""

import re

import pytest
from live.context import system_context
from live.models import OutboxEvent
from live.operations import NAME_RE

from apps.flow import events
from apps.flow.models import FlowRun
from apps.task.models import Task

from .conftest import A, make_flow, run

PAST_FACT = re.compile(r"^flow\.[a-z_]+\.[a-z_]+ed$")


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str) and value.startswith("flow.")
    }


def test_the_events_of_the_workbook():
    assert declared() == {
        "FLOW_CREATED": "flow.flow.created",
        "FLOW_UPDATED": "flow.flow.updated",
        "FLOW_ENABLED": "flow.flow.enabled",
        "FLOW_PAUSED": "flow.flow.paused",
        "FLOW_GRANTED": "flow.flow.granted",
        "FLOW_DELETED": "flow.flow.deleted",
        "RUN_STARTED": "flow.run.started",
        "RUN_PARKED": "flow.run.parked",
        "RUN_RESUMED": "flow.run.resumed",
        "RUN_FINISHED": "flow.run.finished",
        "DRAFT_PROPOSED": "flow.draft.proposed",
        "DRAFT_USED": "flow.draft.used",
        "DRAFT_DISMISSED": "flow.draft.dismissed",
        "SECRET_SAVED": "flow.secret.saved",
        "SECRET_DELETED": "flow.secret.deleted",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_all_lists_every_event_once_and_the_groups_cover_them():
    assert events.ALL == list(declared().values())
    assert events.FLOW_EVENTS + events.RUN_EVENTS + events.DRAFT_EVENTS + events.SECRET_EVENTS == events.ALL


def test_it_reacts_to_every_event():
    # The relay hands every event to flow (WORKBOOK FLOW-F21), not only the names of REACTIONS.
    assert events.REACTIONS == {"*": "flow.run.react"}


@pytest.mark.django_db
def test_react_starts_the_flows_of_a_real_event_as_the_platform():
    flow = make_flow()
    run("customer.customer.create", {"name": "Ana López"}, system_context(A))
    event = OutboxEvent.objects.get(name="customer.customer.created")
    result = events.deliver(event)
    assert (result.started, result.skipped) == (1, 0)
    created = FlowRun.objects.get(flow=flow)
    assert created.status == FlowRun.Status.SUCCEEDED
    assert created.trigger_key == str(event.id)
    assert Task.objects.filter(title="Welcome the new customer").count() == 1


@pytest.mark.django_db
def test_react_passes_the_id_and_the_actor_of_the_event():
    make_flow()
    result = events.react(
        A,
        "customer.customer.created",
        {"id": "x"},
        event_id="0199e7a0-0000-7000-8000-000000000001",
        actor="system",
    )
    assert result.started == 1
    assert FlowRun.objects.get().trigger_key == "0199e7a0-0000-7000-8000-000000000001"


def test_react_ignores_its_own_events():
    assert (
        events.react(
            A,
            "flow.run.finished",
            {"id": "x"},
            event_id="0199e7a0-0000-7000-8000-000000000001",
        )
        is None
    )
