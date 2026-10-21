"""The task app's events (``task.<entity>.<fact>``) and its reaction to Staff's.

A reaction is tested here by handing ``react`` the event as the outbox relay does: its name, its scope
and its payload. Its delivery by the worker's real relay is in ``test_relay.py``.
"""

import re

import pytest
from live.operations import NAME_RE

from apps.task import events
from apps.task.models import Task

from .conftest import A, make_member, make_task

PAST_FACT = re.compile(r"^task\.[a-z_]+\.[a-z_]+ed$")


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str) and value.startswith("task.")
    }


def test_the_events_of_the_workbook():
    assert declared() == {
        "TASK_CREATED": "task.task.created",
        "TASK_UPDATED": "task.task.updated",
        "TASK_STATUS_CHANGED": "task.task.status_changed",
        "TASK_COMPLETED": "task.task.completed",
        "TASK_ASSIGNED": "task.task.assigned",
        "TASK_DELETED": "task.task.deleted",
        "COMMENT_ADDED": "task.comment.added",
        "PROJECT_CREATED": "task.project.created",
        "PROJECT_UPDATED": "task.project.updated",
        "PROJECT_DELETED": "task.project.deleted",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_all_lists_every_event_once():
    assert events.ALL == list(declared().values())


def test_it_reacts_only_to_a_person_leaving_the_team():
    assert events.REACTIONS == {"staff.member.terminated": "task.task.release_member"}


@pytest.mark.django_db
def test_react_runs_the_reaction_as_the_platform():
    ana = make_member()
    task = make_task(assigned_to=ana)
    result = events.react(A, "staff.member.terminated", {"id": str(ana.id)})
    assert result.released == 1
    assert Task.objects.get(pk=task.pk).assigned_to is None


def test_react_ignores_an_event_it_has_no_reaction_for():
    assert events.react(A, "staff.member.updated", {"id": "x"}) is None
