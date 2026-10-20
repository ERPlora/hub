"""The document of an automation (WORKBOOK «Para quien lo mantiene»): data paths, ``{{…}}`` templates,
conditions, schedules and the permissions its steps ask for. Pure: no database.

Cases from the old module (``ui/lib/flow-doc.ts``, ``schemas/draft_propose.json``, ``docs/concepts.md``):
a path keeps its type, a template is always text, a field that is not there never matches except with
``exists: false``, money is in cents, a wait counts from now.
"""

import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.flow import document as doc

MADRID = ZoneInfo("Europe/Madrid")
DATA = {
    "input": {
        "total": 12500,
        "customer_id": "c-1",
        "customer_name": "Ana López",
        "party_size": 6,
        "tags": ["vip", "new"],
        "empty": None,
        "nested": {"city": "Madrid"},
        "amount_text": "10.50",
        "flag": True,
    },
    "steps": {"s1": {"id": "t-9", "number": "TSK-1", "found": True, "count": 3}},
}


# Paths


@pytest.mark.parametrize(
    "text",
    ["input.total", "input.nested.city", "steps.s1.id", "input.a_b2"],
)
def test_a_path_starts_with_a_root_and_a_dot(text):
    assert doc.is_path(text)


@pytest.mark.parametrize(
    "text",
    [
        "input",
        "input.",
        "total",
        "Input.total",
        "event.total",
        "input.tags.0x",
        "input total",
        "",
        "steps.s1 .id",
        "100",
    ],
)
def test_anything_else_is_text(text):
    assert not doc.is_path(text)


def test_a_path_with_an_index_is_not_a_path():
    # The language cannot index a list (old module, docs/limits.md): «lines.0.total» is not offered.
    assert not doc.is_path("input.tags.0")


def test_lookup_finds_a_value_and_says_when_it_is_missing():
    assert doc.lookup("input.total", DATA) == (True, 12500)
    assert doc.lookup("input.nested.city", DATA) == (True, "Madrid")
    assert doc.lookup("steps.s1.id", DATA) == (True, "t-9")
    assert doc.lookup("input.empty", DATA) == (True, None)
    assert doc.lookup("input.missing", DATA) == (False, None)
    assert doc.lookup("input.total.deeper", DATA) == (False, None)
    assert doc.lookup("steps.s2.id", DATA) == (False, None)


# Values: literal, path (keeps its type) or template (always text)


def test_a_literal_stays_as_it_is():
    assert doc.resolve("Call them", DATA) == "Call them"
    assert doc.resolve(10000, DATA) == 10000
    assert doc.resolve(True, DATA) is True
    assert doc.resolve(None, DATA) is None


def test_a_path_keeps_the_type_of_what_it_points_at():
    assert doc.resolve("input.total", DATA) == 12500
    assert doc.resolve("input.tags", DATA) == ["vip", "new"]
    assert doc.resolve("input.missing", DATA) is None


def test_a_template_is_always_text_and_a_missing_field_is_empty():
    assert (
        doc.resolve("Call {{input.customer_name}} ({{input.party_size}})", DATA)
        == "Call Ana López (6)"
    )
    assert doc.resolve("{{input.total}}", DATA) == "12500"
    assert doc.resolve("Hi {{ input.missing }}!", DATA) == "Hi !"
    assert doc.resolve("Task {{steps.s1.number}}", DATA) == "Task TSK-1"


def test_dicts_and_lists_are_resolved_inside():
    assert doc.resolve({"a": "input.total", "b": ["input.customer_id", "x"]}, DATA) == {
        "a": 12500,
        "b": ["c-1", "x"],
    }


def test_references_lists_every_path_a_value_uses():
    value = {
        "title": "Call {{input.customer_name}}",
        "id": "steps.s1.id",
        "n": 3,
        "l": ["input.total"],
    }
    assert doc.references(value) == [
        "input.customer_name",
        "steps.s1.id",
        "input.total",
    ]


def test_references_of_a_template_with_something_that_is_no_path():
    assert doc.references("Hi {{foo}} and {{input.x}}") == ["foo", "input.x"]


# Conditions: every comparison at once; a missing field never matches except exists: false


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        ({"input.total": {"gte": 10000}}, True),
        ({"input.total": {"gt": 12500}}, False),
        ({"input.total": {"lt": 20000, "gt": 100}}, True),
        ({"input.total": {"lte": 12500}}, True),
        ({"input.total": {"eq": 12500}}, True),
        ({"input.total": {"eq": "12500"}}, True),
        ({"input.amount_text": {"gt": 10}}, True),
        ({"input.total": {"neq": 1}}, True),
        ({"input.customer_id": {"exists": True}}, True),
        ({"input.empty": {"exists": True}}, False),
        ({"input.empty": {"exists": False}}, True),
        ({"input.missing": {"exists": False}}, True),
        ({"input.missing": {"neq": 1}}, False),
        ({"input.missing": {"lt": 1}}, False),
        ({"input.customer_name": {"contains": "lópez"}}, True),
        ({"input.tags": {"contains": "vip"}}, True),
        ({"input.tags": {"contains": "old"}}, False),
        ({"input.party_size": {"in": [4, 6, 8]}}, True),
        ({"input.party_size": {"in": [4]}}, False),
        ({"input.flag": {"eq": True}}, True),
        ({"input.flag": {"eq": 1}}, False),
        ({"input.nested.city": {"eq": "Madrid"}}, True),
        ({"steps.s1.found": {"eq": True}, "input.total": {"gte": 10000}}, True),
        ({"steps.s1.found": {"eq": False}, "input.total": {"gte": 10000}}, False),
        ({"input.customer_name": {"gt": 5}}, False),
    ],
)
def test_conditions(condition, expected):
    assert doc.holds(condition, DATA) is expected


