"""What Modifiers gives back from a separate copy of the business (BASE-F114, MODIFIER-F10).

The copy is no business, so it has no alias and the ORM never reaches it: the platform reads it through a direct,
read-only connection, and Modifiers answers with its own SQL over its models' names. First each group the business no
longer has, made again with its options by ``modifier.group.recover`` (the group sheet's create, then each option's),
unless the business has one with its name; then its groups hung from a category, then those hung from a product: each
one of a live category or product that the business no longer has is hung again by ``modifier.link.attach``, the group
sheet's own, unless the business hung that group there again. Modifiers goes after Inventory (its ``requires``), so a
deleted product is back, the same, and a deleted category brought back as a new one, before their groups are hung.

Then, end to end on real databases (``hubs.CopiedHubs``): the business's own and its copy, a clone of it.
"""

import uuid

import pytest
from django.apps import apps
from django.db import connection
from django.utils import translation
from live.models import OutboxEvent
from live.operations import get as get_operation

from apps.inventory.models import Category, Product
from apps.inventory.tests.test_recovery import (
    CATEGORIES,
    LINKS,
    PRODUCTS,
    a_tax_key,
    brought_back,
    gone_altogether,
    made_by_a_recovery,
)
from apps.modifier import queries
from apps.modifier.models import ModifierGroup, ModifierLink, ModifierOption
from apps.modifier.services import OPTION_LEFT, TAX_CATEGORY_UNKNOWN
from apps.tax.models import TaxCategory
from base.recovery import actor_of
from base.tenancy.context import use_hub
from base.tenancy.tests.test_recovery import Recoveries, fields_held_since, fresh, run, run_in

from .conftest import GENERIC, ctx_for, ctx_with, make_category, make_product
from .conftest import run as run_here


def direct():
    """The raw connection of the tests' database, as the platform's direct one reads the copy."""
    connection.ensure_connection()
    return connection.connection


def a_group(name: str):
    return run_here("modifier.group.create", {"name": name})


def groups_now() -> dict:
    """The copy's groups by id with their names, as the link reads give them, where the copy is the business as it is."""
    return dict(ModifierGroup.objects.values_list("pk", "name"))


def hang(group, *, product=None, category=None) -> ModifierLink:
    target = {"product_id": str(product.id)} if product else {"category_id": str(category.id)}
    return ModifierLink.objects.get(pk=run_here("modifier.link.attach", {"group_id": str(group.id), **target}).id)


@pytest.mark.django_db
def test_the_copy_gives_each_group_hung_from_a_live_product_with_what_its_attach_takes():
    burger, fries = make_product("Burger", "BUR"), make_product("Fries", "FRI")
    sauces, extras = a_group("Sauces"), a_group("Extras")
    on_burger = hang(sauces, product=burger)
    extra_burger = hang(extras, product=burger)
    on_fries = hang(sauces, product=fries)
    # A category's groups are not a product's: none is read.
    hang(extras, category=make_category("Mains"))
    # Nor a deleted product's, whose groups its deletion lets go of (before the relay's tick, still there).
    old = make_product("Old", "OLD")
    hang(sauces, product=old)
    run_here("inventory.product.delete", {"id": str(old.id)})

    # One no product asks for: the copy's groups are every one of them.
    bare = a_group("Bare")

    read = queries.links_in_copy(direct())

    # With each product's SKU there, the article's identity, to find the one made again if the business lost it; and
    # every group of the copy by name, to find the one brought back if the business deleted it.
    named = {sauces.id: "Sauces", extras.id: "Extras", bare.id: "Bare"}
    assert read == [
        {"id": on_burger.id, "group_id": sauces.id, "product_id": burger.id, "sku": "BUR", "copy_groups": named},
        {"id": extra_burger.id, "group_id": extras.id, "product_id": burger.id, "sku": "BUR", "copy_groups": named},
        {"id": on_fries.id, "group_id": sauces.id, "product_id": fries.id, "sku": "FRI", "copy_groups": named},
    ]


@pytest.mark.django_db
def test_a_copy_without_the_apps_table_gives_nothing():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE modifier_modifierlink CASCADE")

    assert queries.links_in_copy(direct()) == []


def a_link_of_the_copy(group, product) -> dict:
    return {
        "id": uuid.uuid7(), "group_id": group.id, "product_id": product.id, "sku": product.sku, "copy_groups": groups_now()
    }


def a_link_of_a_product_gone(group, sku: str, product_id=None) -> dict:
    """A link of the copy whose product the business no longer holds at all: only its SKU says which article it was."""
    return {
        "id": uuid.uuid7(), "group_id": group.id, "product_id": product_id or uuid.uuid7(), "sku": sku,
        "copy_groups": groups_now(),
    }


@pytest.mark.django_db
def test_lacking_is_a_group_the_business_no_longer_hangs_from_that_product():
    burger, fries = make_product("Burger", "BUR"), make_product("Fries", "FRI")
    sauces, extras, sizes = a_group("Sauces"), a_group("Extras"), a_group("Sizes")
    # Still in the business: it is the business's, nothing lacks.
    held = hang(sizes, product=fries)
    still = a_link_of_the_copy(sizes, fries) | {"id": held.id}
    # Hung again by the business since, under another id: the business's stays, never a second one.
    hang(sauces, product=burger)
    hung_again = a_link_of_the_copy(sauces, burger)
    # Lacking: the same product with another group, and the same group on another product.
    other_group = a_link_of_the_copy(extras, burger)
    other_product = a_link_of_the_copy(sauces, fries)

    lacking = queries.links_not_in_business([still, hung_again, other_group, other_product])

    # As the group sheet's attach takes each, with its id in the copy: the group and the product.
    assert lacking == [
        {"id": other_group["id"], "group_id": extras.id, "product_id": burger.id},
        {"id": other_product["id"], "group_id": sauces.id, "product_id": fries.id},
    ]


