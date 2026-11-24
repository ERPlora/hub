"""The schemas of the options of a group: what one is named, made and changed with (422 per field)."""

from apps.modifier.models import MAX_DELTA
from apps.modifier.schemas.options import OptionIn, OptionPatchIn, OptionRefIn

from .schema_checks import refused


def test_an_option_names_its_group_and_carries_a_signed_supplement():
    option = OptionIn.model_validate(
        {"group": "Extras", "name": "Cheese", "price_delta": -50}
    )
    assert (option.price_delta, option.tax_category_key, option.is_default) == (
        -50,
        "",
        False,
    )
    assert refused(OptionIn, name="Cheese", price_delta=0) == {"__all__"}
    assert refused(
        OptionIn, group="Extras", name="Gold", price_delta=MAX_DELTA + 1
    ) == {"price_delta"}
    assert refused(OptionIn, group="Extras", name="", price_delta=0) == {"name"}


def test_a_new_option_needs_its_supplement_said_and_free_is_said_as_zero():
    assert refused(OptionIn, group="Extras", name="Extra cheese") == {"price_delta"}
    free = OptionIn.model_validate({"group": "Doneness", "name": "Rare", "price_delta": 0})
    assert free.price_delta == 0


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