def test_the_failed_comparisons_are_named():
    condition = {"input.total": {"gte": 20000}, "input.customer_id": {"exists": True}}
    assert doc.failed_clauses(condition, DATA) == [
        {"path": "input.total", "op": "gte", "value": 20000}
    ]


def test_an_empty_condition_always_holds():
    assert doc.holds({}, DATA) is True


def test_a_condition_is_readable_only_with_paths_to_known_comparisons():
    # hub#1766: what the engine cannot read is said, never evaluated as «does not hold».
    assert doc.readable({}) is True
    assert doc.readable({"input.total": {"gt": 100, "lte": 500}}) is True
    assert doc.readable({"input.total": {"bigger": 100}}) is False
    assert doc.readable({"total": {"gt": 100}}) is False
    assert doc.readable({"input.total": {}}) is False
    assert doc.readable({"input.total": 100}) is False
    assert doc.readable(["input.total"]) is False


def test_number_reads_numbers_and_numeric_text_but_not_booleans():
    assert doc.number(5) == Decimal(5)
    assert doc.number(2.5) == Decimal("2.5")
    assert doc.number("10.50") == Decimal("10.50")
    assert doc.number(True) is None
    assert doc.number("ten") is None
    assert doc.number(None) is None


# Schedules, in the business's time zone


def at(*args):
    return dt.datetime(*args, tzinfo=MADRID)


def test_every_day_at_a_time():
    schedule = {"every": "day", "time": "09:00"}
    assert doc.next_fire(schedule, at(2026, 10, 15, 8, 0), MADRID) == at(
        2026, 10, 15, 9, 0
    )
    assert doc.next_fire(schedule, at(2026, 10, 15, 9, 0), MADRID) == at(
        2026, 10, 16, 9, 0
    )
    assert doc.next_fire(schedule, at(2026, 10, 15, 9, 30), MADRID) == at(
        2026, 10, 16, 9, 0
    )


def test_every_week_on_a_day_monday_being_zero():
    friday_six = {"every": "week", "weekday": 4, "time": "18:00"}
    # 2026-10-15 is a Thursday.
    assert doc.next_fire(friday_six, at(2026, 10, 15, 12, 0), MADRID) == at(
        2026, 10, 16, 18, 0
    )
    assert doc.next_fire(friday_six, at(2026, 10, 16, 18, 0), MADRID) == at(
        2026, 10, 23, 18, 0
    )


def test_every_month_on_a_day_skips_the_months_without_it():
    the_31st = {"every": "month", "day": 31, "time": "07:30"}
    assert doc.next_fire(the_31st, at(2026, 10, 15, 0, 0), MADRID) == at(
        2026, 10, 31, 7, 30
    )
    assert doc.next_fire(the_31st, at(2026, 10, 31, 8, 0), MADRID) == at(
        2026, 12, 31, 7, 30
    )


def test_a_schedule_keeps_its_wall_clock_across_the_change_of_time():
    # Spain goes back an hour on 2026-10-25: 09:00 stays 09:00, local.
    schedule = {"every": "day", "time": "09:00"}
    after = doc.next_fire(schedule, at(2026, 10, 24, 10, 0), MADRID)
    assert after == dt.datetime(2026, 10, 25, 9, 0, tzinfo=MADRID)
    assert after.utcoffset() == dt.timedelta(hours=1)


# Permissions a document asks for


def test_required_grants_are_the_actions_and_reads_of_its_steps_once_each_in_order():
    steps = [
        {
            "id": "s1",
            "kind": "query",
            "operation": "customer.customer.detail",
            "params": {},
        },
        {"id": "s2", "kind": "condition", "when": {"steps.s1.found": {"eq": True}}},
        {"id": "s3", "kind": "delay", "seconds": 60},
        {"id": "s4", "kind": "command", "operation": "task.task.create", "params": {}},
        {"id": "s5", "kind": "command", "operation": "task.task.create", "params": {}},
        {"id": "s6", "kind": "command", "operation": "", "params": {}},
    ]
    assert doc.required_grants(steps) == [
        "customer.customer.detail",
        "task.task.create",
    ]


def test_the_limits():
    assert doc.MAX_STEPS == 50
    assert doc.MIN_DELAY_SECONDS == 60
    assert doc.MAX_DELAY_SECONDS == 30 * 24 * 3600
    assert doc.MAX_CHAIN == 8
    assert doc.OPERATORS == (
        "eq",
        "neq",
        "in",
        "exists",
        "contains",
        "gt",
        "gte",
        "lt",
        "lte",
    )