@pytest.mark.django_db
def test_a_product_gone_gets_its_groups_on_the_one_a_recovery_made_again_with_its_sku():
    sauces, extras = a_group("Sauces"), a_group("Extras")
    burger = made_by_a_recovery("Burger", "BUR")
    # Hung again by the business on the one made again, after the recovery made it: the business's stays.
    hang(sauces, product=burger)
    hung_again = a_link_of_a_product_gone(sauces, "BUR")
    lacking_one = a_link_of_a_product_gone(extras, "BUR", hung_again["product_id"])
    # Made again by hand with its SKU: the business's own, set up as it chose; it keeps the copy's product, which the
    # attach refuses as not found: not created, and why.
    make_product("Fries", "FRI")
    by_hand = a_link_of_a_product_gone(sauces, "FRI")

    lacking = queries.links_not_in_business([hung_again, lacking_one, by_hand])

    assert lacking == [
        {"id": lacking_one["id"], "group_id": extras.id, "product_id": burger.id},
        {"id": by_hand["id"], "group_id": sauces.id, "product_id": by_hand["product_id"]},
    ]


def test_with_nothing_read_nothing_is_lacking():
    assert queries.groups_not_in_business([]) == []
    assert queries.links_not_in_business([]) == []
    assert queries.category_links_not_in_business([]) == []


@pytest.mark.django_db
def test_the_copy_gives_each_group_hung_from_a_live_category_with_what_its_attach_takes():
    mains, drinks, bare = make_category("Mains"), make_category("Drinks"), make_category("Bare")
    sauces, extras = a_group("Sauces"), a_group("Extras")
    on_mains = hang(sauces, category=mains)
    extra_mains = hang(extras, category=mains)
    on_drinks = hang(sauces, category=drinks)
    # A product's groups are not a category's: none is read.
    hang(extras, product=make_product("Burger", "BUR"))
    # Nor a deleted category's, whose groups its deletion lets go of (before the relay's tick, still there).
    old = make_category("Old")
    hang(sauces, category=old)
    run_here("inventory.category.delete", {"id": str(old.id)})

    read = queries.category_links_in_copy(direct())

    # With every live category of the copy by name, one no group hangs from too: the pairing with the business's
    # needs the whole copy, to tell one the copy also holds from the stand-in of another with its name.
    # The same with the copy's groups, to tell one the copy also holds from the stand-in of another with its name.
    named = {mains.id: "Mains", drinks.id: "Drinks", bare.id: "Bare"}
    groups = {sauces.id: "Sauces", extras.id: "Extras"}
    assert read == [
        {"id": on_mains.id, "group_id": sauces.id, "category_id": mains.id, "copy_categories": named,
         "copy_groups": groups},
        {"id": extra_mains.id, "group_id": extras.id, "category_id": mains.id, "copy_categories": named,
         "copy_groups": groups},
        {"id": on_drinks.id, "group_id": sauces.id, "category_id": drinks.id, "copy_categories": named,
         "copy_groups": groups},
    ]


@pytest.mark.django_db
def test_a_copy_without_the_apps_table_gives_no_group_of_a_category():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE modifier_modifierlink CASCADE")

    assert queries.category_links_in_copy(direct()) == []


@pytest.mark.django_db
@pytest.mark.parametrize("read", [queries.links_in_copy, queries.category_links_in_copy])
def test_a_copy_with_none_of_the_apps_tables_reads_no_group_for_its_links(read):
    with connection.cursor() as cursor:
        # Undone with the test's transaction. A copy taken before the app was switched on has none of its tables: the
        # groups by name are not read where there is no link to pair.
        cursor.execute("DROP TABLE modifier_modifierlink, modifier_modifieroption, modifier_modifiergroup CASCADE")

    assert read(direct()) == []


def a_category_link_of_the_copy(group, category_id, copy: dict) -> dict:
    """A link of the copy as ``category_links_in_copy`` gives it: ``group`` on ``category_id``, with the copy's live
    categories by name ``copy``."""
    return {
        "id": uuid.uuid7(), "group_id": group.id, "category_id": category_id, "copy_categories": copy,
        "copy_groups": groups_now(),
    }


@pytest.mark.django_db
def test_lacking_is_a_group_the_business_no_longer_hangs_from_that_category():
    mains, drinks = make_category("Mains"), make_category("Drinks")
    sauces, extras, sizes = a_group("Sauces"), a_group("Extras"), a_group("Sizes")
    copy = {mains.id: "Mains", drinks.id: "Drinks"}
    # Still in the business: it is the business's, nothing lacks.
    held = hang(sizes, category=drinks)
    still = a_category_link_of_the_copy(sizes, drinks.id, copy) | {"id": held.id}
    # Hung again by the business since, under another id: the business's stays, never a second one.
    hang(sauces, category=mains)
    hung_again = a_category_link_of_the_copy(sauces, mains.id, copy)
    # Lacking: the same category with another group, and the same group on another category.
    other_group = a_category_link_of_the_copy(extras, mains.id, copy)
    other_category = a_category_link_of_the_copy(sauces, drinks.id, copy)

    lacking = queries.category_links_not_in_business([still, hung_again, other_group, other_category])

    # As the group sheet's attach takes each, with its id in the copy: the group and the category.
    assert lacking == [
        {"id": other_group["id"], "group_id": extras.id, "category_id": mains.id},
        {"id": other_category["id"], "group_id": sauces.id, "category_id": drinks.id},
    ]


