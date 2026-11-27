"""The read operations of the staff app as a whole: what each one declares, and how the ties of every list go. What each
one reads is tested beside its module, in ``test_queries_<module>.py``."""

import pytest
from live.operations import get

from apps.staff.schemas.accounts import AccountListIn, AccountPage
from apps.staff.schemas.availability import AvailabilityIn, AvailabilityOut
from apps.staff.schemas.commissions import CommissionPage, CommissionSummaryIn
from apps.staff.schemas.fields import ByIdIn, MemberRefIn
from apps.staff.schemas.members import (
    CompensationListIn,
    CompensationPage,
    CurrentMemberIn,
    CurrentMemberOut,
    MemberDetailOut,
    MemberListIn,
    MemberPage,
    MemberStatsIn,
    MemberStatsOut,
    MineIn,
    MineOut,
)
from apps.staff.schemas.roles import RoleListIn, RoleOut, RolePage
from apps.staff.schemas.schedules import ScheduleListIn, ScheduleDetailOut, SchedulePage
from apps.staff.schemas.settings import SettingsGetIn, SettingsOut
from apps.staff.schemas.time_off import (
    MyTimeOffIn,
    TimeOffDetailOut,
    TimeOffNamedOut,
    TimeOffDetailPage,
    TimeOffListIn,
    TimeOffPage,
    TodayIn,
)

from base.tests.ordering import assert_reads_backwards, listed_with

from .conftest import HUB_DB, make_member, make_role, make_time_off, run

pytestmark = HUB_DB


# Declarations


@pytest.mark.parametrize(
    ("name", "permission", "input", "output", "expose_api"),
    [
        ("staff.member.list", "staff.view", MemberListIn, MemberPage, True),
        ("staff.member.detail", "staff.view", MemberRefIn, MemberDetailOut, True),
        ("staff.member.mine", "staff.view", MineIn, MineOut, True),
        # Whoever holds the session, with no Staff permission: Sales attributes «Me» with it (SALE-F16).
        ("staff.member.current", None, CurrentMemberIn, CurrentMemberOut, False),
        ("staff.member.compensation", "staff.view_compensation", CompensationListIn, CompensationPage, False),
        ("staff.member.stats", "staff.view", MemberStatsIn, MemberStatsOut, False),
        ("staff.commission.summary", "staff.view_compensation", CommissionSummaryIn, CommissionPage, True),
        ("staff.role.list", "staff.view", RoleListIn, RolePage, True),
        ("staff.role.detail", "staff.view", ByIdIn, RoleOut, False),
        ("staff.schedule.list", "staff.view", ScheduleListIn, SchedulePage, True),
        ("staff.schedule.detail", "staff.view", ByIdIn, ScheduleDetailOut, False),
        ("staff.availability.for_member", "staff.view", AvailabilityIn, AvailabilityOut, True),
        ("staff.time_off.list", "staff.view_time_off", TimeOffListIn, TimeOffPage, False),
        ("staff.time_off.detail", "staff.view_time_off_detail", ByIdIn, TimeOffDetailOut, False),
        ("staff.time_off.get", "staff.view_time_off", ByIdIn, TimeOffNamedOut, False),
        ("staff.time_off.today", "staff.view_time_off", TodayIn, TimeOffPage, False),
        ("staff.time_off.mine", "staff.view_time_off", MyTimeOffIn, TimeOffDetailPage, True),
        ("staff.settings.get", "staff.view", SettingsGetIn, SettingsOut, False),
        # Whoever sees the team reaches it, and of them, whoever adds or edits a record reads it (checked inside).
        ("staff.account.list", "staff.view", AccountListIn, AccountPage, False),
    ],
)
def test_declarations(name, permission, input, output, expose_api):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output, op.expose_api) == (
        "query",
        permission,
        input,
        output,
        expose_api,
    )


def _tied_members():
    return [make_member("Ana", "López").id for _ in range(4)]


def _tied_roles():
    return [make_role(f"Role {n}", color="#ff0000").id for n in range(4)]


def _tied_time_off():
    ana = make_member("Ana", "López")
    return [make_time_off(ana, f"2026-0{n}-01").id for n in range(1, 5)]


@pytest.mark.parametrize(
    ("operation", "schema", "tied", "column"),
    [
        ("staff.member.list", MemberListIn, _tied_members, "status"),
        ("staff.member.list", MemberListIn, _tied_members, "name"),
        ("staff.member.compensation", CompensationListIn, _tied_members, "status"),
        ("staff.role.list", RoleListIn, _tied_roles, "color"),
        ("staff.time_off.list", TimeOffListIn, _tied_time_off, "leave_type"),
        ("staff.time_off.list", TimeOffListIn, _tied_time_off, "member_name"),
    ],
)
def test_ties_go_by_id_in_the_lists_own_direction(operation, schema, tied, column):
    """hub#768 (as in Customers): a descending list is the ascending one read backwards, ties
    included, and its pages neither repeat nor lose rows."""
    assert_reads_backwards(listed_with(run, operation, column, schema=schema), sorted(tied()))
