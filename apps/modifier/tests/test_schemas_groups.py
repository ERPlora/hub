"""The schemas of the groups of options: what one is named, made and changed with (422 per field)."""

import uuid

from apps.modifier.schemas.groups import GroupIn, GroupPatchIn, GroupRefIn

from .schema_checks import refused


def test_a_new_group_takes_the_old_defaults_and_strips_its_texts():
    group = GroupIn.model_validate({"name": "  Sauces  ", "kitchen_name": " SAUCE "})
    assert group.model_dump() == {
        "name": "Sauces",
        "kitchen_name": "SAUCE",
        "min_choices": 0,
        "max_choices": 0,
        "allow_repeat": False,
        "sort_order": 0,
    }


def test_a_group_needs_a_name_and_choices_between_0_and_50():
    assert refused(GroupIn, name="") == {"name"}
    assert refused(GroupIn, name="x" * 256) == {"name"}
    assert refused(GroupIn, name="A", min_choices=51) == {"min_choices"}
    assert refused(GroupIn, name="A", max_choices=-1) == {"max_choices"}
    assert refused(GroupIn, name="A", sort_order=-1) == {"sort_order"}


def test_a_maximum_below_the_minimum_is_refused_on_the_maximum():
    assert refused(GroupIn, name="A", min_choices=2, max_choices=1) == {"max_choices"}
    assert (
        GroupIn.model_validate(
            {"name": "A", "min_choices": 2, "max_choices": 0}
        ).max_choices
        == 0
    )


def test_a_new_group_refuses_a_field_it_does_not_have():
    assert refused(GroupIn, name="A", required=True) == {"required"}


def test_a_group_is_named_by_its_id_or_its_name():
    assert GroupRefIn.model_validate({"group": "Sauces"}).group == "Sauces"
    assert GroupRefIn.model_validate({"id": str(uuid.uuid7())}).group is None
    assert refused(GroupRefIn) == {"__all__"}


def test_a_group_patch_sends_only_what_changes():
    patch = GroupPatchIn.model_validate({"group": "Sauces", "max_choices": 2})
    assert patch.model_dump(exclude_unset=True) == {"group": "Sauces", "max_choices": 2}
    assert refused(GroupPatchIn, group="Sauces", name="") == {"name"}