@pytest.mark.django_db
def test_a_category_gone_gets_its_groups_on_the_one_a_recovery_brought_back_with_its_name():
    sauces, extras = a_group("Sauces"), a_group("Extras")
    lost = make_category("Mains")
    run_here("inventory.category.delete", {"id": str(lost.id)})
    back = brought_back("Mains")
    gone = uuid.uuid7()
    copy = {lost.id: "Mains", gone: "Drinks"}
    # Hung again by the business on the one brought back, after the recovery made it: the business's stays.
    hang(sauces, category=back)
    hung_again = a_category_link_of_the_copy(sauces, lost.id, copy)
    lacking_one = a_category_link_of_the_copy(extras, lost.id, copy)
    # Made again by hand with its name: the business's own, set up as it chose; it keeps the copy's category, which the
    # attach refuses as not found: not created, and why.
    make_category("Drinks")
    by_hand = a_category_link_of_the_copy(sauces, gone, copy)

    lacking = queries.category_links_not_in_business([hung_again, lacking_one, by_hand])

    assert lacking == [
        {"id": lacking_one["id"], "group_id": extras.id, "category_id": back.id},
        {"id": by_hand["id"], "group_id": sauces.id, "category_id": gone},
    ]


@pytest.mark.django_db
def test_a_category_the_copy_also_holds_is_never_the_stand_in_of_another_with_its_name():
    sauces = a_group("Sauces")
    lost = make_category("Specials")
    run_here("inventory.category.delete", {"id": str(lost.id)})
    # Brought back by an earlier recovery before the copy was made, and kept: the copy holds it too, as itself.
    kept = brought_back("Specials")
    link = a_category_link_of_the_copy(sauces, lost.id, {lost.id: "Specials", kept.id: "Specials"})

    # The lost one has no stand-in: its group keeps the copy's category, which the attach refuses as not found.
    assert queries.category_links_not_in_business([link]) == [
        {"id": link["id"], "group_id": sauces.id, "category_id": lost.id}
    ]


@pytest.mark.django_db
def test_the_copy_gives_each_group_with_its_options_as_its_recover_takes_them():
    sauces = run_here("modifier.group.create", {
        "name": "Sauces", "kitchen_name": "SAU", "min_choices": 1, "max_choices": 2, "allow_repeat": True,
        "sort_order": 3,
    })
    run_here("modifier.option.create", {"group_id": str(sauces.id), "name": "Ketchup", "is_default": True})
    run_here("modifier.option.create", {
        "group_id": str(sauces.id), "name": "BBQ", "kitchen_name": "+BBQ", "price_delta": 50,
        "tax_category_key": GENERIC, "sort_order": 4,
    })
    # A group without options is one too.
    extras = a_group("Extras")
    generic = TaxCategory.objects.get(key=GENERIC).pk

    read = queries.groups_in_copy(direct())

    # Its options by the order they were added in, each with its tax category's id there, the same in the business.
    assert read == [
        {
            "id": sauces.id, "name": "Sauces", "kitchen_name": "SAU", "min_choices": 1, "max_choices": 2,
            "allow_repeat": True, "sort_order": 3, "options": [
                {"name": "Ketchup", "kitchen_name": "", "price_delta": 0, "tax_category_id": None, "is_default": True,
                 "sort_order": 0},
                {"name": "BBQ", "kitchen_name": "+BBQ", "price_delta": 50, "tax_category_id": generic,
                 "is_default": False, "sort_order": 4},
            ],
        },
        {
            "id": extras.id, "name": "Extras", "kitchen_name": "", "min_choices": 0, "max_choices": 0,
            "allow_repeat": False, "sort_order": 0, "options": [],
        },
    ]


@pytest.mark.django_db
def test_a_copy_without_the_groups_table_gives_no_group():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE modifier_modifiergroup CASCADE")

    assert queries.groups_in_copy(direct()) == []


def a_group_of_the_copy(name: str, *, id=None, options=()) -> dict:
    """A group as ``groups_in_copy`` gives it, none of its settings changed but its ``options``."""
    return {
        "id": id or uuid.uuid7(), "name": name, "kitchen_name": "", "min_choices": 0, "max_choices": 0,
        "allow_repeat": False, "sort_order": 0, "options": list(options),
    }


def an_option_of_the_copy(name: str, **fields) -> dict:
    """An option as ``groups_in_copy`` gives it."""
    return {
        "name": name, "kitchen_name": "", "price_delta": 0, "tax_category_id": None, "is_default": False,
        "sort_order": 0, **fields,
    }


