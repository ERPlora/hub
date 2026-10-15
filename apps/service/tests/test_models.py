"""Models of the service app: UUIDv7 keys, money in cents and the rules the database itself keeps.

The operations check every rule first, with their own messages; these constraints are the last line
(the Django admin and two writes at once do not go through the operations' checks).
"""

import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.service.models import (
    parent_problem,
    Assignment,
    Category,
    Grant,
    GrantAdjustment,
    Package,
    PackageItem,
    Redemption,
    Service,
    ServiceSettings,
)
from apps.service.tests.conftest import (
    make_category,
    make_customer,
    make_grant,
    make_member,
    make_package,
    make_service,
    make_tax,
)

pytestmark = pytest.mark.django_db


def refused(**create) -> bool:
    """Whether creating ``model(**fields)`` breaks a constraint (inside its own savepoint)."""
    model, fields = create.pop("model"), create
    try:
        with transaction.atomic():
            model.objects.create(**fields)
    except IntegrityError:
        return True
    return False


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
    with pytest.raises(IntegrityError), transaction.atomic():
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


def test_a_live_package_name_is_unique_and_a_deleted_one_frees_it():
    old = make_package("Bono 5")
    assert refused(model=Package, name="bono 5")
    old.is_deleted = True
    old.save()
    assert not refused(model=Package, name="Bono 5")


def test_a_package_discount_validity_and_uses_stay_in_their_range():
    assert refused(model=Package, name="Too much", discount_percent_bp=10001)
    assert refused(model=Package, name="No days", validity_days=0)
    assert refused(model=Package, name="No uses", max_uses=0)
    assert refused(model=Package, name="Odd", discount_type="gift")


def test_a_package_line_is_one_service_once_with_at_least_one_session():
    cut = make_service("Cut")
    package = make_package("Bono", [cut])
    assert refused(model=PackageItem, package=package, service=cut)
    assert refused(
        model=PackageItem, package=make_package("Other"), service=cut, sessions=0
    )


def test_a_voucher_sold_freezes_its_terms_and_keeps_its_money_in_cents():
    package = make_package("Bono", [make_service()], max_uses=5, validity_days=90)
    grant = make_grant(package, make_customer(), amount=9000)
    assert (
        grant.max_uses,
        grant.validity_days,
        grant.amount,
        grant.source,
        grant.voided_at,
    ) == (5, 90, 9000, "manual", None)
    assert refused(
        model=Grant, package=package, customer=make_customer("Other"), source="gift"
    )


def test_an_adjustment_moves_something_within_its_bounds():
    grant = make_grant(make_package("Bono", max_uses=5), make_customer())
    assert refused(
        model=GrantAdjustment, grant=grant, uses_delta=0, days_delta=0, reason="nothing"
    )
    assert refused(
        model=GrantAdjustment, grant=grant, uses_delta=101, reason="too many"
    )
    assert refused(
        model=GrantAdjustment, grant=grant, uses_delta=-101, reason="too many"
    )
    assert refused(
        model=GrantAdjustment, grant=grant, days_delta=367, reason="too long"
    )
    assert not refused(
        model=GrantAdjustment, grant=grant, uses_delta=-1, days_delta=30, reason="ok"
    )


def test_a_session_spent_points_at_its_voucher_and_optionally_at_the_service_sale_and_appointment():
    cut = make_service()
    grant = make_grant(make_package("Bono", [cut]), make_customer())
    session = Redemption.objects.create(grant=grant, service=cut, sale_id=uuid.uuid7())
    assert session.redeemed_at is not None and session.appointment_id is None


def test_a_session_spent_outside_the_till_is_born_delivered_without_a_line_nor_a_deadline():
    cut = make_service()
    grant = make_grant(make_package("Bono", [cut]), make_customer())
    session = Redemption.objects.create(grant=grant, service=cut)
    assert session.status == Redemption.Status.CONSUMED == "consumed"
    assert session.order_line_id is None and session.hold_until is None
    assert session.settled_at is None and session.ended_at is None
    assert session.ended_by == "" and session.return_reference is None
    assert session.return_reason == ""


def test_a_session_has_one_of_the_five_states():
    cut = make_service()
    grant = make_grant(make_package("Bono", [cut]), make_customer())
    assert [choice for choice, _ in Redemption.Status.choices] == [
        "held",
        "consumed",
        "released",
        "expired",
        "returned",
    ]
    assert refused(model=Redemption, grant=grant, status="spent")


def test_a_line_of_the_check_has_one_live_session_at_most():
    cut = make_service()
    grant = make_grant(make_package("Bono", [cut], max_uses=5), make_customer())
    line = uuid.uuid7()
    Redemption.objects.create(
        grant=grant, service=cut, status="held", order_line_id=line
    )
    assert refused(
        model=Redemption, grant=grant, service=cut, status="held", order_line_id=line
    )
    assert refused(
        model=Redemption,
        grant=grant,
        service=cut,
        status="consumed",
        order_line_id=line,
    )
    # A session released, expired or given back frees the line for another one.
    for ended in ("released", "expired", "returned"):
        assert not refused(
            model=Redemption, grant=grant, service=cut, status=ended, order_line_id=line
        )
    # Sessions spent outside the till carry no line: any number of them.
    assert not refused(model=Redemption, grant=grant, service=cut)
    assert not refused(model=Redemption, grant=grant, service=cut)


def test_the_settings_are_a_single_row_with_the_factory_values():
    first = ServiceSettings.objects.create()
    assert (
        first.default_duration,
        first.default_buffer_time,
        first.default_tax_category,
    ) == (60, 0, None)
    assert (first.show_prices, first.show_duration, first.allow_online_booking) == (
        True,
        True,
        True,
    )
    assert refused(model=ServiceSettings)


def test_a_settings_duration_of_zero_is_refused():
    assert refused(model=ServiceSettings, default_duration=0)


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
