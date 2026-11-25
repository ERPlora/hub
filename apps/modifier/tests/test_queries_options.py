"""The list of the options (MODIFIER-F04), of one group or of the whole catalog."""

from apps.modifier.models import ModifierGroup, ModifierOption

from .conftest import GENERIC, HUB_DB, group, names, option, run

pytestmark = HUB_DB


def test_the_options_of_a_group_or_all_with_their_tax_category_in_the_readers_language():
    group("Sauces")
    group("Drinks")
    option("Sauces", "Mayo", sort_order=2)
    option("Sauces", "Ketchup", sort_order=1, price_delta=20)
    option("Drinks", "Soda", price_delta=250, tax_category_key=GENERIC)

    sauces = run("modifier.option.list", {"group": "Sauces"}, role="hub_employee")
    assert (names(sauces), sauces.total) == (["Ketchup", "Mayo"], 2)
    everything = run("modifier.option.list", {})
    # The whole catalog by its groups' order and name, then each group's own order.
    assert [(row.group_name, row.name) for row in everything.rows] == [
        ("Drinks", "Soda"),
        ("Sauces", "Ketchup"),
        ("Sauces", "Mayo"),
    ]
    soda = everything.rows[0]
    assert (soda.tax_category_key, soda.tax_category_name) == (
        GENERIC,
        "Product — generic",
    )
    assert names(run("modifier.option.list", {"search": "ket"})) == ["Ketchup"]
    assert names(run("modifier.option.list", {"sort": "-price_delta"}))[0] == "Soda"


def test_tied_options_follow_the_list_s_direction():
    """Options tied on the sorted column come by name, then by id, in the list's own direction;
    the whole catalog by its groups too, so «-sort_order» is «sort_order» read backwards."""
    group("Sauces")
    group("Extras")
    # Created out of name order, and two «Bacon» in two groups, so that neither the name nor the id
    # tie-break is the creation order.
    bacon = option("Sauces", "Bacon")
    avocado = option("Sauces", "Avocado")
    extra_bacon = option("Extras", "Bacon")
    # Postgres writes a touched row's new version after the others: without the id tie-break, the first
    # «Bacon» would come after the second.
    ModifierOption.objects.filter(pk=bacon.id).update(kitchen_name="BACON")

    def listed(**query) -> list:
        return [row.id for row in run("modifier.option.list", query).rows]

    for sort in ("name", "price_delta"):
        assert (sort, listed(sort=sort)) == (sort, [avocado.id, bacon.id, extra_bacon.id])
        assert (sort, listed(sort=f"-{sort}")) == (sort, [extra_bacon.id, bacon.id, avocado.id])
    for sort in ("sort_order", "price_delta", "name"):
        assert (sort, listed(group="Sauces", sort=sort)) == (sort, [avocado.id, bacon.id])
        assert (sort, listed(group="Sauces", sort=f"-{sort}")) == (sort, [bacon.id, avocado.id])
    # The whole catalog by its groups' order and name (Extras before Sauces), then each group's own.
    assert listed(sort="sort_order") == [extra_bacon.id, avocado.id, bacon.id]
    assert listed(sort="-sort_order") == [bacon.id, avocado.id, extra_bacon.id]


def test_the_option_list_is_safe_for_a_group_left_without_rows():
    assert ModifierGroup.objects.count() == 0
    assert run("modifier.option.list", {}).total == 0
