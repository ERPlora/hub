"""What Menus gives back from a separate copy of the business (BASE-F114, COMBO-F15).

The copy is no business, so it has no alias and the ORM never reaches it: the platform reads it through a direct,
read-only connection, and Menus answers with its own SQL over its models' names. Its choices: each one of a live
product that the business no longer offers in that course is offered again by ``combo.option.create``, the menu
builder's own, unless the business still holds it or offered that product in that course again. Menus goes after
Inventory (its ``requires``), so a deleted product is back, the same, before its choices are offered.

Then, end to end on real databases (``hubs.CopiedHubs``): the business's own and its copy, a clone of it.
"""

import uuid

import pytest
from django.apps import apps
from django.db import connection
from live.models import OutboxEvent

from apps.combo import queries
from apps.combo.models import ChoiceOption
from apps.inventory.models import Product
from apps.inventory.tests.test_recovery import CATEGORIES, LINKS, PRODUCTS, a_tax_key
from base.recovery import actor_of
from base.tenancy.context import use_hub
from base.tenancy.tests.test_recovery import Recoveries, fresh, run, run_in

from .conftest import make_combo, make_group, make_option, make_product


def direct():
    """The raw connection of the tests' database, as the platform's direct one reads the copy."""
    connection.ensure_connection()
    return connection.connection


@pytest.mark.django_db
def test_the_copy_gives_each_choice_of_a_live_product_with_what_its_create_takes():
    lentils, soup, steak = make_product("Lentils"), make_product("Soup"), make_product("Steak")
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

    assert read == [
        {"id": on_lentils.id, "group_id": starters.id, "product_id": lentils.id, "price_delta": 0, "is_available": True},
        {"id": on_soup.id, "group_id": starters.id, "product_id": soup.id, "price_delta": -50, "is_available": False},
        {"id": on_steak.id, "group_id": mains.id, "product_id": steak.id, "price_delta": 300, "is_available": True},
    ]


@pytest.mark.django_db
def test_a_copy_without_the_apps_table_gives_nothing():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE combo_choiceoption CASCADE")

    assert queries.options_in_copy(direct()) == []


def a_choice_of_the_copy(group, product, **fields) -> dict:
    return {"id": uuid.uuid7(), "group_id": group.id, "product_id": product.id, "price_delta": 0,
            "is_available": True} | fields


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


def test_with_nothing_read_nothing_is_lacking():
    assert queries.options_not_in_business([]) == []


def test_the_app_declares_its_choices_offered_again_by_the_menu_builders_create():
    [choices] = apps.get_app_config("combo").recoverable_from_copy()

    assert (choices.read, choices.missing, choices.create, choices.deleted, choices.restore) == (
        queries.options_in_copy,
        queries.options_not_in_business,
        "combo.option.create",
        None,
        "",
    )
    assert (str(choices.label), choices.reads_since) == ("Menu choices of products", "0001_initial")


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

    def test_a_deleted_product_comes_back_offered_in_its_menus(self, recoveries, every_app_on):
        hub, burger, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        row = recoveries.ask(copy, "combo", "inventory")

        assert run() == 1

        # Inventory first, whatever the order asked: the product is back, the same, before its choices are offered.
        assert said(row) == ("done", [CATEGORIES, PRODUCTS | {"restored": 1}, LINKS, CHOICES | {"created": 2}])
        # As the copy had them: its supplement, and the side still sold out.
        assert offered(hub) == [("Mains", burger, 150, True), ("Sides", burger, 0, False)]
        assert created_by(hub)[-2:] == [actor_of(row.pk)] * 2
        # And the till offers it again in the menu.
        [menu] = run_in(hub, "combo.combo.for_sale").rows
        assert [option.product_id for group in menu.groups for option in group.options] == [burger]
        # Asked again, nothing is offered twice.
        again = recoveries.ask(copy, "inventory", "combo")
        assert run() == 1
        assert said(again) == ("done", [CATEGORIES, PRODUCTS, LINKS, CHOICES])
        assert len(offered(hub)) == 2

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

        assert said(row) == ("done", [CHOICES | {"created": 1}])
        assert offered(hub) == [("Mains", burger, 400, True), ("Sides", burger, 0, False)]

    def test_a_choice_of_a_product_still_deleted_does_not_come_back_and_says_why(self, recoveries, every_app_on):
        hub, burger, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        # Without Products asked, the burger stays deleted: as the menu builder, it is offered in no course.
        row = recoveries.ask(copy, "combo")

        assert run() == 1

        status, [result] = said(row)
        assert (status, result["created"], result["not_created"], result["refused"]) == ("done", 0, 2, "")
        assert [reason["reason"].split(":")[0] for reason in result["reasons"]] == ["invalid_field", "invalid_field"]
        assert offered(hub) == []

    def test_a_choice_whose_course_the_business_removed_since_does_not_come_back_and_says_which(
        self, recoveries, every_app_on
    ):
        hub, burger, courses = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        with use_hub(hub):
            side = ChoiceOption.objects.get(group_id=courses["Sides"]).id
        self.deleted(hub, burger)
        run_in(hub, "combo.group.delete", id=courses["Sides"])
        row = recoveries.ask(copy, "inventory", "combo")

        assert run() == 1

        status, results = said(row)
        assert (status, results[-1]["created"], results[-1]["not_created"]) == ("done", 1, 1)
        assert [(reason["id"], reason["reason"].split(":")[0]) for reason in results[-1]["reasons"]] == [
            (str(side), "not_found")
        ]
        assert offered(hub) == [("Mains", burger, 150, True)]
