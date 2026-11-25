"""The Home's health row: what each app on says of its own (Printing, its receipt station), for who runs the business.

An app declares ``health`` on its ``LiveAppConfig``: the query that says its state (``ok``, ``no_signal`` or
``not_configured`` in the field ``state`` of its first row), the permission it needs, the title of each state and where
to fix it. Base runs the query as the person and adds ``unknown`` when it cannot tell: the query failed or answered a
state it does not know. ``base.E021`` checks the declarations at start.
"""

from types import SimpleNamespace

import pytest
from django.core import checks
from live.context import OperationContext, Scope
from live.operations import Operation, registry
from pydantic import BaseModel

from base import home, home_health

ADMIN = "base.administer_hub"
TITLES = {
    "ok": "Thing ready",
    "no_signal": "Thing not connected",
    "not_configured": "Thing not set up",
    "unknown": "We couldn't check the thing",
}


def declared(**fields):
    return {
        "operation": "things.thing.health",
        "params": {"usage": "receipt"},
        "permission": "things.view",
        "route": "/things/setup",
        "action": "Set up the thing",
        "titles": dict(TITLES),
        **fields,
    }


def app(label="things", health=None, permissions=("things.view",)):
    config = SimpleNamespace(label=label, permissions=dict.fromkeys(permissions, "A phrase"))
    if health is not None:
        config.health = health
    return config


def person(*permissions):
    return OperationContext(scope=Scope("host", "a"), actor="ana", permissions=frozenset(permissions), language="en")


def answers(monkeypatch, row_or_error):
    """Every app's health query answers ``row_or_error`` (raised when it is an exception)."""
    asked = []

    def run_hook(ctx, operation, params):
        asked.append((operation, dict(params)))
        if isinstance(row_or_error, Exception):
            raise row_or_error
        return row_or_error

    monkeypatch.setattr(home.module_hooks, "run_hook", run_hook)
    return asked


# --- What the row says ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "action", "route"),
    [
        ("ok", None, None),
        ("no_signal", "Set up the thing", "/things/setup"),
        ("not_configured", "Set up the thing", "/things/setup"),
    ],
)
def test_an_app_says_its_state_with_its_title_and_where_to_fix_it_only_when_there_is_something_to_fix(
    monkeypatch, state, action, route
):
    asked = answers(monkeypatch, {"state": state})

    items = home_health.health_items(person(ADMIN, "things.view"), [app(health=declared())])

    assert items == [
        {"key": "things", "app": "things", "state": state, "title": TITLES[state], "action": action, "route": route}
    ]
    assert asked == [("things.thing.health", {"usage": "receipt"})]


@pytest.mark.parametrize("answer", [RuntimeError("its query failed"), {"state": "on_fire"}, {}, None])
def test_what_cannot_be_told_is_unknown_never_ok_and_without_an_action(monkeypatch, caplog, answer):
    answers(monkeypatch, answer)

    [item] = home_health.health_items(person(ADMIN, "things.view"), [app(health=declared())])

    assert (item["state"], item["title"], item["action"], item["route"]) == ("unknown", TITLES["unknown"], None, None)
    assert "things.health" in caplog.text


def test_only_who_runs_the_business_and_may_see_the_app_is_told(monkeypatch):
    answers(monkeypatch, {"state": "ok"})
    apps = [app(health=declared())]

    assert home_health.health_items(person("things.view"), apps) == []
    assert home_health.health_items(person(ADMIN), apps) == []
    assert [item["key"] for item in home_health.health_items(person(ADMIN, "things.view"), apps)] == ["things"]


def test_an_app_that_declares_no_health_brings_nothing_and_is_not_asked(monkeypatch):
    asked = answers(monkeypatch, {"state": "ok"})

    assert home_health.health_items(person(ADMIN, "things.view"), [app()]) == []
    assert asked == []


def test_a_health_without_a_permission_is_told_to_who_runs_the_business(monkeypatch):
    answers(monkeypatch, {"state": "no_signal"})
    health = declared()
    del health["permission"], health["params"]

    [item] = home_health.health_items(person(ADMIN), [app(health=health)])

    assert item["state"] == "no_signal"


def test_one_app_failing_leaves_the_others_as_they_are(monkeypatch):
    def run_hook(ctx, operation, params):
        if operation == "broken.thing.health":
            raise RuntimeError("its query failed")
        return {"state": "ok"}

    monkeypatch.setattr(home.module_hooks, "run_hook", run_hook)
    apps = [app("broken", health=declared(operation="broken.thing.health", permission=None)), app(health=declared())]

    states = [(item["key"], item["state"]) for item in home_health.health_items(person(ADMIN, "things.view"), apps)]

    assert states == [("broken", "unknown"), ("things", "ok")]


# --- What an app declares, checked at start (base.E021) --------------------------------------------------------------


class WithState(BaseModel):
    usage: str
    state: str


class WithoutState(BaseModel):
    usage: str


@pytest.fixture
def queries(monkeypatch):
    """``things.thing.health``, whose output has a ``state``, and ``things.thing.count``, whose output has none."""
    for name, output in (("things.thing.health", WithState), ("things.thing.count", WithoutState)):
        op = Operation(
            name=name, kind="query", permission=None, input=BaseModel, output=output, expose_api=False, ai=None,
            fn=lambda ctx, data: {},
        )
        monkeypatch.setitem(registry, name, op)


@pytest.mark.parametrize(
    ("health", "errors"),
    [
        (None, 0),
        (declared(), 0),
        ({key: value for key, value in declared().items() if key not in ("params", "permission")}, 0),
        ("things.thing.health", 1),  # not a mapping
        (declared(operation="nope.thing.health"), 1),  # no such query
        (declared(operation="things.thing.count"), 1),  # its output has no state
        (declared(params=["receipt"]), 1),
        (declared(permission="other.view"), 1),  # not the app's
        (declared(route="things/setup"), 1),  # not a route of the SPA
        (declared(route=None), 1),
        (declared(action=""), 1),
        (declared(titles={**TITLES, "ok": ""}), 1),
        (declared(titles={key: value for key, value in TITLES.items() if key != "unknown"}), 1),
        (declared(titles={**TITLES, "on_fire": "Thing on fire"}), 1),  # a state nobody answers
        (declared(titles=["Thing ready"]), 1),
        (declared(colour="red"), 1),  # a field it does not take
    ],
)
def test_what_an_app_declares_as_its_health_is_checked_at_start(queries, health, errors):
    found = home_health.health_errors([app(health=health)])

    assert len(found) == errors, [error.msg for error in found]
    assert all(error.id == "base.E021" for error in found)


def test_the_check_of_the_health_runs_with_the_others(monkeypatch):
    monkeypatch.setattr("base.home_health.all_live_app_configs", lambda: [app(health="things.thing.health")])

    assert [message.id for message in checks.run_checks(tags=["base"]) if message.id == "base.E021"] == ["base.E021"]


def test_every_app_of_ours_declares_its_health_as_the_check_asks():
    assert home_health.health_errors(home_health.all_live_app_configs()) == []
