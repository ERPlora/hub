"""What Menus gives back from a separate copy of the business (BASE-F114, COMBO-F15).

The copy is no business, so it has no alias and the ORM never reaches it: the platform reads it through a direct,
read-only connection, and Menus answers with its own SQL over its models' names. First each menu the business no
longer has, made again by ``combo.combo.recover``; then each course its menu no longer has, added again by
``combo.group.recover``; both keep which of the copy's they stand for. Then each choice of a live product that the
business no longer offers in that course is offered again by ``combo.option.create``, the menu builder's own, in the
course that stands for the copy's, unless the business still holds it or offered that product in that course again.
Menus goes after Inventory (its ``requires``), so a deleted product is back, the same, before its choices are offered.

Then, end to end on real databases (``hubs.CopiedHubs``): the business's own and its copy, a clone of it.
"""

import uuid

import pytest
from django.apps import apps
from django.db import connection
from live.errors import InvalidPayload
from live.models import OutboxEvent
from live.operations import get

from apps.combo import queries
from apps.combo.models import ChoiceGroup, ChoiceOption, Combo
from apps.inventory.models import Product
from apps.inventory.tests.test_recovery import (
    CATEGORIES,
    LINKS,
    PRODUCTS,
    a_tax_key,
    gone_altogether,
    made_by_a_recovery,
)
from base.recovery import actor_of
from base.tenancy.context import use_hub
from base.tenancy.tests.test_recovery import Recoveries, fields_held_since, fresh, run, run_in
from base.tests.test_image_catalog import image_library  # noqa: F401 - the library fixture

from .conftest import FOOD, ctx_for, make_combo, make_group, make_option, make_product, tax_category


#: An image of the shared library a menu may show (``image_library`` has it).
LIBRARY_IMAGE = "catalog:hospitality/cafe_solo"


def direct():
    """The raw connection of the tests' database, as the platform's direct one reads the copy."""
    connection.ensure_connection()
    return connection.connection


@pytest.mark.django_db
def test_the_copy_gives_each_choice_of_a_live_product_with_what_its_create_takes():
    lentils, soup = make_product("Lentils", sku="LEN"), make_product("Soup", sku="SOU")
    steak = make_product("Steak", sku="STE")
    menu = make_combo()
    starters, mains = make_group(menu, "Starters"), make_group(menu, "Mains")
    # Read in each course's order, whatever order they were added in.
    on_soup = make_option(starters, soup, sort_order=1, price_delta=-50, is_available=False)
    on_lentils = make_option(starters, lentils, sort_order=0)
    on_steak = make_option(mains, steak, price_delta=300)
    # Nor a deleted product's, whose choices its deletion takes away (before the relay's tick, still there).
    old = make_product("Old")
    make_option(mains, old)
    Product.objects.filter(pk=old.pk).update(is_deleted=True)

    read = queries.options_in_copy(direct())

    # With each product's SKU there, the article's identity, to find the one made again if the business lost it.
    assert read == [
        {"id": on_lentils.id, "group_id": starters.id, "product_id": lentils.id, "price_delta": 0, "is_available": True,
         "sku": "LEN"},
        {"id": on_soup.id, "group_id": starters.id, "product_id": soup.id, "price_delta": -50, "is_available": False,
         "sku": "SOU"},
        {"id": on_steak.id, "group_id": mains.id, "product_id": steak.id, "price_delta": 300, "is_available": True,
         "sku": "STE"},
    ]


@pytest.mark.django_db
def test_a_copy_without_the_apps_table_gives_nothing():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE combo_choiceoption CASCADE")

    assert queries.options_in_copy(direct()) == []


def a_choice_of_the_copy(group, product, **fields) -> dict:
    return {"id": uuid.uuid7(), "group_id": group.id, "product_id": product.id, "price_delta": 0,
            "is_available": True, "sku": product.sku} | fields


def a_choice_of_a_product_gone(group, sku: str, product_id=None, **fields) -> dict:
    """A choice of the copy whose product the business no longer holds at all: only its SKU says which article it
    was."""
    return {"id": uuid.uuid7(), "group_id": group.id, "product_id": product_id or uuid.uuid7(), "price_delta": 0,
            "is_available": True, "sku": sku} | fields


