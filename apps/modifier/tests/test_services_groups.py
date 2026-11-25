"""The writes on a modifier group (MODIFIER-F02, F03), each one a transaction with its events in the outbox."""

import uuid

import pytest
from live.errors import Conflict, InvalidPayload, NotFound

from apps.modifier.models import ModifierGroup, ModifierLink, ModifierOption
from apps.modifier.schemas.groups import GroupPatchIn
from apps.modifier.services.groups import update_group

from .conftest import HUB_DB, ctx_for, events, group, make_product, option, refusal, run

pytestmark = HUB_DB


def test_creating_a_group_keeps_what_was_typed_and_says_so():
    created = group(
        "Doneness", kitchen_name="POINT", min_choices=1, max_choices=1, sort_order=10
    )
    assert (
        created.name,
        created.kitchen_name,
        created.min_choices,
        created.max_choices,
    ) == ("Doneness", "POINT", 1, 1)
    assert (created.is_required, created.allow_repeat, created.sort_order) == (
        True,
        False,
        10,
    )
    assert (created.option_count, created.default_count, created.link_count) == (
        0,
        0,
        0,
    )
    row = ModifierGroup.objects.get(pk=created.id)
    assert (row.created_by, row.updated_by) == ("tester", "tester")
    assert events("modifier.group.created") == [
        {"id": str(created.id), "name": "Doneness"}
    ]


def test_a_group_name_taken_whatever_the_case_is_a_409_on_the_name():
    group("Sauces")
    with pytest.raises(Conflict) as error:
        group("  sauces ")
    assert refusal(error) == (
        "Conflict",
        "modifier.group_name_taken",
        {"name": "There is already a group with that name."},
    )
    assert ModifierGroup.objects.count() == 1


def test_changing_a_group_keeps_what_is_not_sent():
    created = group(
        "Sauces",
        kitchen_name="SAUCE",
        min_choices=1,
        max_choices=3,
        allow_repeat=True,
        sort_order=5,
    )
    changed = run(
        "modifier.group.update",
        {"group": "sauces", "max_choices": 2},
        role="hub_manager",
    )
    assert (
        changed.name,
        changed.kitchen_name,
        changed.min_choices,
        changed.max_choices,
    ) == ("Sauces", "SAUCE", 1, 2)
    assert (changed.allow_repeat, changed.sort_order) == (True, 5)
    assert events("modifier.group.updated") == [
        {"id": str(created.id), "name": "Sauces"}
    ]
    # Nothing changes, nothing is said.
    run("modifier.group.update", {"id": str(created.id), "name": "Sauces"})
    assert len(events("modifier.group.updated")) == 1


def test_a_change_that_leaves_the_maximum_below_the_minimum_is_a_422_on_the_field_that_broke_it():
    group("Sauces", min_choices=1, max_choices=2)
    with pytest.raises(InvalidPayload) as error:
        run("modifier.group.update", {"group": "Sauces", "min_choices": 3})
    assert error.value.fields == {
        "min_choices": "The maximum cannot be below the minimum (0 = no ceiling)."
    }
    group("Extras", min_choices=2, max_choices=3)
    with pytest.raises(InvalidPayload) as error:
        run("modifier.group.update", {"group": "Extras", "max_choices": 1})
    assert error.value.fields == {
        "max_choices": "The maximum cannot be below the minimum (0 = no ceiling)."
    }
    # 0 is no ceiling: that one is fine.
    assert (
        run(
            "modifier.group.update",
            {"group": "Sauces", "max_choices": 0, "min_choices": 5},
        ).min_choices
        == 5
    )


def test_renaming_a_group_to_a_taken_name_is_a_409():
    group("Sauces")
    group("Extras")
    with pytest.raises(Conflict) as error:
        run("modifier.group.update", {"group": "Extras", "name": "SAUCES"})
    assert error.value.code == "modifier.group_name_taken"
    # Its own name in other letters is not another's.
    assert update_group(ctx_for(), GroupPatchIn(group="Extras", name="EXTRAS")).name == "EXTRAS"


def test_a_group_that_does_not_exist_is_a_404():
    for name, data in (
        ("modifier.group.update", {"id": str(uuid.uuid7()), "name": "X"}),
        ("modifier.group.delete", {"group": "Nowhere"}),
    ):
        with pytest.raises(NotFound) as error:
            run(name, data)
        assert error.value.message == "This group does not exist."
    assert events("modifier.group.updated") == events("modifier.group.deleted") == []


def test_deleting_a_group_takes_its_options_and_links_in_one_step():
    created = group("Sauces")
    option(name="Ketchup")
    run(
        "modifier.link.attach",
        {"group": "Sauces", "product_id": str(make_product().id)},
    )
    deleted = run("modifier.group.delete", {"group": "Sauces"})
    assert deleted.id == created.id
    assert (
        ModifierGroup.objects.count(),
        ModifierOption.objects.count(),
        ModifierLink.objects.count(),
    ) == (0, 0, 0)
    assert events("modifier.group.deleted") == [
        {"id": str(created.id), "name": "Sauces"}
    ]