@pytest.mark.django_db
def test_lacking_is_a_group_the_business_no_longer_holds_nor_made_again_with_its_name():
    generic = TaxCategory.objects.get(key=GENERIC).pk
    # Still held, renamed since: the business's, never a second one.
    renamed = a_group("Sauces")
    run_here("modifier.group.update", {"id": str(renamed.id), "name": "Dips"})
    still = a_group_of_the_copy("Sauces", id=renamed.id)
    # Made again by the business with its name, the case aside: its own, never a second one (the name is unique).
    a_group("EXTRAS")
    made_again = a_group_of_the_copy("Extras")
    # Gone altogether: lacking, with its options as their create takes them, each tax category by its key.
    sizes = a_group_of_the_copy("Sizes", options=[
        an_option_of_the_copy("Small", is_default=True),
        an_option_of_the_copy("Large", kitchen_name="L", price_delta=150, tax_category_id=generic, sort_order=1),
    ]) | {"kitchen_name": "SIZE", "min_choices": 1, "max_choices": 1, "allow_repeat": True, "sort_order": 2}

    lacking = queries.groups_not_in_business([still, made_again, sizes])

    assert lacking == [
        {
            "id": sizes["id"], "name": "Sizes", "kitchen_name": "SIZE", "min_choices": 1, "max_choices": 1,
            "allow_repeat": True, "sort_order": 2, "options": [
                {"name": "Small", "kitchen_name": "", "price_delta": 0, "tax_category_key": "", "is_default": True,
                 "sort_order": 0},
                {"name": "Large", "kitchen_name": "L", "price_delta": 150, "tax_category_key": GENERIC,
                 "is_default": False, "sort_order": 1},
            ],
        }
    ]


def a_group_brought_back(name: str) -> ModifierGroup:
    """A group a recovery from a separate copy made again, as ``modifier.group.recover`` leaves it."""
    return ModifierGroup.objects.create(name=name, created_by=actor_of(uuid.uuid7()))


@pytest.mark.django_db
def test_a_group_gone_stands_for_the_one_a_recovery_brought_back_with_its_name():
    kept = a_group("Sizes")
    back = a_group_brought_back("SAUCES")
    # Made again by hand with its name: the business's own, set up as it chose; it stands for none.
    a_group("Extras")
    lost, gone = uuid.uuid7(), uuid.uuid7()

    # Still held, renamed since, and its old name taken by one a recovery brought back: it is itself all the same.
    renamed = a_group("Portions")
    run_here("modifier.group.update", {"id": str(renamed.id), "name": "Rations"})
    a_group_brought_back("Portions")

    standing = queries.groups_standing_for(
        {kept.id: "Sizes", renamed.id: "Portions", lost: "Sauces", gone: "Extras"}
    )

    # One the business still holds is itself, and is not in it.
    assert standing == {lost: back.id}


@pytest.mark.django_db
def test_a_group_the_copy_also_holds_is_never_the_stand_in_of_another_with_its_name():
    # Brought back by an earlier recovery before the copy was made, then renamed as the lost one was called.
    earlier = a_group_brought_back("Dips")
    run_here("modifier.group.update", {"id": str(earlier.id), "name": "Sauces"})
    lost = uuid.uuid7()

    assert queries.groups_standing_for({lost: "Sauces", earlier.id: "Dips"}) == {}


@pytest.mark.django_db
def test_a_group_gone_hangs_again_as_the_one_a_recovery_brought_back_with_its_name():
    burger, fries = make_product("Burger", "BUR"), make_product("Fries", "FRI")
    mains = make_category("Mains")
    back = a_group_brought_back("Sauces")
    # Hung again by the business on the one brought back, after the recovery made it: the business's stays.
    hang(back, product=fries)
    # Made again by hand with its name: it keeps the copy's group, which the attach refuses as not found.
    a_group("Extras")
    lost, gone = uuid.uuid7(), uuid.uuid7()
    copy = {lost: "Sauces", gone: "Extras"}

    def on(group_id, product) -> dict:
        return {"id": uuid.uuid7(), "group_id": group_id, "product_id": product.id, "sku": product.sku,
                "copy_groups": copy}

    on_burger, on_fries, by_hand = on(lost, burger), on(lost, fries), on(gone, burger)
    on_mains = {"id": uuid.uuid7(), "group_id": lost, "category_id": mains.id, "copy_categories": {mains.id: "Mains"},
                "copy_groups": copy}

    assert queries.links_not_in_business([on_burger, on_fries, by_hand]) == [
        {"id": on_burger["id"], "group_id": back.id, "product_id": burger.id},
        {"id": by_hand["id"], "group_id": gone, "product_id": burger.id},
    ]
    assert queries.category_links_not_in_business([on_mains]) == [
        {"id": on_mains["id"], "group_id": back.id, "category_id": mains.id}
    ]


def recovered(record: dict, actor: str = "system"):
    """``record`` of ``groups_not_in_business`` made again as the platform does, as the system: all of it but its id
    in the copy."""
    return run_here(
        "modifier.group.recover", {key: value for key, value in record.items() if key != "id"},
        ctx=ctx_with("*", actor=actor),
    )


