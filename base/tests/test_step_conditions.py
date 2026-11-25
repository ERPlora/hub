"""When a step's condition (``configured_when``) passes, as the old hub's ``setup_status.rs`` had it: the cases
are those of its tests (``crates/runtime/src/setup_status.rs`` at ``9dd38215``).
"""

import pytest
from live.meta import SetupCheck

from base import home


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        (True, True),
        (False, False),
        (0, False),
        (0.0, False),
        (3, True),
        (-1, True),
        ("", False),
        ("   ", False),
        ("0", False),
        ("false", False),
        ("FALSE", False),
        (" x ", True),
        ([], False),
        ([0], True),
        ({}, True),  # an object is truthy, as in the old hub
    ],
)
def test_truthy_is_the_old_hubs(value, expected):
    assert home.step_conditions.truthy(value) is expected


@pytest.mark.parametrize(
    ("value", "text"),
    [("ready", "ready"), (None, ""), (True, "true"), (False, "false"), (3, "3"), (1.5, "1.5")],
)
def test_as_text_compares_laxly(value, text):
    assert home.step_conditions.as_text(value) == text


@pytest.mark.parametrize(
    ("row", "check", "passes"),
    [
        ({"active": 2}, SetupCheck(field="active", truthy=True), True),
        ({"active": 0}, SetupCheck(field="active", truthy=True), False),
        ({"active": 0}, SetupCheck(field="active", truthy=False), True),
        ({}, SetupCheck(field="active", truthy=False), True),  # a missing field is null
        ({}, SetupCheck(field="active", truthy=True), False),
        ({"state": "ready"}, SetupCheck(field="state", equals="ready"), True),
        ({"state": "draft"}, SetupCheck(field="state", equals="ready"), False),
        ({"series": 2}, SetupCheck(field="series", equals="2"), True),  # compared as text
        ({"series": 2}, SetupCheck(field="series", equals=2), True),
        ({"on": True}, SetupCheck(field="on", equals=True), True),
        ({"on": False}, SetupCheck(field="on", equals=True), False),
        ({"on": 0}, SetupCheck(field="on", equals=0), True),
        ({"active": 2}, SetupCheck(field="active"), False),  # a half-written condition never passes
    ],
)
def test_a_condition_on_the_first_row(row, check, passes):
    assert home.step_conditions.passes(row, check) is passes


def test_configured_needs_a_row_and_every_condition():
    checks = [SetupCheck(field="a", truthy=True), SetupCheck(field="b", equals="x")]

    assert home.step_conditions.is_configured({"a": 1, "b": "x"}, checks) is True
    assert home.step_conditions.is_configured({"a": 1, "b": "y"}, checks) is False
    assert home.step_conditions.is_configured(None, checks) is False
    assert home.step_conditions.is_configured({"anything": 0}, []) is True  # no conditions: having a row is enough
    assert home.step_conditions.is_configured(None, []) is False