@pytest.mark.django_db
def test_lacking_is_a_choice_the_business_no_longer_offers_in_that_course():
    lentils, soup, steak = make_product("Lentils"), make_product("Soup"), make_product("Steak")
    menu = make_combo()
    starters, mains = make_group(menu, "Starters"), make_group(menu, "Mains")
    # Still in the business, with the product the business replaced it with since: it is the business's, nothing lacks.
    held = make_option(mains, steak)
    still = a_choice_of_the_copy(mains, soup) | {"id": held.id}
    # Offered again by the business since, under another id and supplement: the business's stays, never a second one.
    make_option(starters, lentils, price_delta=100)
    offered_again = a_choice_of_the_copy(starters, lentils)
    # Lacking: the same course with another product, and the same product in another course.
    other_product = a_choice_of_the_copy(starters, soup, price_delta=-50, is_available=False)
    other_course = a_choice_of_the_copy(mains, lentils, price_delta=200)

    lacking = queries.options_not_in_business([still, offered_again, other_product, other_course])

    # As the menu builder's create takes each, with its id in the copy: the course, the product and what it adds.
    assert lacking == [
        {"id": other_product["id"], "group_id": starters.id, "product_id": soup.id, "price_delta": -50,
         "is_available": False},
        {"id": other_course["id"], "group_id": mains.id, "product_id": lentils.id, "price_delta": 200,
         "is_available": True},
    ]


@pytest.mark.django_db
def test_a_product_gone_gets_its_choices_on_the_one_a_recovery_made_again_with_its_sku():
    burger = made_by_a_recovery("Burger", "BUR")
    menu = make_combo()
    starters, mains = make_group(menu, "Starters"), make_group(menu, "Mains")
    # Offered again by the business on the one made again, after the recovery made it: the business's stays.
    make_option(mains, burger, price_delta=400)
    offered_again = a_choice_of_a_product_gone(mains, "BUR", price_delta=150)
    gone = offered_again["product_id"]
    # Lacking: the same course with the one made again of another article, and the one made again in another course.
    fries = made_by_a_recovery("Fries", "FRI")
    other_product = a_choice_of_a_product_gone(mains, "FRI", price_delta=50)
    other_course = a_choice_of_a_product_gone(starters, "BUR", gone, is_available=False)
    # Made again by hand with its SKU: the business's own, set up as it chose; it keeps the copy's product, which the
    # menu builder refuses as not in the hub: not created, and why.
    make_product("Salad", sku="SAL")
    by_hand = a_choice_of_a_product_gone(starters, "SAL")

    lacking = queries.options_not_in_business([offered_again, other_product, other_course, by_hand])

    assert lacking == [
        {"id": other_product["id"], "group_id": mains.id, "product_id": fries.id, "price_delta": 50,
         "is_available": True},
        {"id": other_course["id"], "group_id": starters.id, "product_id": burger.id, "price_delta": 0,
         "is_available": False},
        {"id": by_hand["id"], "group_id": starters.id, "product_id": by_hand["product_id"], "price_delta": 0,
         "is_available": True},
    ]


def test_with_nothing_read_nothing_is_lacking():
    assert queries.options_not_in_business([]) == []
    assert queries.combos_not_in_business([]) == []
    assert queries.groups_not_in_business([]) == []


@pytest.mark.django_db
def test_a_choice_of_a_course_gone_goes_to_the_one_a_recovery_made_again_for_it():
    lentils, soup = make_product("Lentils"), make_product("Soup")
    menu = make_combo()
    gone, made_by_hand = uuid.uuid7(), uuid.uuid7()
    # Made again by a recovery for the copy's course (the oldest, if it made it twice), renamed since.
    sides = make_group(menu, "Side dishes", stands_for=gone)
    make_group(make_combo("Kids' menu"), "Sides", stands_for=gone)
    # Offered there by the business already: the business's stays, never a second one.
    make_option(sides, soup, price_delta=300)
    offered_again = a_choice_of_the_copy(sides, soup) | {"group_id": gone}
    lacking_there = a_choice_of_the_copy(sides, lentils, price_delta=100) | {"group_id": gone}
    # A course the business made again by hand with its name is its own: it stands for none, and the choice keeps the
    # copy's course, which the menu builder refuses as not found.
    make_group(menu, "Desserts")
    by_hand = a_choice_of_the_copy(sides, lentils) | {"group_id": made_by_hand}

    lacking = queries.options_not_in_business([offered_again, lacking_there, by_hand])

    assert lacking == [
        {"id": lacking_there["id"], "group_id": sides.id, "product_id": lentils.id, "price_delta": 100,
         "is_available": True},
        {"id": by_hand["id"], "group_id": made_by_hand, "product_id": lentils.id, "price_delta": 0,
         "is_available": True},
    ]


