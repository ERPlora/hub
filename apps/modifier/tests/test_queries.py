"""Read operations of the modifier app: the lists of the screen (MODIFIER-F01, F04, F05) and the two reads
of the till, the groups of a product (F06) and the valuation of what was chosen (F07, F08)."""

import uuid

import pytest
from live.errors import Conflict, NotFound

from apps.modifier.models import ModifierGroup, ModifierOption

from .conftest import FOOD, GENERIC, make_category, make_product, run

pytestmark = pytest.mark.django_db


def group(name, **fields):
    return run("modifier.group.create", {"name": name, **fields})


def option(group_name, name, **fields):
    return run("modifier.option.create", {"group": group_name, "name": name, **fields})


def link(group_name, **target):
    return run("modifier.link.attach", {"group": group_name, **target})


def names(page) -> list[str]:
    return [row.name for row in page.rows]


# The groups (MODIFIER-F01)


def test_the_groups_by_order_then_name_with_their_counts():
    group("Sauces", sort_order=2)
    group("Doneness", kitchen_name="POINT", min_choices=1, max_choices=1, sort_order=1)
    group("Extras", sort_order=2)
    option("Sauces", "Ketchup", is_default=True)
    option("Sauces", "Mayo")
    burger = make_product()
    link("Sauces", product_id=str(burger.id))
    link("Sauces", category_id=str(make_category().id))

    page = run("modifier.group.list", {}, role="hub_employee")
    assert (names(page), page.total, page.limit, page.offset) == (
        ["Doneness", "Extras", "Sauces"],
        3,
        50,
        0,
    )
    sauces = page.rows[2]
    assert (
        sauces.option_count,
        sauces.default_count,
        sauces.link_count,
        sauces.is_required,
    ) == (2, 1, 2, False)
    assert (page.rows[0].kitchen_name, page.rows[0].is_required) == ("POINT", True)


def test_a_link_to_a_deleted_product_or_category_does_not_count():
    group("Sauces")
    burger = make_product()
    mains = make_category()
    link("Sauces", product_id=str(burger.id))
    link("Sauces", category_id=str(mains.id))
    run("inventory.product.delete", {"id": str(burger.id)})
    run("inventory.category.delete", {"id": str(mains.id)})
    assert run("modifier.group.list", {}).rows[0].link_count == 0


def test_search_filters_sort_and_pages():
    group("Sauces", kitchen_name="SALSA")
    group("Doneness", min_choices=1)
    group("Extras", max_choices=3)
    assert names(run("modifier.group.list", {"search": "salsa"})) == ["Sauces"]
    assert names(run("modifier.group.list", {"search": "ONE"})) == ["Doneness"]
    assert names(run("modifier.group.list", {"name": "x"})) == ["Extras"]
    assert names(run("modifier.group.list", {"required": True})) == ["Doneness"]
    assert names(run("modifier.group.list", {"required": False})) == [
        "Extras",
        "Sauces",
    ]
    assert names(run("modifier.group.list", {"sort": "-name"})) == [
        "Sauces",
        "Extras",
        "Doneness",
    ]
    assert names(run("modifier.group.list", {"sort": "-max_choices"}))[0] == "Extras"
    assert names(run("modifier.group.list", {"sort": "-min_choices"}))[0] == "Doneness"
    second = run("modifier.group.list", {"limit": 2, "offset": 2})
    assert (names(second), second.total) == (["Sauces"], 3)


def test_a_group_by_its_id_or_its_name():
    sauces = group("Sauces")
    group("Sweet sauces")
    assert run("modifier.group.get", {"id": str(sauces.id)}).name == "Sauces"
    # The exact name first, whatever the case; else the only one that contains it.
    assert run("modifier.group.get", {"group": "SAUCES"}).id == sauces.id
    assert run("modifier.group.get", {"group": "sweet"}).name == "Sweet sauces"
    with pytest.raises(Conflict) as error:
        group("Hot sauces")
        run("modifier.group.get", {"group": "sauc"})
    assert error.value.code == "modifier.group_ambiguous"
    with pytest.raises(NotFound):
        run("modifier.group.get", {"id": str(uuid.uuid7())})


