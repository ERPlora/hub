"""The writes on an option of a modifier group (MODIFIER-F04): its supplement and its own tax category. Taxes is the
real app (no doubles)."""

import pytest
from live.errors import Conflict, InvalidPayload, NotFound

from apps.modifier.models import MAX_OPTIONS, ModifierGroup, ModifierOption
from apps.modifier.schemas.options import OptionPatchIn
from apps.modifier.services.options import update_option

from .conftest import GENERIC, HUB_DB, ctx_for, events, group, option, refusal, run

pytestmark = HUB_DB


def test_adding_an_option_with_its_supplement():
    sauces = group("Sauces")
    cheese = option(
        name="Cheese", kitchen_name="+CHEESE", price_delta=100, sort_order=2
    )
    assert (cheese.group_id, cheese.group_name, cheese.name, cheese.kitchen_name) == (
        sauces.id,
        "Sauces",
        "Cheese",
        "+CHEESE",
    )
    assert (
        cheese.price_delta,
        cheese.tax_category_key,
        cheese.is_default,
        cheese.sort_order,
    ) == (100, None, False, 2)
    assert events("modifier.option.created") == [
        {
            "id": str(cheese.id),
            "group_id": str(sauces.id),
            "name": "Cheese",
            "price_delta": 100,
        }
    ]
    # A discount and a free one.
    assert option(name="No bread", price_delta=-50).price_delta == -50
    assert option(name="No onion").price_delta == 0


def test_an_option_name_is_unique_in_its_group():
    group("Sauces")
    group("Extras")
    option("Sauces", "Cheese")
    option("Extras", "Cheese")
    with pytest.raises(Conflict) as error:
        option("Sauces", "CHEESE")
    assert refusal(error) == (
        "Conflict",
        "modifier.option_name_taken",
        {"name": "This group already has an option with that name."},
    )


def test_an_option_of_a_group_that_does_not_exist_is_a_404():
    with pytest.raises(NotFound):
        option("Nowhere", "Cheese")


def test_an_own_tax_category_by_its_key_or_its_name_and_never_an_unknown_one():
    group("Drinks")
    soda = option("Drinks", "Soda", price_delta=250, tax_category_key=GENERIC)
    assert (soda.tax_category_key, soda.tax_category_name) == (
        GENERIC,
        "Product — generic",
    )
    water = option(
        "Drinks", "Water", price_delta=150, tax_category_key="Product — generic"
    )
    assert water.tax_category_key == GENERIC
    with pytest.raises(InvalidPayload) as error:
        option("Drinks", "Juice", price_delta=200, tax_category_key="nowhere.tax")
    assert error.value.fields == {
        "tax_category_key": "This tax category does not exist in Taxes."
    }


def test_an_option_with_its_own_tax_category_must_be_worth_more_than_zero():
    group("Drinks")
    message = "An option with its own tax category is billed on a line of its own: its supplement must be more than zero."
    for delta in (0, -100):
        with pytest.raises(InvalidPayload) as error:
            option(
                "Drinks", f"Soda {delta}", price_delta=delta, tax_category_key=GENERIC
            )
        assert error.value.fields == {"price_delta": message}
    soda = option("Drinks", "Soda", price_delta=250, tax_category_key=GENERIC)
    with pytest.raises(InvalidPayload) as error:
        run("modifier.option.update", {"id": str(soda.id), "price_delta": 0})
    assert error.value.fields == {"price_delta": message}
    # Back to the dish's category, it may be free again.
    assert (
        run(
            "modifier.option.update",
            {"id": str(soda.id), "price_delta": 0, "tax_category_key": ""},
        ).tax_category_key
        is None
    )


def test_a_group_holds_at_most_100_options():
    sauces = ModifierGroup.objects.create(name="Sauces")
    ModifierOption.objects.bulk_create(
        [ModifierOption(group=sauces, name=f"O{i}") for i in range(MAX_OPTIONS)]
    )
    with pytest.raises(Conflict) as error:
        option("Sauces", "One more")
    assert error.value.code == "modifier.group_full"


def test_changing_an_option_keeps_what_is_not_sent():
    group("Drinks")
    soda = option(
        "Drinks",
        "Soda",
        kitchen_name="SODA",
        price_delta=250,
        tax_category_key=GENERIC,
        sort_order=3,
    )
    changed = run(
        "modifier.option.update",
        {"option": "soda", "price_delta": 300},
        role="hub_manager",
    )
    assert (
        changed.name,
        changed.kitchen_name,
        changed.price_delta,
        changed.tax_category_key,
        changed.sort_order,
    ) == (
        "Soda",
        "SODA",
        300,
        GENERIC,
        3,
    )
    assert events("modifier.option.updated")[-1] == {
        "id": str(soda.id),
        "group_id": str(soda.group_id),
        "name": "Soda",
        "price_delta": 300,
    }
    run("modifier.option.update", {"id": str(soda.id), "name": "Soda"})
    assert len(events("modifier.option.updated")) == 1


def test_an_option_named_in_two_groups_needs_its_group():
    group("Sauces")
    group("Extras")
    option("Sauces", "Cheese")
    extra_cheese = option("Extras", "Cheese")
    with pytest.raises(Conflict) as error:
        run("modifier.option.update", {"option": "Cheese", "price_delta": 50})
    assert error.value.code == "modifier.option_ambiguous"
    assert (
        "Cheese (Sauces)" in error.value.message
        and "Cheese (Extras)" in error.value.message
    )
    assert (
        run(
            "modifier.option.update",
            {"option": "Cheese", "group": "Extras", "price_delta": 50},
        ).id
        == extra_cheese.id
    )


def test_renaming_an_option_to_a_taken_name_is_a_409():
    group("Sauces")
    option("Sauces", "Ketchup")
    mayo = option("Sauces", "Mayo")
    with pytest.raises(Conflict) as error:
        run("modifier.option.update", {"id": str(mayo.id), "name": "ketchup"})
    assert error.value.code == "modifier.option_name_taken"
    # Its own name in other letters is not another's.
    assert update_option(ctx_for(), OptionPatchIn(id=mayo.id, name="MAYO")).name == "MAYO"


def test_deleting_an_option():
    group("Sauces")
    ketchup = option("Sauces", "Ketchup", price_delta=20)
    assert (
        run("modifier.option.delete", {"option": "Ketchup", "group": "Sauces"}).id
        == ketchup.id
    )
    assert ModifierOption.objects.count() == 0
    assert events("modifier.option.deleted") == [
        {
            "id": str(ketchup.id),
            "group_id": str(ketchup.group_id),
            "name": "Ketchup",
            "price_delta": 20,
        }
    ]
    with pytest.raises(NotFound) as error:
        run("modifier.option.delete", {"id": str(ketchup.id)})
    assert error.value.message == "This option does not exist."
