"""Models of the vouchers sold, their adjustments and sessions: the rules the database itself keeps.

The operations check every rule first, with their own messages; these constraints are the last line
(the Django admin and two writes at once do not go through the operations' checks).
"""

import uuid

from apps.service.models.grants import Grant, GrantAdjustment, Redemption
from apps.service.tests.conftest import HUB_DB, make_customer, make_grant, make_package, make_service, refused

pytestmark = HUB_DB


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