# ── Menus and their courses (hub#1474): one the business withdrew comes back as a new one ──────────────────────────


@pytest.mark.django_db
def test_the_copy_gives_each_menu_with_what_its_recover_takes():
    day = make_combo("Menu of the day", sort_order=1)
    takeaway = make_combo(
        "Sandwich and beer", price=900, supply_kind="goods", kitchen_name="SANDWICH", sort_order=0, is_active=False,
        image=LIBRARY_IMAGE,
    )

    read = queries.combos_in_copy(direct())

    # In the menus' order, with the id of its tax category there (Taxes never deletes one).
    assert read == [
        {"id": takeaway.id, "name": "Sandwich and beer", "kitchen_name": "SANDWICH", "price": 900,
         "supply_kind": "goods", "sort_order": 0, "is_active": False, "image": LIBRARY_IMAGE, "tax_category_id": None},
        {"id": day.id, "name": "Menu of the day", "kitchen_name": "", "price": 1350, "supply_kind": "service",
         "sort_order": 1, "is_active": True, "image": "", "tax_category_id": day.tax_category_id},
    ]


@pytest.mark.django_db
def test_the_copy_gives_each_course_menu_by_menu_in_its_order():
    day, kids = make_combo("Menu of the day"), make_combo("Kids' menu")
    mains = make_group(day, "Mains", sort_order=1, min_choices=1, max_choices=2, allow_repeat=True)
    starters = make_group(day, "Starters", sort_order=0, min_choices=0, max_choices=0)
    drink = make_group(kids, "Drink", sort_order=0)

    read = queries.groups_in_copy(direct())

    assert read == [
        {"id": starters.id, "combo_id": day.id, "name": "Starters", "min_choices": 0, "max_choices": 0,
         "allow_repeat": False},
        {"id": mains.id, "combo_id": day.id, "name": "Mains", "min_choices": 1, "max_choices": 2,
         "allow_repeat": True},
        {"id": drink.id, "combo_id": kids.id, "name": "Drink", "min_choices": 1, "max_choices": 1,
         "allow_repeat": False},
    ]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("table", "read"), [("combo_combo", "combos_in_copy"), ("combo_choicegroup", "groups_in_copy")]
)
def test_a_copy_without_the_menus_or_the_courses_table_gives_none(table, read):
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute(f"DROP TABLE {table} CASCADE")

    assert getattr(queries, read)(direct()) == []


def a_menu_of_the_copy(name: str = "Menu of the day", **fields) -> dict:
    return {"id": uuid.uuid7(), "name": name, "kitchen_name": "", "price": 1350, "supply_kind": "service",
            "sort_order": 0, "is_active": True, "image": "", "tax_category_id": tax_category(FOOD).id} | fields


def as_recovered(menu: dict) -> dict:
    """``menu`` of the copy as ``combo.combo.recover`` takes it, with its id there."""
    fields = ("id", "name", "kitchen_name", "price", "supply_kind", "sort_order", "is_active", "image")
    key = FOOD if menu["tax_category_id"] is not None else None
    return {field: menu[field] for field in fields} | {"tax_category_key": key, "stands_for": menu["id"]}