@pytest.mark.django_db
def test_a_group_comes_back_with_its_options_by_the_group_sheets_own_creates():
    actor = actor_of(uuid.uuid7())
    [record] = queries.groups_not_in_business([
        a_group_of_the_copy("Doneness", options=[
            an_option_of_the_copy("Rare", sort_order=1),
            an_option_of_the_copy("Medium", is_default=True, sort_order=2),
            an_option_of_the_copy("Truffle", kitchen_name="+TRF", price_delta=300,
                                  tax_category_id=TaxCategory.objects.get(key=GENERIC).pk, sort_order=3),
        ]) | {"kitchen_name": "POINT", "min_choices": 1, "max_choices": 1}
    ])

    made = recovered(record, actor)

    assert made.left_out == []
    group = ModifierGroup.objects.get(pk=made.id)
    assert (group.name, group.kitchen_name, group.min_choices, group.max_choices, group.created_by) == (
        "Doneness", "POINT", 1, 1, actor
    )
    assert list(
        group.options.values_list("name", "kitchen_name", "price_delta", "tax_category__key", "is_default", "sort_order")
    ) == [
        ("Rare", "", 0, None, False, 1),
        ("Medium", "", 0, None, True, 2),
        ("Truffle", "+TRF", 300, GENERIC, False, 3),
    ]
    # Each by its create: their events, as the recovery that made them.
    assert list(OutboxEvent.objects.filter(actor=actor).order_by("id").values_list("name", flat=True)) == [
        "modifier.group.created", "modifier.option.created", "modifier.option.created", "modifier.option.created"
    ]


@pytest.mark.django_db
def test_an_option_its_create_refuses_today_is_left_out_and_said_and_the_group_comes_back():
    generic = TaxCategory.objects.get(key=GENERIC)
    [record] = queries.groups_not_in_business([
        a_group_of_the_copy("Sauces", options=[
            an_option_of_the_copy("Wine sauce", price_delta=200, tax_category_id=generic.pk),
            an_option_of_the_copy("Ketchup", sort_order=1),
        ])
    ])
    # Taxes turned its tax category off since: the option sheet no longer takes it.
    TaxCategory.objects.filter(pk=generic.pk).update(is_active=False)

    with translation.override("es"):
        made = recovered(record)
        spanish = OPTION_LEFT % {"option": "Wine sauce", "why": TAX_CATEGORY_UNKNOWN}

    assert list(ModifierOption.objects.filter(group_id=made.id).values_list("name", flat=True)) == ["Ketchup"]
    # Said by the option's name in the language it is made in, with the create's own code and why.
    [said] = made.left_out
    assert (said.code, said.message) == ("invalid_field", spanish)
    assert spanish != OPTION_LEFT % {"option": "Wine sauce", "why": TAX_CATEGORY_UNKNOWN}


@pytest.mark.django_db
def test_an_option_named_as_one_already_back_in_its_group_is_left_out_with_why():
    [record] = queries.groups_not_in_business([
        a_group_of_the_copy("Sauces", options=[an_option_of_the_copy("Alioli"), an_option_of_the_copy("ALIOLI")])
    ])

    made = recovered(record)

    assert list(ModifierOption.objects.filter(group_id=made.id).values_list("name", flat=True)) == ["Alioli"]
    assert [one.code for one in made.left_out] == ["modifier.option_name_taken"]


@pytest.mark.django_db
def test_making_a_group_again_with_its_options_is_only_the_systems():
    op = get_operation("modifier.group.recover")

    assert op.permission == "modifier.system"
    assert not ctx_for("hub_owner").has(op.permission)


def test_the_app_declares_its_groups_first_made_again_with_their_options():
    groups, _categories, _links = apps.get_app_config("modifier").recoverable_from_copy()

    assert (groups.read, groups.missing, groups.create, groups.deleted, groups.restore) == (
        queries.groups_in_copy,
        queries.groups_not_in_business,
        "modifier.group.recover",
        None,
        "",
    )
    assert (str(groups.label), groups.reads_since) == ("Modifier groups", "0001_initial")
    # A copy that far back holds what the read takes: each column of a group and of an option it reads.
    assert {"id", *queries.GROUP_COPY_FIELDS} <= fields_held_since("modifier", "modifiergroup", groups.reads_since)
    assert {"id", "group", "tax_category", *queries.OPTION_COPY_FIELDS} <= fields_held_since(
        "modifier", "modifieroption", groups.reads_since
    )


def test_the_app_declares_its_groups_of_categories_first_hung_again_by_the_same_attach():
    _groups, categories, _links = apps.get_app_config("modifier").recoverable_from_copy()

    assert (categories.read, categories.missing, categories.create, categories.deleted, categories.restore) == (
        queries.category_links_in_copy,
        queries.category_links_not_in_business,
        "modifier.link.attach",
        None,
        "",
    )
    assert (str(categories.label), categories.reads_since) == ("Modifier groups of categories", "0001_initial")
    # A copy that far back holds what the read takes: the link's columns, its group's name, and of its category, those
    # of Inventory's migration that one depends on.
    assert {"id", "group", "category"} <= fields_held_since("modifier", "modifierlink", categories.reads_since)
    assert {"id", "name"} <= fields_held_since("modifier", "modifiergroup", categories.reads_since)
    assert {"id", "name", "is_deleted"} <= fields_held_since("inventory", "category", "0001_initial")


def test_the_app_declares_its_groups_of_products_hung_again_by_the_group_sheets_attach():
    _groups, _categories, links = apps.get_app_config("modifier").recoverable_from_copy()

    assert (links.read, links.missing, links.create, links.deleted, links.restore) == (
        queries.links_in_copy,
        queries.links_not_in_business,
        "modifier.link.attach",
        None,
        "",
    )
    assert (str(links.label), links.reads_since) == ("Modifier groups of products", "0001_initial")
    # A copy that far back holds what the read takes: the link's columns, its group's name, and of its product, those
    # of Inventory's migration that one depends on.
    assert {"id", "group", "product"} <= fields_held_since("modifier", "modifierlink", links.reads_since)
    assert {"id", "name"} <= fields_held_since("modifier", "modifiergroup", links.reads_since)
    assert {"sku", "is_deleted"} <= fields_held_since("inventory", "product", "0001_initial")