def test_tied_groups_follow_the_list_s_direction():
    """hub#2355: groups tied on the sorted column come by name in the list's own direction, never always
    ascending; a descending list is the ascending one read backwards, ties included."""
    # Created out of name order, so that the name tie-break is not the id one (names are unique).
    for name in ("Beta", "Gamma", "Alpha"):
        group(name)
    for column in ("name", "sort_order", "min_choices", "max_choices", "option_count", "link_count"):
        up = names(run("modifier.group.list", {"sort": column}))
        down = names(run("modifier.group.list", {"sort": f"-{column}"}))
        assert (column, up, down) == (
            column,
            ["Alpha", "Beta", "Gamma"],
            ["Gamma", "Beta", "Alpha"],
        )


# The options (MODIFIER-F04)


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
    """hub#2355: options tied on the sorted column come by name, then by id, in the list's own direction;
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


# The links (MODIFIER-F05)


def test_the_links_of_a_group_name_their_target_and_leave_out_what_is_deleted():
    group("Sauces")
    group("Extras")
    burger = make_product("Burger", "BUR-01")
    fries = make_product("Fries", "FRI-01")
    mains = make_category("Mains")
    link("Sauces", product_id=str(fries.id))
    link("Sauces", category_id=str(mains.id))
    link("Sauces", product_id=str(burger.id))
    link("Extras", product_id=str(burger.id))

    page = run("modifier.link.list", {"group": "Sauces"}, role="hub_employee")
    # By what it names: Burger, Fries, Mains.
    assert [
        (row.target_kind, row.product_name or row.category_name) for row in page.rows
    ] == [
        ("product", "Burger"),
        ("product", "Fries"),
        ("category", "Mains"),
    ]
    assert page.rows[0].product_sku == "BUR-01"
    assert run("modifier.link.list", {"product_id": str(burger.id)}).total == 2
    assert run("modifier.link.list", {"category_id": str(mains.id)}).total == 1
    run("inventory.product.delete", {"id": str(fries.id)})
    assert [
        row.product_name for row in run("modifier.link.list", {"group": "Sauces"}).rows
    ] == ["Burger", None]


# The groups of a product (MODIFIER-F06)


@pytest.fixture
def menu():
    """A burger in Mains and Grill: its own Doneness, Sauces from Mains and from itself, Drinks from Grill."""
    burger = make_product("Burger", "BUR-01")
    mains = make_category("Mains")
    grill = make_category("Grill")
    for category in (mains, grill):
        run(
            "inventory.product_category.add",
            {"product_id": str(burger.id), "category_id": str(category.id)},
        )
    group("Doneness", kitchen_name="POINT", min_choices=1, max_choices=1, sort_order=1)
    option("Doneness", "Medium", sort_order=2)
    option("Doneness", "Rare", kitchen_name="RARE", sort_order=1, is_default=True)
    group("Sauces", max_choices=2, sort_order=2)
    option("Sauces", "Ketchup")
    option("Sauces", "Mayo", price_delta=30)
    group("Drinks", sort_order=3)
    option("Drinks", "Soda", price_delta=250, tax_category_key=GENERIC)
    group("Empty", min_choices=1, sort_order=0)
    group("Elsewhere")
    option("Elsewhere", "Nothing")
    link("Doneness", product_id=str(burger.id))
    link("Sauces", product_id=str(burger.id))
    link("Sauces", category_id=str(mains.id))
    link("Drinks", category_id=str(grill.id))
    link("Empty", product_id=str(burger.id))
    link("Elsewhere", product_id=str(make_product("Salad", "SAL-01").id))
    return {"burger": burger, "mains": mains, "grill": grill}


def test_a_product_carries_its_own_groups_and_those_of_all_its_categories_each_once(
    menu,
):
    target = run(
        "modifier.group.for_target", {"product": "bur-01"}, role="hub_employee"
    )
    assert (target.product_id, target.product_name) == (menu["burger"].id, "Burger")
    # Each once (Sauces hangs from the product and from Mains), by order and name; Empty has no options.
    assert [group.name for group in target.groups] == ["Doneness", "Sauces", "Drinks"]
    doneness = target.groups[0]
    assert (
        doneness.kitchen_name,
        doneness.min_choices,
        doneness.max_choices,
        doneness.is_required,
    ) == ("POINT", 1, 1, True)
    assert [
        (o.name, o.kitchen_name, o.price_delta, o.is_default) for o in doneness.options
    ] == [
        ("Rare", "RARE", 0, True),
        ("Medium", "", 0, False),
    ]
    soda = target.groups[2].options[0]
    assert (soda.price_delta, soda.tax_category_key) == (250, GENERIC)


def test_a_deleted_category_or_a_product_without_groups_carries_nothing(menu):
    run("inventory.category.delete", {"id": str(menu["grill"].id)})
    assert [
        g.name
        for g in run(
            "modifier.group.for_target", {"product_id": str(menu["burger"].id)}
        ).groups
    ] == [
        "Doneness",
        "Sauces",
    ]
    assert (
        run(
            "modifier.group.for_target",
            {"product_id": str(make_product("Water", "WAT").id)},
        ).groups
        == []
    )
    with pytest.raises(NotFound):
        run("modifier.group.for_target", {"product": "nowhere"})


# Valuing the picks (MODIFIER-F07, F08)


def ids(target, *names_):
    by_name = {o.name: o.id for g in target.groups for o in g.options}
    return [str(by_name[name]) for name in names_]


def resolve(product, picks):
    return run(
        "modifier.selection.resolve",
        {"product": product, "option_ids": picks},
        role="hub_employee",
    )


def refused(product, picks) -> tuple:
    with pytest.raises(Conflict) as error:
        resolve(product, picks)
    return error.value.code, error.value.message, error.value.fields


def test_the_picks_are_valued_at_the_catalog_price_in_the_order_chosen(menu):
    target = run("modifier.group.for_target", {"product": "BUR-01"})
    valued = resolve("BUR-01", ids(target, "Mayo", "Rare", "Soda"))
    assert [
        (p.name, p.kitchen_name, p.price_delta, p.own_line) for p in valued.picks
    ] == [
        ("Mayo", "Mayo", 30, False),
        ("Rare", "RARE", 0, False),
        ("Soda", "Soda", 250, True),
    ]
    assert valued.picks[0].group_name == "Sauces"
    # The soda taxes differently from the burger (restaurant food): its own line, not folded.
    assert (valued.folded_delta, valued.kitchen_text) == (30, "Mayo, RARE, Soda")
    assert valued.picks[2].tax_category_key == GENERIC


def test_an_own_tax_category_equal_to_the_products_is_folded(menu):
    group("Wine")
    option("Wine", "Glass", price_delta=300, tax_category_key=FOOD)
    link("Wine", product="BUR-01")
    target = run("modifier.group.for_target", {"product": "BUR-01"})
    valued = resolve("BUR-01", ids(target, "Rare", "Glass"))
    assert [(p.name, p.own_line) for p in valued.picks] == [
        ("Rare", False),
        ("Glass", False),
    ]
    assert valued.folded_delta == 300


def test_a_required_group_must_be_answered(menu):
    target = run("modifier.group.for_target", {"product": "BUR-01"})
    assert refused("BUR-01", ids(target, "Mayo")) == (
        "modifier.choice_below_min",
        "Choose at least 1 in «Doneness».",
        {"option_ids": "Choose at least 1 in «Doneness»."},
    )
    # The empty group is required but has nothing to choose: it is never asked.
    assert resolve("BUR-01", ids(target, "Medium")).kitchen_text == "Medium"


def test_never_more_than_the_maximum(menu):
    target = run("modifier.group.for_target", {"product": "BUR-01"})
    code, message, _ = refused("BUR-01", ids(target, "Rare", "Medium"))
    assert (code, message) == (
        "modifier.choice_above_max",
        "Choose at most 1 in «Doneness».",
    )


def test_an_option_is_repeated_only_where_the_group_allows_it(menu):
    target = run("modifier.group.for_target", {"product": "BUR-01"})
    code, message, _ = refused("BUR-01", ids(target, "Rare", "Mayo", "Mayo"))
    assert (code, message) == (
        "modifier.option_repeated",
        "«Mayo» cannot be chosen more than once.",
    )
    run("modifier.group.update", {"group": "Sauces", "allow_repeat": True})
    valued = resolve("BUR-01", ids(target, "Rare", "Mayo", "Mayo"))
    assert (valued.folded_delta, valued.kitchen_text) == (60, "RARE, Mayo, Mayo")
    # A repeat counts toward the maximum.
    code, _, _ = refused("BUR-01", ids(target, "Rare", "Mayo", "Mayo", "Ketchup"))
    assert code == "modifier.choice_above_max"


def test_an_option_that_is_not_offered_with_the_product_is_refused(menu):
    elsewhere = run("modifier.option.list", {"group": "Elsewhere"}).rows[0]
    target = run("modifier.group.for_target", {"product": "BUR-01"})
    message = "This option is not offered with this product."
    for picks in ([str(elsewhere.id)], [str(uuid.uuid7())]):
        assert refused("BUR-01", ids(target, "Rare") + picks) == (
            "modifier.option_not_offered",
            message,
            {"option_ids": message},
        )


def test_a_product_without_groups_is_valued_with_nothing():
    make_product("Water", "WAT")
    valued = resolve("WAT", [])
    assert (valued.picks, valued.folded_delta, valued.kitchen_text) == ([], 0, "")


def test_the_option_list_is_safe_for_a_group_left_without_rows():
    assert ModifierGroup.objects.count() == 0
    assert run("modifier.option.list", {}).total == 0


# The money rules the valuation holds for Sales (WORKBOOK «Contrato con Ventas»)


def test_an_empty_choice_is_valued_too_and_a_required_group_still_asks(menu):
    # Sales calls the valuation for every line of a product with groups, also with no option chosen:
    # otherwise the API or the assistant would skip a required group.
    assert refused("BUR-01", [])[0] == "modifier.choice_below_min"


def test_a_discount_never_takes_the_dish_below_zero():
    make_product("Toast", "TOA", price=300)
    group("Bread")
    option("Bread", "No bread", price_delta=-500)
    option("Bread", "Half bread", price_delta=-300)
    link("Bread", product="TOA")
    target = run("modifier.group.for_target", {"product": "TOA"})
    message = "These options take the price of «Toast» below zero."
    assert refused("TOA", ids(target, "No bread")) == ("modifier.price_below_zero", message, {"option_ids": message})
    # Down to zero is a free dish, which is a price.
    assert resolve("TOA", ids(target, "Half bread")).folded_delta == -300


def test_an_own_line_is_one_line_per_option_with_its_quantity_per_unit_of_the_dish(menu):
    run("modifier.group.update", {"group": "Drinks", "allow_repeat": True})
    target = run("modifier.group.for_target", {"product": "BUR-01"})
    [soda] = ids(target, "Soda")
    valued = resolve("BUR-01", ids(target, "Rare", "Soda", "Mayo", "Soda"))
    # Four choices, each in the order chosen; the soda twice is one line of 2 (Sales multiplies it by
    # the line's quantity: two burgers, four sodas).
    assert [pick.name for pick in valued.picks] == ["Rare", "Soda", "Mayo", "Soda"]
    assert [line.model_dump() for line in valued.own_lines] == [
        {
            "option_id": uuid.UUID(soda),
            "group_id": valued.picks[1].group_id,
            "name": "Soda",
            "kitchen_name": "Soda",
            "tax_category_key": GENERIC,
            "price_delta": 250,
            "quantity": 2,
        }
    ]
    assert valued.folded_delta == 30
    # Without own lines, none.
    assert resolve("BUR-01", ids(target, "Rare")).own_lines == []


def test_a_product_sold_by_weight_or_measure_takes_no_priced_option():
    make_product("Ham", "HAM", price=4000, unit="kg", pricing_unit="kg")
    make_product("Screws", "SCR", price=37, unit="ud", price_quantity="100")
    group("Cut")
    option("Cut", "Sliced")
    option("Cut", "Extra fine", price_delta=100)
    option("Cut", "Gift wrap", price_delta=200, tax_category_key=GENERIC)
    for sku in ("HAM", "SCR"):
        link("Cut", product=sku)
    target = run("modifier.group.for_target", {"product": "HAM"})
    # A free one is fine: nothing to scale.
    assert resolve("HAM", ids(target, "Sliced")).folded_delta == 0
    # Sales prices the line by its quantity (0.350 kg, 250 units): a supplement per unit would be
    # scaled with it, so it is refused, folded or on a line of its own.
    for sku, name in (("HAM", "Ham"), ("SCR", "Screws")):
        message = f"«{name}» is sold by weight or measure: an option with a supplement cannot go with it."
        for picks in (ids(target, "Extra fine"), ids(target, "Gift wrap")):
            assert refused(sku, picks) == ("modifier.priced_by_measure", message, {"option_ids": message})