@pytest.mark.django_db
def test_lacking_is_a_menu_the_business_no_longer_has():
    held = make_combo("Menu of the day")
    still = a_menu_of_the_copy("Its old name") | {"id": held.id}
    # Made again by a recovery for it, and renamed since: it stands for it, never a second one.
    brought = a_menu_of_the_copy("Kids' menu")
    make_combo("Children's menu", stands_for=brought["id"])
    # Made again by hand with its name (the case and the spaces aside): the business's own, never a second one.
    make_combo("tasting  MENU")
    by_hand = a_menu_of_the_copy("Tasting menu")
    # Two of the copy with one name and one made again by hand: it stands for the oldest, the other is lacking.
    make_combo("Brunch")
    brunch, other_brunch = a_menu_of_the_copy("Brunch"), a_menu_of_the_copy("Brunch", price=2000)
    # Two of the copy with one name, one made again by a recovery: it is that one's, never the other's.
    dinner, other_dinner = a_menu_of_the_copy("Dinner"), a_menu_of_the_copy("Dinner")
    make_combo("Dinner", stands_for=dinner["id"])
    # Lacking: one eaten in, with the key of its tax category; one to take away without one, off sale, with its image.
    vegan = a_menu_of_the_copy("Vegan menu", kitchen_name="VEGAN", price=1250, sort_order=3)
    takeaway = a_menu_of_the_copy(
        "Sandwich and beer", supply_kind="goods", tax_category_id=None, is_active=False, image=LIBRARY_IMAGE
    )

    lacking = queries.combos_not_in_business(
        [still, brought, by_hand, other_brunch, brunch, dinner, other_dinner, vegan, takeaway]
    )

    assert lacking == [
        as_recovered(other_brunch), as_recovered(other_dinner), as_recovered(vegan), as_recovered(takeaway)
    ]


def a_course_of_the_copy(menu_id, name: str = "Sides", **fields) -> dict:
    return {"id": uuid.uuid7(), "combo_id": menu_id, "name": name, "min_choices": 1, "max_choices": 1,
            "allow_repeat": False} | fields


@pytest.mark.django_db
def test_lacking_is_a_course_its_menu_no_longer_has():
    menu = make_combo("Menu of the day")
    mains = make_group(menu, "Mains")
    still = a_course_of_the_copy(menu.id, "Its old name") | {"id": mains.id}
    # Made again by a recovery for it, and renamed since: it stands for it, never a second one.
    brought = a_course_of_the_copy(menu.id, "Desserts")
    make_group(menu, "Sweets", stands_for=brought["id"])
    # Its name taken in its menu since (the case aside, as the menu builder refuses it): the business's stays.
    make_group(menu, "STARTERS")
    taken = a_course_of_the_copy(menu.id, "Starters")
    # Lacking in the menu the business holds, with the copy's picks.
    sides = a_course_of_the_copy(menu.id, "Sides", min_choices=0, max_choices=2, allow_repeat=True)
    # Lacking in a menu gone, to the one a recovery made again for it; a name another menu has is no matter.
    gone = uuid.uuid7()
    again = make_combo("Kids' menu", stands_for=gone)
    make_group(again, "Sides")
    drink = a_course_of_the_copy(gone, "Drink")
    # Lacking in a menu gone that nothing made again for it (the business made its own by hand, or it did not come
    # back): with the copy's menu, which the menu builder refuses as not found.
    lost = uuid.uuid7()
    make_combo("Brunch")
    eggs = a_course_of_the_copy(lost, "Eggs")

    lacking = queries.groups_not_in_business([still, brought, taken, sides, drink, eggs])

    assert lacking == [
        sides | {"stands_for": sides["id"]},
        drink | {"combo_id": again.id, "stands_for": drink["id"]},
        eggs | {"stands_for": eggs["id"]},
    ]


def made_again(record: dict, operation: str):
    """``record`` made again as the platform does, with every permission: its input, all of it but its id there."""
    op = get(operation)
    ctx = ctx_for(actor="system", permissions={"*"})
    return op(ctx, op.input.model_validate({key: value for key, value in record.items() if key != "id"}))


def combo_events() -> list[str]:
    return list(OutboxEvent.objects.filter(name__startswith="combo.").order_by("id").values_list("name", flat=True))


