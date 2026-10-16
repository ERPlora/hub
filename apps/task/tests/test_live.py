"""Live queries of the task app: which events re-run which query."""

from pathlib import Path

from live.live_registry import live_registry

from apps.task import events, services

EVENTS_SOURCE = Path(events.__file__).read_text()
SERVICES_SOURCE = Path(services.__file__).read_text()

TASK = [
    events.TASK_CREATED,
    events.TASK_UPDATED,
    events.TASK_STATUS_CHANGED,
    events.TASK_COMPLETED,
    events.TASK_ASSIGNED,
    events.TASK_DELETED,
    events.COMMENT_ADDED,
]
PROJECT_CHANGED = [events.PROJECT_UPDATED, events.PROJECT_DELETED]
STAFF = ["staff.member.updated", "staff.member.terminated"]


def task_queries():
    return {name: on for name, on in live_registry.subscribable.items() if name.startswith("task.")}


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_every_query_of_the_app_can_be_followed_live():
    assert set(task_queries()) == {
        "task.task.list",
        "task.task.mine",
        "task.task.detail",
        "task.task.subtasks",
        "task.comment.list",
        "task.project.list",
        "task.project.detail",
    }


def test_each_query_and_its_events():
    queries = task_queries()
    # A task row shows its project's name and colour and its assignee's name.
    for name in ("task.task.list", "task.task.mine", "task.task.detail", "task.task.subtasks"):
        assert queries[name] == [*TASK, *PROJECT_CHANGED, *STAFF], name
    # A reassignment may hide the task (and its thread) from an employee.
    assert queries["task.comment.list"] == [events.COMMENT_ADDED, events.TASK_ASSIGNED, events.TASK_DELETED]
    # A project row counts its tasks and names its owner.
    for name in ("task.project.list", "task.project.detail"):
        assert queries[name] == [
            events.PROJECT_CREATED,
            *PROJECT_CHANGED,
            events.TASK_CREATED,
            events.TASK_UPDATED,
            events.TASK_STATUS_CHANGED,
            events.TASK_DELETED,
            *STAFF,
        ], name


def test_every_event_is_a_literal_of_events_py_recorded_by_a_service():
    for on in task_queries().values():
        for event in on:
            assert f'"{event}"' in EVENTS_SOURCE, event
    for name, value in vars(events).items():
        if name.isupper() and isinstance(value, str) and value.startswith("task."):
            assert f"events.{name}" in SERVICES_SOURCE, name


def test_a_comment_does_not_re_run_the_projects():
    affected = live_registry.affected([events.COMMENT_ADDED])
    assert "task.project.list" not in affected
    assert {"task.comment.list", "task.task.detail", "task.task.list"} <= affected