# ── End to end: the business's own database and its copy ────────────────────────────────────────────────────────────


@pytest.fixture
def recoveries(django_db_blocker, hub_databases):
    with django_db_blocker.unblock():
        made = Recoveries(hub_databases.template)
        yield made
        made.clean()


GROUPS = {
    "app": "modifier", "label": "Modifier groups of products", "restored": 0, "created": 0, "not_created": 0,
    "reasons": [], "refused": "",
}
CATEGORY_GROUPS = GROUPS | {"label": "Modifier groups of categories"}
MODIFIER_GROUPS = GROUPS | {"label": "Modifier groups"}


def said(row) -> tuple[str, list[dict]]:
    """``row``'s status and what each thing it gave back gave, by the keys these tests read."""
    keys = ("app", "label", "restored", "created", "not_created", "reasons", "refused")
    row = fresh(row)
    return row.status, [{key: result[key] for key in keys} for result in row.results]


def hung(hub) -> list[tuple]:
    """The business's groups hung from a product: group name and product id, by group name."""
    with use_hub(hub):
        return list(
            ModifierLink.objects.filter(product__isnull=False)
            .order_by("group__name")
            .values_list("group__name", "product_id")
        )


def hung_from_categories(hub) -> list[tuple]:
    """The business's groups hung from a category: group name and category id, by group name."""
    with use_hub(hub):
        return list(
            ModifierLink.objects.filter(category__isnull=False)
            .order_by("group__name")
            .values_list("group__name", "category_id")
        )


def asked_again_hangs_nothing_twice(recoveries, copy) -> None:
    """``copy`` asked again, Inventory and Modifiers: every group is in its place already, nothing is hung twice."""
    again = recoveries.ask(copy, "inventory", "modifier")
    assert run() == 1
    assert said(again) == ("done", [CATEGORIES, PRODUCTS, LINKS, MODIFIER_GROUPS, CATEGORY_GROUPS, GROUPS])


def attached(hub) -> int:
    with use_hub(hub):
        return OutboxEvent.objects.filter(name="modifier.link.attached").count()