@pytest.mark.django_db
def test_a_menu_made_again_is_its_screens_create_with_its_image_and_which_it_stands_for(image_library):  # noqa: F811
    [record] = queries.combos_not_in_business(
        [a_menu_of_the_copy("Vegan menu", kitchen_name="VEGAN", price=1250, sort_order=3, is_active=False,
                            image=LIBRARY_IMAGE)]
    )

    made = made_again(record, "combo.combo.recover")

    menu = Combo.objects.select_related("tax_category").get(pk=made.id)
    assert (
        menu.name, menu.kitchen_name, menu.price, menu.supply_kind, menu.tax_category.key, menu.sort_order,
        menu.is_active, menu.image, menu.stands_for, made.image,
    ) == ("Vegan menu", "VEGAN", 1250, "service", FOOD, 3, False, LIBRARY_IMAGE, record["id"], LIBRARY_IMAGE)
    # As the screens do it: the create, then its image (COMBO-F14).
    assert combo_events() == ["combo.combo.created", "combo.combo.updated"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "image",
    [
        # A copy is of the database, never of the files: the photo went with the menu.
        "file:combo/combos/0193a1b2c3d47e8f9a0b1c2d3e4f5a6b.webp",
        # The library no longer has it.
        "catalog:hospitality/churros",
        "",
    ],
)
def test_a_menu_made_again_without_an_image_of_the_library_is_the_screens_create(image_library, image):  # noqa: F811
    [record] = queries.combos_not_in_business([a_menu_of_the_copy(image=image)])

    made = made_again(record, "combo.combo.recover")

    assert (made.image, Combo.objects.get(pk=made.id).image) == ("", "")
    assert combo_events() == ["combo.combo.created"]


@pytest.mark.django_db
def test_a_menu_whose_tax_category_was_turned_off_since_is_refused_as_its_screen_refuses_it():
    off = tax_category("restaurant.closed")
    off.is_active = False
    off.save(update_fields=["is_active"])
    [record] = queries.combos_not_in_business([a_menu_of_the_copy(tax_category_id=off.id)])

    with pytest.raises(InvalidPayload) as refused:
        made_again(record, "combo.combo.recover")

    assert (refused.value.code, list(refused.value.fields)) == ("invalid_field", ["tax_category_key"])
    assert not Combo.objects.exists()


@pytest.mark.django_db
def test_a_course_made_again_goes_last_in_its_menu_and_keeps_which_it_stands_for():
    menu = make_combo()
    make_group(menu, "Mains")
    [record] = queries.groups_not_in_business(
        [a_course_of_the_copy(menu.id, "Sides", min_choices=0, max_choices=2, allow_repeat=True)]
    )

    made = made_again(record, "combo.group.recover")

    course = ChoiceGroup.objects.get(pk=made.id)
    assert (
        course.combo_id, course.name, course.min_choices, course.max_choices, course.allow_repeat, course.sort_order,
        course.stands_for,
    ) == (menu.id, "Sides", 0, 2, True, 1, record["id"])
    assert combo_events() == ["combo.group.created"]


def test_the_app_declares_its_menus_then_their_courses_then_their_choices():
    menus, courses, choices = apps.get_app_config("combo").recoverable_from_copy()

    assert [
        (str(one.label), one.read, one.missing, one.create, one.deleted, one.restore)
        for one in (menus, courses, choices)
    ] == [
        ("Menus", queries.combos_in_copy, queries.combos_not_in_business, "combo.combo.recover", None, ""),
        ("Menu courses", queries.groups_in_copy, queries.groups_not_in_business, "combo.group.recover", None, ""),
        (
            "Menu choices of products",
            queries.options_in_copy,
            queries.options_not_in_business,
            "combo.option.create",
            None,
            "",
        ),
    ]
    # What each read names is in a copy at its migration, never a column a later one adds: the menu's image is
    # 0002_combo_image's.
    assert (menus.reads_since, courses.reads_since, choices.reads_since) == (
        "0002_combo_image", "0001_initial", "0001_initial"
    )
    assert {
        "id", "name", "kitchen_name", "price", "supply_kind", "tax_category", "sort_order", "is_active", "image"
    } <= fields_held_since("combo", "combo", menus.reads_since)
    assert {"id", "combo", "name", "min_choices", "max_choices", "allow_repeat", "sort_order"} <= fields_held_since(
        "combo", "choicegroup", courses.reads_since
    )
    # The choice's columns, and the product's it joins (Inventory's 0001_initial, which Menus' first migration depends
    # on).
    assert {"id", "group", "product", "price_delta", "is_available", "sort_order"} <= fields_held_since(
        "combo", "choiceoption", choices.reads_since
    )
    assert {"id", "sku", "is_deleted"} <= fields_held_since("inventory", "product", "0001_initial")


# ── End to end: the business's own database and its copy ────────────────────────────────────────────────────────────


@pytest.fixture
def recoveries(django_db_blocker, hub_databases):
    with django_db_blocker.unblock():
        made = Recoveries(hub_databases.template)
        yield made
        made.clean()


