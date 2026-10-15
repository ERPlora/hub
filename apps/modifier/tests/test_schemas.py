"""The modifier app's schemas: what a route, the assistant and an API key may send (422 per field)."""

import uuid

import pytest
from pydantic import ValidationError

from apps.modifier.models import MAX_DELTA
from apps.modifier.schemas import (
    DropIn,
    GroupIn,
    GroupListIn,
    GroupPatchIn,
    GroupRefIn,
    LinkIn,
    LinkListIn,
    LinkRefIn,
    OptionIn,
    OptionListIn,
    OptionPatchIn,
    OptionRefIn,
    ResolveIn,
    TargetIn,
)


def fields_of(error: ValidationError) -> set[str]:
    return {
        ".".join(str(part) for part in item["loc"]) or "__all__"
        for item in error.errors()
    }


def refused(schema, **data) -> set[str]:
    with pytest.raises(ValidationError) as caught:
        schema.model_validate(data)
    return fields_of(caught.value)


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


def test_lists_page_by_at_most_100_and_refuse_an_unknown_filter():
    assert GroupListIn.model_validate({}).model_dump() == {
        "limit": 50,
        "offset": 0,
        "search": None,
        "name": None,
        "required": None,
        "sort": "sort_order",
    }
    assert refused(GroupListIn, limit=101) == {"limit"}
    assert refused(GroupListIn, colour="red") == {"colour"}
    assert refused(GroupListIn, sort="price") == {"sort"}
    assert refused(OptionListIn, limit=0) == {"limit"}
    assert refused(LinkListIn, offset=-1) == {"offset"}


def test_an_option_names_its_group_and_carries_a_signed_supplement():
    option = OptionIn.model_validate(
        {"group": "Extras", "name": "Cheese", "price_delta": -50}
    )
    assert (option.price_delta, option.tax_category_key, option.is_default) == (
        -50,
        "",
        False,
    )
    assert refused(OptionIn, name="Cheese") == {"__all__"}
    assert refused(
        OptionIn, group="Extras", name="Gold", price_delta=MAX_DELTA + 1
    ) == {"price_delta"}
    assert refused(OptionIn, group="Extras", name="") == {"name"}


def test_an_option_is_named_by_its_id_or_by_its_name_and_optionally_its_group():
    assert (
        OptionRefIn.model_validate({"option": "Cheese", "group": "Extras"}).group
        == "Extras"
    )
    assert refused(OptionRefIn, group="Extras") == {"__all__"}
    patch = OptionPatchIn.model_validate({"option": "Cheese", "tax_category_key": ""})
    assert patch.model_dump(exclude_unset=True) == {
        "option": "Cheese",
        "tax_category_key": "",
    }


def test_a_link_hangs_a_group_from_exactly_one_product_or_category():
    assert (
        LinkIn.model_validate({"group": "Sauces", "product": "BUR-01"}).product
        == "BUR-01"
    )
    assert (
        LinkIn.model_validate({"group": "Sauces", "category": "Mains"}).category
        == "Mains"
    )
    assert refused(LinkIn, group="Sauces") == {"__all__"}
    assert refused(LinkIn, group="Sauces", product="BUR-01", category="Mains") == {
        "__all__"
    }
    assert refused(LinkIn, product="BUR-01") == {"__all__"}
    assert LinkRefIn.model_validate({"id": str(uuid.uuid7())}).group is None
    assert refused(LinkRefIn, group="Sauces") == {"__all__"}


def test_the_pos_reads_name_a_product():
    assert TargetIn.model_validate({"product": "Burger"}).product == "Burger"
    assert refused(TargetIn) == {"__all__"}
    picks = [str(uuid.uuid7()) for _ in range(3)]
    resolved = ResolveIn.model_validate(
        {"product": "Burger", "option_ids": [picks[0], picks[1], picks[0]]}
    )
    # The order of choice and the repeats are kept: they are what is valued.
    assert [str(pick) for pick in resolved.option_ids] == [picks[0], picks[1], picks[0]]
    assert ResolveIn.model_validate({"product": "Burger"}).option_ids == []
    assert refused(
        ResolveIn, product="Burger", option_ids=[str(uuid.uuid7())] * 101
    ) == {"option_ids"}


def test_a_reaction_takes_the_inventory_payload_as_it_is():
    row = uuid.uuid7()
    assert (
        DropIn.model_validate({"id": str(row), "sku": "BUR", "name": "Burger"}).id
        == row
    )
