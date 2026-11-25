"""The catalog of what automations can use, read in parts (FLOW-F17): a business with many apps has a catalog far
longer than the assistant can read in one go, so the assistant first reads the names of the apps it needs and then
reads whole, with every datum each one asks for, only the events and actions it will use."""

import json

import pytest
from live.assistant import running
from live.assistant.tools import MAX_RESULT_CHARS
from live.operations import get

from .conftest import HOST, HUB_DB, A, ctx_for, run

pytestmark = HUB_DB


def told_to_the_assistant(data: dict) -> str:
    """What the assistant reads of ``flow.catalog.read`` with ``data``, as its turn tells it a tool's result."""
    outcome = running.run_tool(ctx_for(language="es"), get("flow.catalog.read"), json.dumps(data))
    assert outcome.outcome == "ok", outcome.content
    return outcome.content


def test_the_whole_catalog_of_a_business_with_many_apps_does_not_fit_in_what_the_assistant_reads():
    whole = run("flow.catalog.read")
    assert len({action.app for action in whole.actions}) >= 20
    assert len(whole.model_dump_json()) > MAX_RESULT_CHARS


def test_the_assistant_finds_the_till_and_the_task_by_their_names_and_reads_them_whole():
    found = json.loads(told_to_the_assistant({"apps": ["cash_register", "task"], "only_names": True}))
    assert "cut" not in found
    assert "cash_register.session.closed" in {event["name"] for event in found["events"]}
    assert "task.task.create" in found["action_names"]
    catalog = json.loads(told_to_the_assistant({"names": ["cash_register.session.closed", "task.task.create"]}))
    assert "cut" not in catalog
    assert [event["name"] for event in catalog["events"]] == ["cash_register.session.closed"]
    [action] = catalog["actions"]
    assert {field["name"] for field in action["fields"]} >= {"title", "priority"}


def test_names_bring_only_those_events_and_actions():
    catalog = run("flow.catalog.read", {"names": ["cash_register.session.closed", "task.task.create"]})
    assert [event.name for event in catalog.events] == ["cash_register.session.closed"]
    assert [action.name for action in catalog.actions] == ["task.task.create"]


def test_apps_bring_every_event_and_action_of_those_apps_and_nothing_else():
    whole = run("flow.catalog.read")
    part = run("flow.catalog.read", {"apps": ["task"]})
    assert part.events == [event for event in whole.events if event.app == "task"]
    assert part.actions == [action for action in whole.actions if action.app == "task"]
    assert part.events and part.actions


def test_only_names_bring_the_events_and_the_action_names_of_those_apps_and_no_action_whole():
    whole = run("flow.catalog.read")
    found = run("flow.catalog.read", {"apps": ["task"], "only_names": True})
    assert found.events == [event for event in whole.events if event.app == "task"]
    assert found.action_names == [action.name for action in whole.actions if action.app == "task"]
    assert found.events and found.action_names
    assert (found.actions, whole.action_names) == ([], [])


def test_the_names_of_every_app_read_on_its_own_come_whole_to_the_assistant():
    found = run("flow.catalog.read", {"only_names": True}, ctx=ctx_for(language="es"))
    for app in {event.app for event in found.events} | {name.split(".", 1)[0] for name in found.action_names}:
        part = found.model_copy(
            update={
                "events": [event for event in found.events if event.app == app],
                "action_names": [name for name in found.action_names if name.startswith(f"{app}.")],
            }
        )
        assert len(part.model_dump_json()) <= MAX_RESULT_CHARS, app


def test_every_action_read_by_its_name_comes_whole_to_the_assistant():
    whole = run("flow.catalog.read", ctx=ctx_for(language="es"))
    for action in whole.actions:
        part = whole.model_copy(update={"events": [], "actions": [action]})
        assert len(part.model_dump_json()) <= MAX_RESULT_CHARS, action.name


def test_saying_no_part_reads_the_whole_catalog_as_the_editor_does():
    assert run("flow.catalog.read", {"apps": None, "names": None}) == run("flow.catalog.read")


def test_a_part_that_names_nothing_here_brings_nothing_and_still_says_which_apps_are_off():
    run("base.app.disable", {"app": "task"})
    catalog = run("flow.catalog.read", {"apps": ["task"], "names": ["task.task.create"]})
    assert (catalog.events, catalog.actions) == ([], [])
    assert "task" in [app.app for app in catalog.off_apps]


@pytest.fixture
def owner_client(client, make_user):
    client.force_login(make_user("boss", host=A.key, role="hub_owner"))
    return client


def test_the_route_reads_the_parts_it_is_asked_for(owner_client):
    answer = owner_client.get(
        "/api/flow/catalog", {"apps": ["cash_register"], "names": ["task.task.create"]}, HTTP_HOST=HOST
    )
    assert answer.status_code == 200, answer.content
    assert {action["app"] for action in answer.json()["actions"]} == {"cash_register", "task"}


def test_the_route_reads_only_the_names_when_asked(owner_client):
    answer = owner_client.get("/api/flow/catalog", {"apps": ["task"], "only_names": "true"}, HTTP_HOST=HOST)
    assert answer.status_code == 200, answer.content
    assert answer.json()["actions"] == []
    assert "task.task.create" in answer.json()["action_names"]
