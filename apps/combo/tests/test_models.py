"""The combo app's tables: what the database itself refuses (WORKBOOK «Para quien lo mantiene»).

A menu's price is never negative and a menu eaten in always has its own tax category; a course's
ceiling is never below its floor (0 = no ceiling) and its name is unique in its menu; a product is
offered once per course. Deleting a menu takes its courses and their choices with it.
"""

import uuid

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.combo.models import ChoiceGroup, ChoiceOption, Combo

from .conftest import (
    FOOD,
    make_combo,
    make_group,
    make_option,
    make_product,
    tax_category,
)

pytestmark = pytest.mark.django_db


def refused(make) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        make()


def test_a_menu_has_a_uuid7_key_and_the_old_defaults():
    combo = Combo.objects.create(
        name="Menu of the day", price=1350, tax_category=tax_category(FOOD)
    )
    assert isinstance(combo.pk, uuid.UUID) and combo.pk.version == 7
    assert combo.supply_kind == "service"
    assert combo.is_active is True
    assert combo.sort_order == 0
    assert combo.kitchen_name == ""
    assert str(combo) == "Menu of the day"


def test_the_two_ways_a_menu_is_sold():
    assert [value for value, _ in Combo.SupplyKind.choices] == ["service", "goods"]


def test_a_negative_price_is_refused_by_the_database():
    refused(lambda: Combo.objects.create(name="x", price=-1, supply_kind="goods"))


def test_a_menu_eaten_in_without_a_tax_category_is_refused():
    refused(lambda: Combo.objects.create(name="x", price=100, supply_kind="service"))
    # Sold to take away it needs none: each component brings its own.
    assert (
        Combo.objects.create(name="Pack", price=600, supply_kind="goods").tax_category
        is None
    )


def test_a_third_way_of_selling_is_refused():
    refused(
        lambda: Combo.objects.create(
            name="x", price=100, supply_kind="mixed", tax_category=tax_category()
        )
    )


def test_a_tax_category_in_use_cannot_be_deleted():
    combo = make_combo()
    with pytest.raises(ProtectedError):
        combo.tax_category.delete()


def test_a_course_ceiling_is_never_below_its_floor_and_zero_means_no_ceiling():
    combo = make_combo()
    refused(
        lambda: ChoiceGroup.objects.create(
            combo=combo, name="Mains", min_choices=2, max_choices=1
        )
    )
    assert (
        ChoiceGroup.objects.create(
            combo=combo, name="Drinks", min_choices=2, max_choices=0
        ).max_choices
        == 0
    )
    assert (
        ChoiceGroup.objects.create(
            combo=combo, name="Desserts", min_choices=0, max_choices=3
        ).min_choices
        == 0
    )


def test_a_course_asks_for_fifty_at_most():
    combo = make_combo()
    refused(
        lambda: ChoiceGroup.objects.create(
            combo=combo, name="A", min_choices=51, max_choices=0
        )
    )
    refused(
        lambda: ChoiceGroup.objects.create(
            combo=combo, name="B", min_choices=1, max_choices=51
        )
    )


def test_a_course_defaults_to_one_compulsory_pick_without_repeats():
    group = make_group(make_combo())
    assert (group.min_choices, group.max_choices, group.allow_repeat) == (1, 1, False)


def test_a_course_name_is_unique_in_its_menu_whatever_the_case():
    combo = make_combo()
    make_group(combo, "Starters")
    refused(lambda: ChoiceGroup.objects.create(combo=combo, name="STARTERS"))
    # Another menu may have its own Starters.
    assert make_group(make_combo("Kids menu"), "Starters").name == "Starters"


def test_a_product_is_offered_once_per_course():
    group = make_group(make_combo())
    lentils = make_product("Lentils")
    make_option(group, lentils)
    refused(lambda: ChoiceOption.objects.create(group=group, product=lentils))
    # The same product may be a choice of another course.
    assert make_option(make_group(group.combo, "Mains"), lentils).product == lentils


def test_a_choice_defaults_to_no_supplement_and_available():
    option = make_option(make_group(make_combo()), make_product())
    assert option.price_delta == 0
    assert option.is_available is True


def test_a_supplement_may_be_negative():
    option = make_option(make_group(make_combo()), make_product(), price_delta=-50)
    option.refresh_from_db()
    assert option.price_delta == -50


def test_deleting_a_menu_takes_its_courses_and_choices():
    combo = make_combo()
    group = make_group(combo)
    make_option(group, make_product())
    combo.delete()
    assert ChoiceGroup.objects.count() == 0
    assert ChoiceOption.objects.count() == 0


def test_courses_and_choices_come_in_their_order():
    combo = make_combo()
    second = make_group(combo, "Mains", sort_order=2)
    first = make_group(combo, "Starters", sort_order=1)
    assert list(combo.groups.all()) == [first, second]
    b = make_option(first, make_product("B"), sort_order=2)
    a = make_option(first, make_product("A"), sort_order=1)
    assert list(first.options.all()) == [a, b]
