"""The server says what an automation does in the words of the Automations screens (the assistant's card is drawn on
the server, hub#2300). What each trigger and each step is called is written once, in
``frontend/lib/phrasing-cases.json``: this file and the screens' ``phrasing-cases.test.ts`` both read it, so a phrase
that changes on one side fails on the other."""

import json
from pathlib import Path

import pytest
from django.utils import translation

from apps.flow.phrasing import Phrasing, describe_clause, describe_step, describe_trigger, event_label, path_label

EN = Phrasing("en")
CASES = json.loads((Path(__file__).resolve().parents[1] / "frontend/lib/phrasing-cases.json").read_text(encoding="utf-8"))
TASK = {"id": "s1", "kind": "command", "operation": "task.task.create", "params": {}}


def _said(shared: dict) -> str:
    return f"{shared['language']}: {shared['said']}"


@pytest.mark.parametrize("shared", CASES["triggers"], ids=_said)
def test_each_way_of_starting_in_words(shared):
    with translation.override(shared["language"]):  # an app is named in the language of the request
        assert describe_trigger(shared["trigger"], Phrasing(shared["language"])) == shared["said"]


def test_no_trigger_starts_only_by_hand():
    assert describe_trigger(None, EN) == "Only when you press Run"


def test_a_trigger_that_runs_once_says_its_moment_as_given():
    assert describe_trigger({"kind": "at", "at": "x"}, EN, at="Nov 2, 2026, 10:00 AM") == "Once, on Nov 2, 2026, 10:00 AM"


def test_spanish_says_the_weekday_in_spanish():
    trigger = {"kind": "schedule", "every": "week", "weekday": 4, "time": "18:00"}
    assert describe_trigger(trigger, Phrasing("es")) == "Todos los viernes a las 18:00"


def test_an_event_without_a_phrase_is_composed_from_its_app_and_what_happened():
    assert event_label("customer.badge.deleted", EN) == "Customers: badge deleted"
    assert event_label("spa.sauna.overheated", EN) == "Sauna overheated"


@pytest.mark.parametrize("shared", CASES["steps"], ids=_said)
def test_each_kind_of_step_in_one_line(shared):
    steps = (*shared.get("steps", ()), shared["step"])
    assert describe_step(shared["step"], Phrasing(shared["language"], steps)) == shared["said"]


def test_a_comparison_names_its_data_its_operator_and_its_value():
    assert describe_clause("input.customer_id", "exists", True, EN) == "Customer present: yes"
    assert describe_clause("input.party_size", "in", [6, 8], EN) == "Party size one of 6, 8"


def test_a_comparison_with_another_datum_names_that_datum_never_its_path():
    clause = describe_clause("input.total", "eq", "input.customer_id", EN)
    assert "Customer" in clause and "input." not in clause
    assert "input." not in describe_clause("input.total", "in", ["input.customer_id", 5], EN)


def test_a_path_says_where_it_comes_from():
    p = Phrasing("en", (TASK,))
    assert path_label("input.customer_name", p) == "Customer name"
    assert path_label("input.customer.name", p) == "Customer › Name"
    assert path_label("steps.s1.number", p) == "1. Create a task › Number"
    assert path_label("steps.s9.id", p) == "steps.s9.id"
    assert path_label("secret.API_KEY", p) == "Secret «API_KEY»"
