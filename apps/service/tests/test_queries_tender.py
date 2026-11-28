"""The vouchers that can pay a service at the till: which ones, the one spent first and why, and how they page."""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.errors import PermissionDenied

from apps.service.schemas.tender import TenderOptionsIn

from .conftest import (
    HUB_DB, make_customer, make_grant, make_package, make_redemption, make_service, make_tax, run,
)

pytestmark = HUB_DB


def _tender(customer, service, role="hub_admin", **more):
    return run(
        "service.grant.tender_options",
        TenderOptionsIn(customer_id=customer.id, service_id=service.id, **more),
        role=role,
    )


def test_the_tender_options_are_the_customers_vouchers_that_can_pay_the_service(tax):
    cut = make_service("Cut", tax=tax)
    colour = make_service("Colour", tax=make_tax("test.colour", "Colour"))
    lucia, marta = make_customer("Lucía"), make_customer("Marta")
    good = make_grant(make_package("Cuts", [cut], max_uses=5), lucia, amount=9000)
    make_grant(make_package("Colours", [colour], max_uses=5), lucia)  # does not cover it
    make_grant(make_package("Marta's", [cut], max_uses=5), marta)  # someone else's
    voided = make_grant(make_package("Voided", [cut], max_uses=5), lucia)
    voided.voided_at = timezone.now()
    voided.save()
    make_grant(make_package("Old", [cut], max_uses=5, validity_days=30), lucia, days_ago=31)
    spent = make_grant(make_package("Spent", [cut], max_uses=1), lucia)
    make_redemption(spent, cut)
    page = _tender(lucia, cut, role="hub_employee")
    assert [row.grant_id for row in page.rows] == [good.id]
    [row] = page.rows
    assert (row.package_name, row.max_uses, row.used, row.remaining_before, row.remaining_after) == (
        "Cuts",
        5,
        0,
        5,
        4,
    )
    assert (row.is_unlimited, row.is_default, row.default_reason, row.candidate_count) == (
        False,
        True,
        "only_option",
        1,
    )
    assert page.total == 1


def test_a_deleted_package_still_pays_with_what_was_sold(tax):
    cut = make_service("Cut", tax=tax)
    package = make_package("Retired", [cut], max_uses=3)
    lucia = make_customer("Lucía")
    grant = make_grant(package, lucia)
    package.is_deleted = True
    package.save()
    assert [row.grant_id for row in _tender(lucia, cut).rows] == [grant.id]


def test_the_voucher_spent_first_and_why(tax):
    cut = make_service("Cut", tax=tax)
    lucia = make_customer("Lucía")
    unlimited = make_grant(make_package("Unlimited", [cut]), lucia, days_ago=50)
    late = make_grant(make_package("Late", [cut], max_uses=5, validity_days=90), lucia, days_ago=1)
    soon = make_grant(make_package("Soon", [cut], max_uses=5, validity_days=90), lucia, days_ago=40)
    rows = _tender(lucia, cut).rows
    assert [row.grant_id for row in rows] == [soon.id, late.id, unlimited.id]
    assert [(row.is_default, row.default_reason) for row in rows] == [
        (True, "expires_first"),
        (False, ""),
        (False, ""),
    ]
    assert {row.candidate_count for row in rows} == {3}
    assert rows[2].remaining_before is None and rows[2].remaining_after is None
    assert rows[2].is_unlimited is True


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ("finite_vs_unlimited", "finite_before_unlimited"),
        ("started_vs_new", "already_started"),
        ("fewer_left", "fewest_sessions_left"),
        ("older", "oldest_voucher"),
        ("twins", "stable_order"),
    ],
)
def test_each_tie_break_says_its_reason(tax, setup, reason):
    cut = make_service("Cut", tax=tax)
    lucia = make_customer("Lucía")
    now = timezone.now()

    def grant(name, *, max_uses=5, at=now):
        made = make_grant(make_package(name, [cut], max_uses=max_uses), lucia)
        made.granted_at = at
        made.save()
        return made

    if setup == "finite_vs_unlimited":
        first, _ = grant("Finite"), grant("Unlimited", max_uses=None)
    elif setup == "started_vs_new":
        first, other = grant("Started"), grant("New")
        make_redemption(first, cut)
        other.max_uses = 4  # the same sessions left, so only «started» tells them apart
        other.save()
    elif setup == "fewer_left":
        first, _ = grant("Fewer", max_uses=2), grant("More", max_uses=5)
    elif setup == "older":
        first, _ = grant("Older", at=now - dt.timedelta(days=3)), grant("Newer")
    else:
        a, b = grant("Twin A"), grant("Twin B")
        first = min(a, b, key=lambda row: row.id)
    rows = _tender(lucia, cut).rows
    assert rows[0].grant_id == first.id
    assert rows[0].default_reason == reason


def test_a_live_hold_is_counted_in_the_options_and_a_full_voucher_drops_out(tax):
    cut = make_service("Cut", tax=tax)
    lucia = make_customer("Lucía")
    grant = make_grant(make_package("Two", [cut], max_uses=2), lucia)
    make_redemption(
        grant, cut, status="held", hold_until=timezone.now() + dt.timedelta(hours=1), order_line_id=uuid.uuid7()
    )
    [row] = _tender(lucia, cut).rows
    assert (row.used, row.remaining_before, row.remaining_after) == (1, 1, 0)
    make_redemption(grant, cut)
    assert _tender(lucia, cut).rows == []


def test_the_options_of_a_card_include_the_vouchers_of_a_card_merged_into_it(tax):
    cut = make_service("Cut", tax=tax)
    lucia, duplicate = make_customer("Lucía Pérez"), make_customer("Lucia P.")
    duplicate.deleted_at, duplicate.merged_into = timezone.now(), lucia
    duplicate.save()
    absorbed = make_grant(make_package("Bono", [cut], max_uses=3), duplicate)
    assert [row.grant_id for row in _tender(lucia, cut).rows] == [absorbed.id]


def test_the_options_name_the_customer_and_the_service_as_a_person_says_them(tax):
    cut = make_service("Haircut", tax=tax)
    lucia = make_customer("Lucía Pérez")
    grant = make_grant(make_package("Bono", [cut], max_uses=3), lucia)
    page = run(
        "service.grant.tender_options",
        TenderOptionsIn(customer="Lucía Pérez", service="Haircut"),
    )
    assert [row.grant_id for row in page.rows] == [grant.id]


def test_the_options_page_and_need_the_permission_to_spend_sessions(tax):
    cut = make_service("Cut", tax=tax)
    lucia = make_customer("Lucía")
    for index in range(3):
        make_grant(make_package(f"Bono {index}", [cut], max_uses=3), lucia)
    page = _tender(lucia, cut, limit=2, offset=0)
    assert (len(page.rows), page.total) == (2, 3)
    assert {row.candidate_count for row in page.rows} == {3}
    with pytest.raises(PermissionDenied):
        run(
            "service.grant.tender_options",
            TenderOptionsIn(customer_id=lucia.id, service_id=cut.id),
            permissions={"service.view_package"},
        )
