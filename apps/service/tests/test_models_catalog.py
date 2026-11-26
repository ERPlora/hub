"""Models of the service catalog: UUIDv7 keys, money in cents and the rules the database itself keeps.

The operations check every rule first, with their own messages; these constraints are the last line
(the Django admin and two writes at once do not go through the operations' checks).
"""

import uuid

import pytest
from django.db import IntegrityError
from live.operations import atomic

from apps.service.models.catalog import (
    parent_problem,
    Assignment,
    Category,
    Service,
)
from apps.service.tests.conftest import HUB_DB, make_category, make_member, make_service, make_tax, refused

pytestmark = HUB_DB


def test_every_key_is_a_uuid7():
    service = make_service()
    assert isinstance(service.id, uuid.UUID) and service.id.version == 7


def test_a_service_is_born_offered_for_an_hour_at_a_fixed_price():
    service = make_service("Colour", price=4500)
    assert (
        service.pricing_type,
        service.price,
        service.duration_minutes,
        service.max_capacity,
    ) == (
        "fixed",
        4500,
        60,
        1,
    )
    assert (
        service.is_active,
        service.is_bookable,
        service.allow_online_booking,
        service.archived_at,
    ) == (
        True,
        True,
        True,
        None,
    )
    assert str(service) == "Colour"


def test_a_service_takes_time_serves_someone_and_its_minimum_price_is_not_above_its_maximum():
    assert refused(model=Service, name="Zero", duration_minutes=0)
    assert refused(model=Service, name="Nobody", max_capacity=0)
    assert refused(
        model=Service,
        name="Upside down",
        pricing_type="from",
        min_price=5000,
        max_price=4000,
    )
    assert not refused(
        model=Service, name="From", pricing_type="from", min_price=4000, max_price=5000
    )


def test_a_pricing_type_outside_the_five_is_refused_by_the_database():
    assert refused(model=Service, name="Odd", pricing_type="barter")


def test_a_live_category_name_is_unique_ignoring_case_and_a_deleted_one_frees_it():
    hair = make_category("Hair")
    assert refused(model=Category, name="HAIR")
    hair.is_deleted = True
    hair.save()
    assert not refused(model=Category, name="hair")


def test_a_category_is_not_its_own_parent():
    hair = make_category("Hair")
    hair.parent = hair
    with pytest.raises(IntegrityError), atomic():
        hair.save()


def test_one_professional_once_per_service_and_one_primary_service_per_professional():
    tax = make_tax()
    cut, colour = make_service("Cut", tax=tax), make_service("Colour", tax=tax)
    ana = make_member()
    Assignment.objects.create(service=cut, member=ana, is_primary=True)
    assert refused(model=Assignment, service=cut, member=ana)
    assert refused(model=Assignment, service=colour, member=ana, is_primary=True)
    assert not refused(model=Assignment, service=colour, member=ana, is_primary=False)
    assert refused(
        model=Assignment, service=make_service("Beard"), member=ana, custom_duration=0
    )


def test_a_parent_that_closes_a_loop_or_meets_one_is_refused_without_walking_for_ever():
    a, b, c, d = (uuid.uuid7() for _ in range(4))
    tree = {a: None, b: a, c: b}
    assert parent_problem(a, c, tree) == "cycle"  # a under its own grandchild
    assert parent_problem(a, a, tree) == "cycle"  # a under itself
    assert parent_problem(c, a, tree) is None
    looped = {a: b, b: a, c: None}
    assert (
        parent_problem(c, a, looped) == "loop"
    )  # the data already loops: refused, not walked for ever
    assert parent_problem(d, None, looped) is None
