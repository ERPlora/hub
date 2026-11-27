"""The Home's steps, as the old hub's ``setup_status.rs`` had them.

The cases are those of its tests (``crates/runtime/src/setup_status.rs`` at ``9dd38215``): which countries a step
applies to, its level and the counters of the document.
"""

import pytest

from base import home


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
        # hub#682: a hub without a country (a demo, ERPlora's own) is in ERPlora's market, Spain
        (["ES"], "", True),
        (["es"], "", True),
        (["PT"], "", False),
    ],
)
def test_a_step_applies_to_its_countries(countries, hub_country, applies):
    assert home.setup_steps.applies_to_country(countries, hub_country) is applies


# --- Level ------------------------------------------------------------------------------------------------


def test_only_bases_list_is_legal():
    assert home.setup_steps.LEGAL_STEPS == frozenset({"invoice.business_identity"})
    assert home.setup_steps.level_of("invoice.business_identity", required=False) == home.setup_steps.LEVEL_LEGAL
    assert home.setup_steps.level_of("invoice.business_identity", required=True) == home.setup_steps.LEVEL_LEGAL
    assert home.setup_steps.level_of("invoice.numbering", required=True) == home.setup_steps.LEVEL_FUNCTIONAL
    assert home.setup_steps.level_of("printing.printer", required=False) == home.setup_steps.LEVEL_RECOMMENDED


# --- The document ---------------------------------------------------------------------------------------


def item(key, state, level=home.setup_steps.LEVEL_FUNCTIONAL, order=500):
    return {"key": key, "state": state, "level": level, "order": order}


def test_the_document_orders_by_order_then_key_and_counts():
    items = [
        item("team", home.setup_steps.STATE_PENDING, home.setup_steps.LEVEL_RECOMMENDED, 80),
        item("b.x", home.setup_steps.STATE_DONE),
        item("invoice.business_identity", home.setup_steps.STATE_PENDING, home.setup_steps.LEVEL_LEGAL, 40),
        item("a.x", home.setup_steps.STATE_PENDING),
        item("apps", home.setup_steps.STATE_UNAVAILABLE, order=10),
        item("invoice.done", home.setup_steps.STATE_DONE, home.setup_steps.LEVEL_LEGAL, 40),
    ]

    document = home.setup_steps.document(items)

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
    assert home.setup_steps.document([]) == {
        "title": "Finish setting up your business",
        "total": 0,
        "pending": 0,
        "unavailable": 0,
        "blocking_pending": 0,
        "items": [],
    }
