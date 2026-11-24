"""The server says what an automation does in the words of the Automations screens: the same phrases, for the same
cases, as ``frontend/lib/phrasing.test.ts`` expects of the screens (the assistant's card is drawn on the server,
hub#2300)."""

import pytest

from apps.flow.phrasing import Phrasing, describe_clause, describe_step, describe_trigger, event_label, path_label

EN = Phrasing("en")
TASK = {"id": "s1", "kind": "command", "operation": "task.task.create", "params": {}}


@pytest.mark.parametrize(
    ("trigger", "said"),
    [
        ({"kind": "event", "event": "sale.sale.completed"}, "When a sale is charged"),
        ({"kind": "event", "event": ""}, "Choose what has to happen for it to start"),
        ({"kind": "manual"}, "Only when you press Run"),
        (None, "Only when you press Run"),
        ({"kind": "schedule", "every": "day", "time": "09:00"}, "Every day at 09:00"),
        ({"kind": "schedule", "every": "week", "weekday": 4, "time": "18:00"}, "Every Friday at 18:00"),
        ({"kind": "schedule", "every": "month", "day": 1, "time": "08:30"}, "Every month on day 1 at 08:30"),
        ({"kind": "at"}, "Once, on a date you choose"),
    ],
)
def test_each_way_of_starting_in_words(trigger, said):
    assert describe_trigger(trigger, EN) == said


def test_a_trigger_that_runs_once_says_its_moment_as_given():
    assert describe_trigger({"kind": "at", "at": "x"}, EN, at="Nov 2, 2026, 10:00 AM") == "Once, on Nov 2, 2026, 10:00 AM"


def test_spanish_says_the_weekday_in_spanish():
    trigger = {"kind": "schedule", "every": "week", "weekday": 4, "time": "18:00"}
    assert describe_trigger(trigger, Phrasing("es")) == "Todos los viernes a las 18:00"


def test_an_event_without_a_phrase_is_composed_from_its_app_and_what_happened():
    assert event_label("customer.badge.deleted", EN) == "Customers: badge deleted"
    assert event_label("spa.sauna.overheated", EN) == "Sauna overheated"


@pytest.mark.parametrize(
    ("step", "said"),
    [
        (TASK, "Create a task"),
        ({**TASK, "operation": ""}, "Choose what this step does"),
        ({"id": "s1", "kind": "query", "operation": "customer.customer.detail", "params": {}}, "Look up: Read a customer"),
        ({"id": "s1", "kind": "command", "operation": "spa.sauna.heat", "params": {}}, "heat (sauna)"),
        ({"id": "s2", "kind": "condition", "when": {"input.total": {"gte": 10000}}}, "Total greater than or equal to 10000"),
        ({"id": "s2", "kind": "condition", "when": {}}, "nothing yet"),
        ({"id": "s3", "kind": "delay", "seconds": 86400}, "Wait 1 day"),
        ({"id": "s3", "kind": "delay", "seconds": 7200}, "Wait 2 hours"),
        ({"id": "s4", "kind": "http", "url": "https://api.example.com/orders/{{input.id}}"}, "Call api.example.com"),
        ({"id": "s4", "kind": "http", "url": "http://api.example.com"}, "Call another system"),
        ({"id": "s5", "kind": "ask", "title": "Approve {{input.total}}?"}, "Ask: Approve «Total»?"),
        ({"id": "s5", "kind": "ask", "title": ""}, "Ask someone first"),
        ({"id": "s6", "kind": "assistant", "prompt": "input.customer_name"}, "Ask the assistant: «Customer name»"),
        ({"id": "s6", "kind": "assistant", "prompt": ""}, "Ask the assistant"),
    ],
)
def test_each_kind_of_step_in_one_line(step, said):
    assert describe_step(step, EN) == said


def test_a_wait_of_a_minute_in_spanish():
    assert describe_step({"id": "s3", "kind": "delay", "seconds": 60}, Phrasing("es")) == "Esperar 1 minuto"


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
