"""The options a modifier group comes with chosen by default (MODIFIER-F04): never more than it takes."""

import pytest
from live.errors import Conflict

from apps.modifier.models import ModifierGroup, ModifierOption
from apps.modifier.services.defaults import _defaults_in_full

from .conftest import HUB_DB, events, group, option, refusal, run

pytestmark = HUB_DB


def test_in_a_group_of_one_a_new_default_takes_the_place_of_the_old_one():
    group("Doneness", min_choices=1, max_choices=1)
    rare = option("Doneness", "Rare", is_default=True)
    medium = option("Doneness", "Medium", is_default=True)
    assert medium.is_default is True
    assert ModifierOption.objects.get(pk=rare.id).is_default is False
    assert events("modifier.option.updated") == [
        {
            "id": str(rare.id),
            "group_id": str(rare.group_id),
            "name": "Rare",
            "price_delta": 0,
        }
    ]
    well = option("Doneness", "Well done")
    run("modifier.option.update", {"id": str(well.id), "is_default": True})
    assert list(
        ModifierOption.objects.filter(is_default=True).values_list("name", flat=True)
    ) == ["Well done"]


def test_otherwise_there_are_never_more_defaults_than_the_maximum():
    group("Sauces", max_choices=2)
    option("Sauces", "Ketchup", is_default=True)
    option("Sauces", "Mayo", is_default=True)
    assert _defaults_in_full(ModifierGroup.objects.get(name="Sauces")) == ["Ketchup", "Mayo"]
    message = "This group has more options chosen by default than its maximum."
    with pytest.raises(Conflict) as error:
        option("Sauces", "Mustard", is_default=True)
    assert refusal(error) == (
        "Conflict",
        "modifier.too_many_defaults",
        {"is_default": message},
    )
    mustard = option("Sauces", "Mustard")
    with pytest.raises(Conflict):
        run("modifier.option.update", {"id": str(mustard.id), "is_default": True})
    # Lowering the group's maximum below its defaults is the same refusal, on the maximum.
    with pytest.raises(Conflict) as error:
        run("modifier.group.update", {"group": "Sauces", "max_choices": 1})
    assert refusal(error) == (
        "Conflict",
        "modifier.too_many_defaults",
        {"max_choices": message},
    )
    # No ceiling, no limit.
    run("modifier.group.update", {"group": "Sauces", "max_choices": 0})
    assert (
        run(
            "modifier.option.update", {"id": str(mustard.id), "is_default": True}
        ).is_default
        is True
    )