CHOICES = {
    "app": "combo", "label": "Menu choices of products", "restored": 0, "created": 0, "not_created": 0,
    "reasons": [], "refused": "",
}
MENUS = CHOICES | {"label": "Menus"}
COURSES = CHOICES | {"label": "Menu courses"}


def said(row) -> tuple[str, list[dict]]:
    """``row``'s status and what each thing it gave back gave, by the keys these tests read."""
    keys = ("app", "label", "restored", "created", "not_created", "reasons", "refused")
    row = fresh(row)
    return row.status, [{key: result[key] for key in keys} for result in row.results]


def offered(hub) -> list[tuple]:
    """The business's choices: course name, product id, supplement and whether it is offered today, by course."""
    with use_hub(hub):
        return list(
            ChoiceOption.objects.order_by("group__name", "sort_order")
            .values_list("group__name", "product_id", "price_delta", "is_available")
        )


def created_by(hub) -> list[str]:
    """Who made each choice the business was told was created, in order."""
    with use_hub(hub):
        return list(OutboxEvent.objects.filter(name="combo.option.created").order_by("created_at", "id").values_list("actor", flat=True))


@pytest.mark.usefixtures("no_test_fallback")
class TestChoicesComeBack:
    def a_business(self, recoveries, every_app_on):
        """A business whose menu of the day offers a burger as a main with a supplement and fries, sold out today, as a
        side, by their screens' operations: the hub, the burger's id and the courses' ids."""
        hub, _ = recoveries.business(every_app_on)
        tax = a_tax_key(hub)
        burger = run_in(hub, "inventory.product.create", name="Burger", sku="BUR", price=900,
                        tax_category_key=tax).id
        menu = run_in(hub, "combo.combo.create", name="Menu of the day", price=1350, tax_category_key=tax).id
        # The side is optional, so the till sells the menu while it is sold out.
        courses = {
            name: run_in(hub, "combo.group.create", combo_id=menu, name=name, min_choices=picks).id
            for name, picks in (("Mains", 1), ("Sides", 0))
        }
        run_in(hub, "combo.option.create", group_id=courses["Mains"], product_id=burger, price_delta=150)
        run_in(hub, "combo.option.create", group_id=courses["Sides"], product_id=burger, is_available=False)
        return hub, burger, courses

    def deleted(self, hub, product) -> None:
        """``product`` deleted in the business, and its choices taken away as the relay hands its deletion to Menus."""
        run_in(hub, "inventory.product.delete", id=product)
        run_in(hub, "combo.option.drop_product", id=product)
        assert offered(hub) == []

    def copied_then_withdrawn(self, recoveries, hub, courses):
        """A copy of ``hub``, and then its menu withdrawn by the business with its courses and choices: the copy and the
        menu's id."""
        with use_hub(hub):
            withdrawn = ChoiceGroup.objects.get(pk=courses["Mains"]).combo_id
        copy = recoveries.copy_of(hub)
        run_in(hub, "combo.combo.delete", id=withdrawn)
        return copy, withdrawn

    def nothing_comes_back_twice(self, recoveries, copy, hub, *asked: str) -> None:
        """Asked again from ``copy``, nothing is made twice: each thing counts nothing and the two choices stay."""
        again = recoveries.ask(copy, *asked)
        assert run() == 1
        before = [CATEGORIES, PRODUCTS, LINKS] if "inventory" in asked else []
        assert said(again) == ("done", [*before, MENUS, COURSES, CHOICES])
        assert len(offered(hub)) == 2

    def test_a_deleted_product_comes_back_offered_in_its_menus(self, recoveries, every_app_on):
        hub, burger, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        row = recoveries.ask(copy, "combo", "inventory")

        assert run() == 1

        # Inventory first, whatever the order asked: the product is back, the same, before its choices are offered.
        assert said(row) == (
            "done", [CATEGORIES, PRODUCTS | {"restored": 1}, LINKS, MENUS, COURSES, CHOICES | {"created": 2}]
        )
        # As the copy had them: its supplement, and the side still sold out.
        assert offered(hub) == [("Mains", burger, 150, True), ("Sides", burger, 0, False)]
        assert created_by(hub)[-2:] == [actor_of(row.pk)] * 2
        # And the till offers it again in the menu.
        [menu] = run_in(hub, "combo.combo.for_sale").rows
        assert [option.product_id for group in menu.groups for option in group.options] == [burger]
        # Asked again, nothing is offered twice.
        self.nothing_comes_back_twice(recoveries, copy, hub, "inventory", "combo")

    def test_a_product_gone_altogether_comes_back_as_a_new_one_offered_in_its_menus(self, recoveries, every_app_on):
        hub, burger, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        gone_altogether(hub, burger)
        row = recoveries.ask(copy, "combo", "inventory")

        assert run() == 1

        assert said(row) == (
            "done", [CATEGORIES, PRODUCTS | {"created": 1}, LINKS, MENUS, COURSES, CHOICES | {"created": 2}]
        )
        with use_hub(hub):
            [made] = Product.objects.filter(sku="BUR").values_list("pk", flat=True)
        assert made != burger
        # On the one made again, as the copy had them: its supplement, and the side still sold out.
        assert offered(hub) == [("Mains", made, 150, True), ("Sides", made, 0, False)]
        [menu] = run_in(hub, "combo.combo.for_sale").rows
        assert [option.product_id for group in menu.groups for option in group.options] == [made]
        # Asked again, nothing is offered twice: its choices are in their place on the one made again.
        self.nothing_comes_back_twice(recoveries, copy, hub, "inventory", "combo")

    def test_a_product_gone_the_business_made_again_by_hand_keeps_its_own_choices(self, recoveries, every_app_on):
        hub, burger, courses = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        gone_altogether(hub, burger)
        # Made again by hand with its SKU, the business offered it only as a side.
        made = run_in(hub, "inventory.product.create", name="Burger", sku="BUR", price=900,
                      tax_category_key=a_tax_key(hub)).id
        run_in(hub, "combo.option.create", group_id=courses["Sides"], product_id=made)
        row = recoveries.ask(copy, "inventory", "combo")

        assert run() == 1

        status, results = said(row)
        assert (status, results[1]["created"], results[-1]["created"], results[-1]["not_created"]) == ("done", 0, 0, 2)
        reasons = [reason["reason"].split(":")[0] for reason in results[-1]["reasons"]]
        assert reasons == ["invalid_field", "invalid_field"]
        assert offered(hub) == [("Sides", made, 0, True)]

    def test_a_choice_the_business_offered_again_stays_as_it_is(self, recoveries, every_app_on):
        hub, burger, courses = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        recoveries.ask(copy, "inventory")
        assert run() == 1
        # The product back without its choices, the business offered it again as a main by hand, at another supplement.
        run_in(hub, "combo.option.create", group_id=courses["Mains"], product_id=burger, price_delta=400)
        row = recoveries.ask(copy, "combo")

        assert run() == 1

        assert said(row) == ("done", [MENUS, COURSES, CHOICES | {"created": 1}])
        assert offered(hub) == [("Mains", burger, 400, True), ("Sides", burger, 0, False)]

    def test_a_choice_of_a_product_still_deleted_does_not_come_back_and_says_why(self, recoveries, every_app_on):
        hub, burger, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        # Without Products asked, the burger stays deleted: as the menu builder, it is offered in no course.
        row = recoveries.ask(copy, "combo")

        assert run() == 1

        status, [menus, courses, result] = said(row)
        assert (menus, courses) == (MENUS, COURSES)
        assert (status, result["created"], result["not_created"], result["refused"]) == ("done", 0, 2, "")
        assert [reason["reason"].split(":")[0] for reason in result["reasons"]] == ["invalid_field", "invalid_field"]
        assert offered(hub) == []

    def test_a_course_the_business_removed_since_comes_back_with_its_choices(self, recoveries, every_app_on):
        hub, burger, courses = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        run_in(hub, "combo.group.delete", id=courses["Sides"])
        row = recoveries.ask(copy, "inventory", "combo")

        assert run() == 1

        assert said(row) == (
            "done",
            [CATEGORIES, PRODUCTS | {"restored": 1}, LINKS, MENUS, COURSES | {"created": 1}, CHOICES | {"created": 2}],
        )
        # A new course, last in its menu as the menu builder adds one, optional as it was, with its choice sold out.
        assert offered(hub) == [("Mains", burger, 150, True), ("Sides", burger, 0, False)]
        with use_hub(hub):
            sides = ChoiceGroup.objects.get(name="Sides")
        assert (sides.id != courses["Sides"], sides.stands_for, sides.min_choices, sides.sort_order) == (
            True, courses["Sides"], 0, 1,
        )
        # Asked again, nothing comes back twice.
        self.nothing_comes_back_twice(recoveries, copy, hub, "combo")

    def test_a_menu_the_business_withdrew_comes_back_with_its_courses_and_choices(self, recoveries, every_app_on):
        hub, burger, courses = self.a_business(recoveries, every_app_on)
        copy, withdrawn = self.copied_then_withdrawn(recoveries, hub, courses)
        assert offered(hub) == []
        row = recoveries.ask(copy, "combo")

        assert run() == 1

        assert said(row) == (
            "done", [MENUS | {"created": 1}, COURSES | {"created": 2}, CHOICES | {"created": 2}]
        )
        # A new menu as its screen creates it, with its courses and their choices as the copy had them.
        with use_hub(hub):
            menu = Combo.objects.get()
        assert (menu.id != withdrawn, menu.stands_for, menu.name, menu.price) == (
            True, withdrawn, "Menu of the day", 1350,
        )
        assert offered(hub) == [("Mains", burger, 150, True), ("Sides", burger, 0, False)]
        assert created_by(hub)[-2:] == [actor_of(row.pk)] * 2
        # And the till offers it again.
        [for_sale] = run_in(hub, "combo.combo.for_sale").rows
        assert (for_sale.id, [option.product_id for group in for_sale.groups for option in group.options]) == (
            menu.id, [burger],
        )
        # Asked again, nothing comes back twice, though the business renamed it.
        run_in(hub, "combo.combo.update", id=menu.id, name="Lunch menu")
        self.nothing_comes_back_twice(recoveries, copy, hub, "combo")

    def test_a_menu_made_again_by_hand_keeps_its_own_and_what_hung_from_the_copys_says_why(
        self, recoveries, every_app_on
    ):
        hub, _, courses = self.a_business(recoveries, every_app_on)
        copy, _ = self.copied_then_withdrawn(recoveries, hub, courses)
        own = run_in(hub, "combo.combo.create", name="Menu of the day", price=1500, tax_category_key=a_tax_key(hub)).id
        run_in(hub, "combo.group.create", combo_id=own, name="Mains")
        row = recoveries.ask(copy, "combo")

        assert run() == 1

        status, [menus, back, choices] = said(row)
        assert (status, menus) == ("done", MENUS)
        # Not created, each by its id in the copy and why: its menu, and then its course, are not the business's.
        assert (back["created"], back["not_created"], choices["created"], choices["not_created"]) == (0, 2, 0, 2)
        assert [(reason["id"], reason["reason"].split(":")[0]) for reason in back["reasons"]] == [
            (str(courses["Mains"]), "not_found"), (str(courses["Sides"]), "not_found"),
        ]
        assert [reason["reason"].split(":")[0] for reason in choices["reasons"]] == ["not_found", "not_found"]
        # The business's own menu as it made it.
        with use_hub(hub):
            assert list(Combo.objects.values_list("pk", "price")) == [(own, 1500)]
            assert list(ChoiceGroup.objects.values_list("name", flat=True)) == ["Mains"]
        assert offered(hub) == []

    def test_a_course_made_again_by_hand_keeps_its_own_choices(self, recoveries, every_app_on):
        hub, burger, courses = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        with use_hub(hub):
            side = ChoiceOption.objects.get(group_id=courses["Sides"]).id
            menu = ChoiceGroup.objects.get(pk=courses["Sides"]).combo_id
        run_in(hub, "combo.group.delete", id=courses["Sides"])
        run_in(hub, "combo.group.create", combo_id=menu, name="sides", min_choices=0)
        row = recoveries.ask(copy, "combo")

        assert run() == 1

        status, [menus, back, choices] = said(row)
        assert (status, menus, back) == ("done", MENUS, COURSES)
        assert (choices["created"], choices["not_created"]) == (0, 1)
        assert [(reason["id"], reason["reason"].split(":")[0]) for reason in choices["reasons"]] == [
            (str(side), "not_found")
        ]
        assert offered(hub) == [("Mains", burger, 150, True)]
