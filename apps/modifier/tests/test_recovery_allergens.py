"""An option that comes back from a separate copy comes back with its allergens (MODIFIER-F10, MODIFIER-F11): the
option a group the business keeps lost, and each option of a group the business deleted. A copy made before options
had allergens still gives its options back, without them: the column is read only where the copy has it, and the
recovery keeps reading copies as far back as before."""

from django.db import connections

from apps.inventory.tests.test_recovery import direct
from apps.modifier import queries
from apps.modifier.models import ModifierGroup, ModifierOption
from base.tenancy.context import current_alias, use_hub
from base.tenancy.tests.test_recovery import in_the_copy, run, run_in

from . import test_recovery as whole
from . import test_recovery_options as lost
from .conftest import HUB_DB
from .test_recovery import recoveries

#: The fixture taken from the recovery tests: the business's database and its copy.
__all__ = ["recoveries"]

OPTIONS = whole.OPTIONS


def cheese_in_extras() -> ModifierOption:
    extras = whole.a_group("Extras")
    return lost.an_option(extras, "Cheese", allergens=["milk", "gluten"])


def as_before_allergens() -> None:
    """Business A's database read as a copy made before options had allergens: without the column, undone with the
    test's transaction."""
    with connections[current_alias()].cursor() as cursor:
        # The options were just written: their deferred checks run first, or Postgres refuses to alter the table.
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("ALTER TABLE modifier_modifieroption DROP COLUMN allergens")


@HUB_DB
def test_the_copy_gives_each_option_with_its_allergens():
    cheese = cheese_in_extras()

    [read] = queries.options_in_copy(direct())
    [group] = queries.groups_in_copy(direct())

    assert (read["id"], read["allergens"]) == (cheese.id, ["gluten", "milk"])
    assert [option["allergens"] for option in group["options"]] == [["gluten", "milk"]]


@HUB_DB
def test_a_copy_from_before_options_had_allergens_gives_its_options_without_them():
    cheese = cheese_in_extras()
    as_before_allergens()

    [read] = queries.options_in_copy(direct())
    [group] = queries.groups_in_copy(direct())

    assert (read["id"], read["name"]) == (cheese.id, "Cheese")
    assert "allergens" not in read
    assert [sorted(option) for option in group["options"]] == [
        sorted(("name", "kitchen_name", "price_delta", "is_default", "sort_order", "tax_category_id"))
    ]


@HUB_DB
def test_what_is_lacking_takes_the_allergens_the_copy_gave_to_its_create():
    sauces = whole.a_group("Sauces")
    option = lost.of_the_copy(sauces.id, "Mustard sauce", allergens=["mustard"])
    group = whole.a_group_of_the_copy("Sizes", options=[whole.an_option_of_the_copy("Large", allergens=["milk"])])

    [option_back] = queries.options_not_in_business([option])
    [group_back] = queries.groups_not_in_business([group])

    assert option_back == lost.as_recovered(option, sauces.id, allergens=["mustard"])
    assert [one["allergens"] for one in group_back["options"]] == [["milk"]]


@HUB_DB
def test_an_option_comes_back_by_its_create_with_its_allergens():
    sauces = whole.a_group("Sauces")
    [record] = queries.options_not_in_business([lost.of_the_copy(sauces.id, "Mustard sauce", allergens=["mustard"])])

    made = lost.recovered(record)

    assert ModifierOption.objects.get(pk=made.id).allergens == ["mustard"]


# ── End to end: the business's own database and its copy ────────────────────────────────────────────────────────────


def allergens_of(hub) -> dict[tuple[str, str], list[str]]:
    with use_hub(hub):
        return {
            (group, name): allergens
            for group, name, allergens in ModifierOption.objects.values_list("group__name", "name", "allergens")
        }


def a_business(recoveries, every_app_on):
    """A business whose «Extras» offers «Cheese» with milk and whose «Sauces» offers «Mustard sauce» with mustard: the
    hub and the options' ids."""
    hub, _ = recoveries.business(every_app_on)
    ids = {}
    for group, name, allergens in (("Extras", "Cheese", ["milk"]), ("Sauces", "Mustard sauce", ["mustard"])):
        group_id = run_in(hub, "modifier.group.create", name=group).id
        ids[name] = run_in(hub, "modifier.option.create", group_id=group_id, name=name, allergens=allergens).id
    return hub, ids


def test_an_option_and_a_group_the_business_lost_come_back_with_their_allergens(recoveries, every_app_on):
    hub, ids = a_business(recoveries, every_app_on)
    copy = recoveries.copy_of(hub)
    run_in(hub, "modifier.option.delete", id=ids["Cheese"])
    with use_hub(hub):
        sauces = ModifierGroup.objects.get(name="Sauces").pk
    run_in(hub, "modifier.group.delete", id=sauces)
    row = recoveries.ask(copy, "modifier")

    assert run() == 1

    assert whole.said(row) == (
        "done", [whole.MODIFIER_GROUPS | {"created": 1}, OPTIONS | {"created": 1}, whole.CATEGORY_GROUPS, whole.GROUPS]
    )
    assert allergens_of(hub) == {("Extras", "Cheese"): ["milk"], ("Sauces", "Mustard sauce"): ["mustard"]}


def test_a_copy_from_before_allergens_still_gives_its_options_back_without_them(recoveries, every_app_on):
    hub, ids = a_business(recoveries, every_app_on)
    copy = recoveries.copy_of(hub)
    # A copy made before options had allergens: neither the column nor the migration that adds it.
    in_the_copy(copy, "ALTER TABLE modifier_modifieroption DROP COLUMN allergens")
    in_the_copy(copy, "DELETE FROM django_migrations WHERE app = 'modifier' AND name = '0002_option_allergens'")
    run_in(hub, "modifier.option.delete", id=ids["Cheese"])
    row = recoveries.ask(copy, "modifier")

    assert run() == 1

    assert whole.said(row)[1][1] == OPTIONS | {"created": 1}
    assert allergens_of(hub) == {("Extras", "Cheese"): [], ("Sauces", "Mustard sauce"): ["mustard"]}