@pytest.mark.usefixtures("no_test_fallback")
class TestGroupsComeBack:
    def a_business(self, recoveries, every_app_on):
        """A business with a burger that asks for «Sauces» and «Extras», by their screens' operations: the hub, the
        burger's id and the groups' ids."""
        hub, _ = recoveries.business(every_app_on)
        burger = run_in(hub, "inventory.product.create", name="Burger", sku="BUR", price=900,
                        tax_category_key=a_tax_key(hub)).id
        groups = {}
        for name in ("Sauces", "Extras"):
            groups[name] = run_in(hub, "modifier.group.create", name=name).id
            run_in(hub, "modifier.link.attach", group_id=groups[name], product_id=burger)
        return hub, burger, groups

    def deleted(self, hub, product) -> None:
        """``product`` deleted in the business, and its groups let go as the relay hands its deletion to Modifiers."""
        run_in(hub, "inventory.product.delete", id=product)
        run_in(hub, "modifier.link.drop_product", id=product)
        assert hung(hub) == []

    def test_a_deleted_product_comes_back_asking_for_its_groups(self, recoveries, every_app_on):
        hub, burger, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        before = attached(hub)
        row = recoveries.ask(copy, "modifier", "inventory")

        assert run() == 1

        # Inventory first, whatever the order asked: the product is back, the same, before its groups are hung.
        assert said(row) == (
            "done", [CATEGORIES, PRODUCTS | {"restored": 1}, LINKS, MODIFIER_GROUPS, CATEGORY_GROUPS, GROUPS | {"created": 2}]
        )
        assert hung(hub) == [("Extras", burger), ("Sauces", burger)]
        with use_hub(hub):
            assert set(ModifierLink.objects.values_list("created_by", flat=True)) == {actor_of(row.pk)}
        assert attached(hub) == before + 2
        asked_again_hangs_nothing_twice(recoveries, copy)
        assert len(hung(hub)) == 2

    def test_a_product_gone_altogether_comes_back_as_a_new_one_asking_for_its_groups(self, recoveries, every_app_on):
        hub, burger, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        gone_altogether(hub, burger)
        row = recoveries.ask(copy, "modifier", "inventory")

        assert run() == 1

        assert said(row) == (
            "done", [CATEGORIES, PRODUCTS | {"created": 1}, LINKS, MODIFIER_GROUPS, CATEGORY_GROUPS, GROUPS | {"created": 2}]
        )
        with use_hub(hub):
            [made] = Product.objects.filter(sku="BUR").values_list("pk", flat=True)
        assert made != burger
        assert hung(hub) == [("Extras", made), ("Sauces", made)]
        # Its groups are in their place on the one made again.
        asked_again_hangs_nothing_twice(recoveries, copy)
        assert len(hung(hub)) == 2

    def test_a_product_gone_the_business_made_again_by_hand_keeps_its_own_groups(self, recoveries, every_app_on):
        hub, burger, groups = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        gone_altogether(hub, burger)
        # Made again by hand with its SKU, the business hung only «Extras» from it.
        made = run_in(hub, "inventory.product.create", name="Burger", sku="BUR", price=900,
                      tax_category_key=a_tax_key(hub)).id
        run_in(hub, "modifier.link.attach", group_id=groups["Extras"], product_id=made)
        row = recoveries.ask(copy, "inventory", "modifier")

        assert run() == 1

        status, results = said(row)
        assert (status, results[1]["created"], results[-1]["created"], results[-1]["not_created"]) == ("done", 0, 0, 2)
        assert [reason["reason"].split(":")[0] for reason in results[-1]["reasons"]] == ["not_found", "not_found"]
        assert hung(hub) == [("Extras", made)]

    def test_a_group_the_business_hung_again_stays_as_it_is(self, recoveries, every_app_on):
        hub, burger, groups = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        recoveries.ask(copy, "inventory")
        assert run() == 1
        # The product back without its groups, the business hung «Sauces» again by hand.
        run_in(hub, "modifier.link.attach", group_id=groups["Sauces"], product_id=burger)
        row = recoveries.ask(copy, "modifier")

        assert run() == 1

        assert said(row) == ("done", [MODIFIER_GROUPS, CATEGORY_GROUPS, GROUPS | {"created": 1}])
        assert hung(hub) == [("Extras", burger), ("Sauces", burger)]
        with use_hub(hub):
            assert ModifierLink.objects.get(group_id=groups["Sauces"]).created_by == "system"

    def test_a_group_that_cannot_hang_now_does_not_come_back_and_says_why(self, recoveries, every_app_on):
        hub, burger, groups = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        # Without Products asked, the burger stays deleted: as the group sheet, nothing is hung from it.
        row = recoveries.ask(copy, "modifier")

        assert run() == 1

        status, [of_groups, of_categories, result] = said(row)
        assert (of_groups, of_categories) == (MODIFIER_GROUPS, CATEGORY_GROUPS)
        assert (status, result["created"], result["not_created"], result["refused"]) == ("done", 0, 2, "")
        assert [reason["reason"].split(":")[0] for reason in result["reasons"]] == ["not_found", "not_found"]
        assert hung(hub) == []

    def with_options(self, hub, group) -> None:
        """``group`` with two options, the first chosen by default."""
        run_in(hub, "modifier.option.create", group_id=group, name="Ketchup", is_default=True)
        run_in(hub, "modifier.option.create", group_id=group, name="BBQ", kitchen_name="+BBQ", price_delta=50,
               sort_order=1)

    def test_a_group_the_business_deleted_since_comes_back_with_its_options_and_hung(self, recoveries, every_app_on):
        hub, burger, groups = self.a_business(recoveries, every_app_on)
        self.with_options(hub, groups["Sauces"])
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        run_in(hub, "modifier.group.delete", id=groups["Sauces"])
        row = recoveries.ask(copy, "inventory", "modifier")

        assert run() == 1

        # The group first, made again by the group sheet's create with its options, then hung from the burger back.
        assert said(row) == (
            "done",
            [CATEGORIES, PRODUCTS | {"restored": 1}, LINKS, MODIFIER_GROUPS | {"created": 1}, CATEGORY_GROUPS,
             GROUPS | {"created": 2}],
        )
        with use_hub(hub):
            back = ModifierGroup.objects.get(name="Sauces")
            options = list(back.options.values_list("name", "kitchen_name", "price_delta", "is_default", "sort_order"))
        assert (back.pk != groups["Sauces"], back.created_by) == (True, actor_of(row.pk))
        assert options == [("Ketchup", "", 0, True, 0), ("BBQ", "+BBQ", 50, False, 1)]
        assert hung(hub) == [("Extras", burger), ("Sauces", burger)]
        # Asked again: the group is the business's now, none made twice, nor an option added twice.
        asked_again_hangs_nothing_twice(recoveries, copy)
        with use_hub(hub):
            assert (ModifierGroup.objects.count(), back.options.count()) == (2, 2)

    def test_a_group_the_business_made_again_by_hand_stays_as_it_is(self, recoveries, every_app_on):
        hub, burger, groups = self.a_business(recoveries, every_app_on)
        self.with_options(hub, groups["Sauces"])
        copy = recoveries.copy_of(hub)
        with use_hub(hub):
            sauces_link = ModifierLink.objects.get(group_id=groups["Sauces"]).id
        self.deleted(hub, burger)
        run_in(hub, "modifier.group.delete", id=groups["Sauces"])
        # Made again by hand with its name, with an option of its own and hung from nothing.
        mine = run_in(hub, "modifier.group.create", name="SAUCES").id
        run_in(hub, "modifier.option.create", group_id=mine, name="Mayo")
        row = recoveries.ask(copy, "inventory", "modifier")

        assert run() == 1

        # Not made twice; its link in the copy finds no group of its own (the business's is its own): not created, and
        # why.
        status, results = said(row)
        assert (status, results[3], results[-1]["created"], results[-1]["not_created"]) == (
            "done", MODIFIER_GROUPS, 1, 1
        )
        assert [(reason["id"], reason["reason"].split(":")[0]) for reason in results[-1]["reasons"]] == [
            (str(sauces_link), "not_found")
        ]
        with use_hub(hub):
            assert list(ModifierGroup.objects.order_by("name").values_list("name", flat=True)) == ["Extras", "SAUCES"]
            assert list(ModifierOption.objects.filter(group_id=mine).values_list("name", flat=True)) == ["Mayo"]
        assert hung(hub) == [("Extras", burger)]

    def test_an_option_that_cannot_come_back_is_noted_and_its_group_comes_back(self, recoveries, every_app_on):
        hub, burger, groups = self.a_business(recoveries, every_app_on)
        with use_hub(hub):
            own = TaxCategory.objects.filter(is_active=True).exclude(key=a_tax_key(hub)).order_by("key").first()
        run_in(hub, "modifier.option.create", group_id=groups["Sauces"], name="Wine sauce", price_delta=200,
               tax_category_key=own.key)
        run_in(hub, "modifier.option.create", group_id=groups["Sauces"], name="Ketchup", sort_order=1)
        copy = recoveries.copy_of(hub)
        run_in(hub, "modifier.group.delete", id=groups["Sauces"])
        # Taxes turned its tax category off since: the option sheet no longer takes it.
        with use_hub(hub):
            TaxCategory.objects.filter(pk=own.pk).update(is_active=False)
        row = recoveries.ask(copy, "modifier")

        assert run() == 1

        # The group back, without the option, counted and said by the group's id in the copy, and hung again.
        [made, of_categories, of_products] = fresh(row).results
        assert (made["label"], made["created"], made["noted"], of_categories, of_products["created"]) == (
            "Modifier groups", 1, 1, CATEGORY_GROUPS, 1
        )
        assert [(note["id"], note["note"].split(":")[0]) for note in made["notes"]] == [
            (str(groups["Sauces"]), "invalid_field")
        ]
        assert "Wine sauce" in made["notes"][0]["note"]
        with use_hub(hub):
            assert list(ModifierOption.objects.filter(group__name="Sauces").values_list("name", flat=True)) == [
                "Ketchup"
            ]
        assert hung(hub) == [("Extras", burger), ("Sauces", burger)]


