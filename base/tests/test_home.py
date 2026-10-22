"""The Home's rules (PLAN-HUB round 2026-10-21), as the old hub's ``setup_status.rs`` had them.

The cases are those of its tests (``crates/runtime/src/setup_status.rs`` at ``9dd38215``): which row a step reads,
when a condition passes, which countries a step applies to, its level and the counters of the document.
"""

from types import SimpleNamespace

import pytest
from live.meta import SetupCheck

from base import home

# --- The row a step reads -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("result", "row"),
    [
        ({"rows": [{"a": 1}, {"a": 2}], "total": 2}, {"a": 1}),
        ({"items": [{"b": 1}]}, {"b": 1}),
        ({"rows": [], "total": 0}, None),
        ({"items": []}, None),
        ({"count": 3}, {"count": 3}),  # a single object is its own row (``*.status``, ``count_to_confirm``)
        ({"configured": False, "series": 0}, {"configured": False, "series": 0}),
    ],
)
def test_the_first_row_of_a_result(result, row):
    assert home.first_row(result) == row


# --- Conditions (``configured_when``) ----------------------------------------------------------------


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
    assert home.truthy(value) is expected


@pytest.mark.parametrize(
    ("value", "text"),
    [("ready", "ready"), (None, ""), (True, "true"), (False, "false"), (3, "3"), (1.5, "1.5")],
)
def test_as_text_compares_laxly(value, text):
    assert home.as_text(value) == text


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
    assert home.passes(row, check) is passes


def test_configured_needs_a_row_and_every_condition():
    checks = [SetupCheck(field="a", truthy=True), SetupCheck(field="b", equals="x")]

    assert home.is_configured({"a": 1, "b": "x"}, checks) is True
    assert home.is_configured({"a": 1, "b": "y"}, checks) is False
    assert home.is_configured(None, checks) is False
    assert home.is_configured({"anything": 0}, []) is True  # no conditions: having a row is enough
    assert home.is_configured(None, []) is False


# --- Countries ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("countries", "hub_country", "applies"),
    [
        ([], "ES", True),
        ([], "", True),
        (["ES"], "ES", True),
        (["es"], "ES", True),
        ([" ES "], "es", True),
        (["ES", "PT"], "PT", True),
        (["ES"], "FR", False),
        (["ES"], "", False),  # a hub without a country gets no national step
    ],
)
def test_a_step_applies_to_its_countries(countries, hub_country, applies):
    assert home.applies_to_country(countries, hub_country) is applies


# --- Level ------------------------------------------------------------------------------------------------


def test_only_bases_list_is_legal():
    assert home.LEGAL_STEPS == frozenset({"invoice.business_identity"})
    assert home.level_of("invoice.business_identity", required=False) == home.LEVEL_LEGAL
    assert home.level_of("invoice.business_identity", required=True) == home.LEVEL_LEGAL
    assert home.level_of("invoice.numbering", required=True) == home.LEVEL_FUNCTIONAL
    assert home.level_of("printing.printer", required=False) == home.LEVEL_RECOMMENDED


# --- The document ---------------------------------------------------------------------------------------


def item(key, state, level=home.LEVEL_FUNCTIONAL, order=500):
    return {"key": key, "state": state, "level": level, "order": order}


def test_the_document_orders_by_order_then_key_and_counts():
    items = [
        item("team", home.STATE_PENDING, home.LEVEL_RECOMMENDED, 80),
        item("b.x", home.STATE_DONE),
        item("invoice.business_identity", home.STATE_PENDING, home.LEVEL_LEGAL, 40),
        item("a.x", home.STATE_PENDING),
        item("apps", home.STATE_UNAVAILABLE, order=10),
        item("invoice.done", home.STATE_DONE, home.LEVEL_LEGAL, 40),
    ]

    document = home.document(items)

    assert [entry["key"] for entry in document["items"]] == [
        "apps",
        "invoice.business_identity",
        "invoice.done",
        "team",
        "a.x",
        "b.x",
    ]
    assert (document["total"], document["pending"], document["unavailable"], document["blocking_pending"]) == (
        6,
        3,
        1,
        1,
    )


def test_an_empty_document():
    assert home.document([]) == {"total": 0, "pending": 0, "unavailable": 0, "blocking_pending": 0, "items": []}


# --- Which modules bring their hooks --------------------------------------------------------------------


def config(label, listed=True):
    return SimpleNamespace(label=label, listed=listed)


def test_only_the_modules_on_in_the_scope_bring_their_hooks(monkeypatch, settings):
    settings.SHOW_UNLISTED_MODULES = True
    monkeypatch.setattr("base.home.module_configs", lambda: [config("sale"), config("stock"), config("demo", False)])

    assert [c.label for c in home.home_modules({"sale", "demo", "base"})] == ["sale", "demo"]


def test_a_module_out_of_the_store_brings_none_unless_the_setting_says_so(monkeypatch, settings):
    """``demo`` (``listed = False``) is the platform's reference, not a customer's app: its example step, panel and
    counter are for the tests and the e2e (``SHOW_UNLISTED_MODULES``, on with ``DEBUG``), never for a customer."""
    monkeypatch.setattr("base.home.module_configs", lambda: [config("sale"), config("demo", False)])

    settings.SHOW_UNLISTED_MODULES = False
    assert [c.label for c in home.home_modules({"sale", "demo"})] == ["sale"]
    settings.SHOW_UNLISTED_MODULES = True
    assert [c.label for c in home.home_modules({"sale", "demo"})] == ["sale", "demo"]


def test_the_setting_is_off_in_production_and_on_with_debug():
    from django.conf import settings

    from config import settings as hub_settings

    assert hub_settings.SHOW_UNLISTED_MODULES == hub_settings.DEBUG
    assert settings.SHOW_UNLISTED_MODULES is True  # the suite runs with the development settings
