"""The commission sheet (STAFF-F21): who can earn one, at what rate, and who reads it."""

from decimal import Decimal

import pytest
from live.errors import PermissionDenied

from apps.staff.models import Member
from apps.staff.queries.commissions import commission_summary
from apps.staff.schemas.commissions import CommissionSummaryIn

from .conftest import HUB_DB, TERMINATED, ctx_for, make_member, make_role, run

pytestmark = HUB_DB


def test_the_commission_sheet_lists_who_can_earn_one_with_both_ids(make_user):
    account = make_user("ana")
    ana = make_member("Ana", user=account.person, commission_rate=Decimal("15"), role=make_role("Stylist"))
    bea = make_member("Bea", status=Member.Status.ON_LEAVE)  # a zero rate is listed too
    make_member("Carla", status=Member.Status.INACTIVE, commission_rate=Decimal("10"))
    make_member("Dora", status=TERMINATED, commission_rate=Decimal("10"))

    page = run("staff.commission.summary", CommissionSummaryIn(), "hub_manager")

    assert [row.model_dump() for row in page.rows] == [
        {
            "id": ana.id,
            "user_id": account.person.id,
            "full_name": "Ana López",
            "role_id": ana.role_id,
            "role_name": "Stylist",
            "commission_rate": Decimal("15.00"),
        },
        {
            "id": bea.id,
            "user_id": None,
            "full_name": "Bea López",
            "role_id": None,
            "role_name": None,
            "commission_rate": Decimal("0.00"),
        },
    ]
    assert [row.id for row in run("staff.commission.summary", CommissionSummaryIn(search="bea")).rows] == [bea.id]


def test_an_employee_does_not_see_the_commission_sheet():
    with pytest.raises(PermissionDenied):
        commission_summary(ctx_for("hub_employee"), CommissionSummaryIn())