@pytest.mark.usefixtures("no_test_fallback")
class TestCategoryGroupsComeBack:
    def a_business(self, recoveries, every_app_on):
        """A business whose category «Mains» asks for «Sauces» and «Extras», by their screens' operations: the hub,
        the category's id and the groups' ids; the links' ids, the copy's to be, in ``copied_links``."""
        hub, _ = recoveries.business(every_app_on)
        mains = run_in(hub, "inventory.category.create", name="Mains").id
        groups, self.copied_links = {}, []
        for name in ("Sauces", "Extras"):
            groups[name] = run_in(hub, "modifier.group.create", name=name).id
            self.copied_links.append(run_in(hub, "modifier.link.attach", group_id=groups[name], category_id=mains).id)
        return hub, mains, groups

    def deleted(self, hub, category) -> None:
        """``category`` deleted in the business, and its groups let go as the relay hands its deletion to Modifiers."""
        run_in(hub, "inventory.category.delete", id=category)
        run_in(hub, "modifier.link.drop_category", id=category)
        assert hung_from_categories(hub) == []

    def test_a_deleted_category_comes_back_asking_for_its_groups(self, recoveries, every_app_on):
        hub, mains, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, mains)
        before = attached(hub)
        row = recoveries.ask(copy, "modifier", "inventory")

        assert run() == 1

        # Inventory first: the category comes back as a new one, and its groups are hung from that one.
        with use_hub(hub):
            back = Category.objects.get(name="Mains", is_deleted=False).pk
        assert back != mains
        assert said(row) == (
            "done", [CATEGORIES | {"created": 1}, PRODUCTS, LINKS, MODIFIER_GROUPS, CATEGORY_GROUPS | {"created": 2}, GROUPS]
        )
        assert hung_from_categories(hub) == [("Extras", back), ("Sauces", back)]
        with use_hub(hub):
            assert set(ModifierLink.objects.values_list("created_by", flat=True)) == {actor_of(row.pk)}
        assert attached(hub) == before + 2
        # Its groups are in their place on the one brought back.
        asked_again_hangs_nothing_twice(recoveries, copy)
        assert len(hung_from_categories(hub)) == 2

    def test_a_category_that_stays_deleted_gets_no_group_and_says_why(self, recoveries, every_app_on):
        hub, mains, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, mains)
        # Without Products asked, the category stays deleted: as the group sheet, nothing is hung from it.
        row = recoveries.ask(copy, "modifier")

        assert run() == 1

        assert said(row)[0] == "done"
        [of_groups, result, of_products] = fresh(row).results
        assert (of_groups, of_products) == (MODIFIER_GROUPS, GROUPS)
        assert (result["label"], result["created"], result["not_created"], result["refused"]) == (
            "Modifier groups of categories", 0, 2, ""
        )
        # By the link's id in the copy, and why.
        assert sorted(reason["id"] for reason in result["reasons"]) == sorted(str(one) for one in self.copied_links)
        assert [reason["reason"].split(":")[0] for reason in result["reasons"]] == ["not_found", "not_found"]
        assert hung_from_categories(hub) == []

    def test_a_category_the_business_made_again_by_hand_keeps_its_own_groups(self, recoveries, every_app_on):
        hub, mains, groups = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, mains)
        # Made again by hand with its name, the business hung only «Extras» from it.
        made = run_in(hub, "inventory.category.create", name="Mains").id
        run_in(hub, "modifier.link.attach", group_id=groups["Extras"], category_id=made)
        row = recoveries.ask(copy, "inventory", "modifier")

        assert run() == 1

        status, results = said(row)
        # Inventory makes no second «Mains», and the copy's groups find no category of theirs: not created, and why.
        assert (status, results[0]["created"], results[-2]["created"], results[-2]["not_created"]) == ("done", 0, 0, 2)
        assert [reason["reason"].split(":")[0] for reason in results[-2]["reasons"]] == ["not_found", "not_found"]
        assert hung_from_categories(hub) == [("Extras", made)]
