"""The modifier app's tables: UUIDv7 keys, the group's rules and every uniqueness held by the database too.

The admin and any future bug go around the operations: what must never be stored (a maximum below the
minimum, two groups with the same name, a link to nothing or to two things, the same link twice) is
refused by Postgres itself.
"""

import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.modifier.models import (
    MAX_CHOICES,
    MAX_DELTA,
    ModifierGroup,
    ModifierLink,
    ModifierOption,
)
from apps.tax.models import TaxCategory

from .conftest import FOOD, make_category, make_product

pytestmark = pytest.mark.django_db


def refused(make) -> bool:
    try:
        with transaction.atomic():
            make()
    except IntegrityError:
        return True
    return False


def test_a_group_has_a_uuid7_key_and_the_old_defaults():
    group = ModifierGroup.objects.create(name="Sauces")
    assert isinstance(group.pk, uuid.UUID) and group.pk.version == 7
    assert (
        group.kitchen_name,
        group.min_choices,
        group.max_choices,
        group.allow_repeat,
        group.sort_order,
    ) == ("", 0, 0, False, 0)
    assert str(group) == "Sauces"


def test_groups_are_ordered_by_order_then_name():
    ModifierGroup.objects.create(name="B", sort_order=1)
    ModifierGroup.objects.create(name="A", sort_order=2)
    ModifierGroup.objects.create(name="C", sort_order=1)
    assert [g.name for g in ModifierGroup.objects.all()] == ["B", "C", "A"]


def test_a_group_name_is_unique_whatever_the_case():
    ModifierGroup.objects.create(name="Sauces")
    assert refused(lambda: ModifierGroup.objects.create(name="sauces"))


def test_the_maximum_is_zero_or_not_below_the_minimum():
    assert refused(
        lambda: ModifierGroup.objects.create(name="Bad", min_choices=2, max_choices=1)
    )
    ModifierGroup.objects.create(name="No ceiling", min_choices=2, max_choices=0)
    ModifierGroup.objects.create(name="Exactly", min_choices=2, max_choices=2)


def test_the_choices_stay_within_fifty():
    assert MAX_CHOICES == 50
    assert refused(
        lambda: ModifierGroup.objects.create(name="Too many", min_choices=51)
    )
    assert refused(
        lambda: ModifierGroup.objects.create(name="Too many max", max_choices=51)
    )


def test_an_option_belongs_to_its_group_with_its_supplement_and_inherits_its_tax_by_default():
    group = ModifierGroup.objects.create(name="Extras")
    option = ModifierOption.objects.create(group=group, name="Cheese", price_delta=100)
    assert option.pk.version == 7
    assert (
        option.kitchen_name,
        option.tax_category,
        option.is_default,
        option.sort_order,
    ) == ("", None, False, 0)
    assert str(option) == "Cheese"
    # A supplement may be a discount.
    ModifierOption.objects.create(group=group, name="No bread", price_delta=-50)


def test_an_option_name_is_unique_within_its_group_only():
    extras = ModifierGroup.objects.create(name="Extras")
    sauces = ModifierGroup.objects.create(name="Sauces")
    ModifierOption.objects.create(group=extras, name="Cheese")
    ModifierOption.objects.create(group=sauces, name="Cheese")
    assert refused(lambda: ModifierOption.objects.create(group=extras, name="CHEESE"))


def test_a_supplement_stays_within_its_bounds():
    group = ModifierGroup.objects.create(name="Extras")
    assert refused(
        lambda: ModifierOption.objects.create(
            group=group, name="Gold", price_delta=MAX_DELTA + 1
        )
    )
    assert refused(
        lambda: ModifierOption.objects.create(
            group=group, name="Free money", price_delta=-MAX_DELTA - 1
        )
    )


def test_an_option_points_at_a_real_tax_category_that_taxes_never_deletes():
    group = ModifierGroup.objects.create(name="Drinks")
    soda = ModifierOption.objects.create(
        group=group,
        name="Soda",
        price_delta=250,
        tax_category=TaxCategory.objects.get(key=FOOD),
    )
    assert refused(lambda: TaxCategory.objects.filter(pk=soda.tax_category_id).delete())


def test_an_option_with_its_own_tax_category_is_worth_more_than_zero_also_in_the_database():
    # Its own line cannot be worth zero or less (Sales bills it apart): the admin cannot store it either.
    group = ModifierGroup.objects.create(name="Drinks")
    generic = TaxCategory.objects.get(key="product.generic")
    for delta in (0, -100):
        assert refused(lambda: ModifierOption.objects.create(group=group, name=f"Soda {delta}", price_delta=delta, tax_category=generic))
    ModifierOption.objects.create(group=group, name="Soda", price_delta=1, tax_category=generic)
    ModifierOption.objects.create(group=group, name="Water", price_delta=0)


def test_options_are_ordered_by_order_then_name():
    group = ModifierGroup.objects.create(name="Extras")
    ModifierOption.objects.create(group=group, name="B", sort_order=1)
    ModifierOption.objects.create(group=group, name="A", sort_order=2)
    ModifierOption.objects.create(group=group, name="C", sort_order=1)
    assert [o.name for o in group.options.all()] == ["B", "C", "A"]


def test_a_link_points_at_exactly_one_product_or_category():
    group = ModifierGroup.objects.create(name="Sauces")
    burger = make_product()
    mains = make_category()
    by_product = ModifierLink.objects.create(group=group, product_id=burger.id)
    by_category = ModifierLink.objects.create(group=group, category_id=mains.id)
    assert (by_product.target_kind, by_category.target_kind) == ("product", "category")
    assert refused(lambda: ModifierLink.objects.create(group=group))
    assert refused(
        lambda: ModifierLink.objects.create(
            group=group, product_id=burger.id, category_id=mains.id
        )
    )


def test_the_same_link_cannot_exist_twice():
    group = ModifierGroup.objects.create(name="Sauces")
    burger = make_product()
    mains = make_category()
    ModifierLink.objects.create(group=group, product_id=burger.id)
    ModifierLink.objects.create(group=group, category_id=mains.id)
    assert refused(
        lambda: ModifierLink.objects.create(group=group, product_id=burger.id)
    )
    assert refused(
        lambda: ModifierLink.objects.create(group=group, category_id=mains.id)
    )
    # Another group may hang from the same product: a group is shared, a product carries several.
    ModifierLink.objects.create(
        group=ModifierGroup.objects.create(name="Extras"), product_id=burger.id
    )


def test_deleting_a_group_takes_its_options_and_links_with_it():
    group = ModifierGroup.objects.create(name="Sauces")
    ModifierOption.objects.create(group=group, name="Ketchup")
    ModifierLink.objects.create(group=group, product_id=make_product().id)
    group.delete()
    assert (ModifierOption.objects.count(), ModifierLink.objects.count()) == (0, 0)
