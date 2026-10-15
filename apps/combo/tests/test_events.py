"""The combo app's events (``combo.<entity>.<fact>``) and its reaction to Inventory's.

There is no outbox relay yet (phase 2 runs it in the worker); a reaction is tested by handing ``react``
the event as the relay will: its name, its scope and its payload.
"""

import re

import pytest
from live.operations import NAME_RE

from apps.combo import events
from apps.combo.models import ChoiceOption

from .conftest import A, make_combo, make_group, make_option, make_product

PAST_FACT = re.compile(r"^combo\.[a-z_]+\.[a-z_]+ed$")


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str) and value.startswith("combo.")
    }


def test_the_events_of_the_workbook():
    assert declared() == {
        "COMBO_CREATED": "combo.combo.created",
        "COMBO_UPDATED": "combo.combo.updated",
        "COMBO_DELETED": "combo.combo.deleted",
        "GROUP_CREATED": "combo.group.created",
        "GROUP_UPDATED": "combo.group.updated",
        "GROUP_DELETED": "combo.group.deleted",
        "GROUP_REORDERED": "combo.group.reordered",
        "OPTION_CREATED": "combo.option.created",
        "OPTION_UPDATED": "combo.option.updated",
        "OPTION_DELETED": "combo.option.deleted",
        "OPTION_REORDERED": "combo.option.reordered",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_all_lists_every_event_once():
    assert events.ALL == list(declared().values())


def test_inventorys_product_events_are_its_own_names():
    assert events.PRODUCT_UPDATED == "inventory.product.updated"
    assert events.PRODUCT_DELETED == "inventory.product.deleted"


def test_it_reacts_only_to_a_product_deleted_in_inventory():
    assert events.REACTIONS == {
        "inventory.product.deleted": "combo.option.drop_product"
    }


@pytest.mark.django_db
def test_react_runs_the_reaction_as_the_platform():
    flan = make_product("Flan", sku="FLAN")
    make_option(make_group(make_combo()), flan)
    result = events.react(
        A,
        "inventory.product.deleted",
        {"id": str(flan.id), "sku": "FLAN", "name": "Flan"},
    )
    assert result.dropped == 1
    assert ChoiceOption.objects.count() == 0


def test_react_ignores_an_event_it_has_no_reaction_for():
    assert events.react(A, "inventory.product.updated", {"id": "x"}) is None
