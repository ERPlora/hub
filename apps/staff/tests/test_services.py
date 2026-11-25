"""What the write operations of the staff app declare, and who hears of one.

The writes of each entity are tested by ``test_services_<module>.py``.
"""

import json

import psycopg
import pytest
from live.errors import Conflict
from live.operations import get
from live.outbox import channel_for

from apps.staff import events
from apps.staff.models import Member
from apps.staff.schemas.fields import DeletedOut, MemberRefIn
from apps.staff.schemas.members import (
    BulkCreatedOut,
    BulkCreateIn,
    MemberDetailOut,
    MemberIn,
    MemberPatchIn,
    TerminatedOut,
    TerminateIn,
)
from apps.staff.schemas.roles import RoleIn, RoleOut, RolePatchIn
from apps.staff.schemas.schedules import ScheduleIn, ScheduleOut, ScheduleRefIn, ScheduleUpdateIn, SetActiveIn
from apps.staff.schemas.settings import SettingsIn, SettingsOut
from apps.staff.schemas.time_off import TimeOffDetailOut, TimeOffIn, TimeOffRefIn, TimeOffRequestIn
from base.tenancy.context import use_hub

from .conftest import HUB_DB_COMMITTED, QUIET, A, B, ctx_for, make_member

WAIT = 1.0


# Declarations


@pytest.mark.parametrize(
    ("name", "permission", "input", "output", "expose_api"),
    [
        ("staff.member.create", "staff.add_member", MemberIn, MemberDetailOut, True),
        (
            "staff.member.bulk_create",
            "staff.add_member",
            BulkCreateIn,
            BulkCreatedOut,
            False,
        ),
        (
            "staff.member.update",
            "staff.change_member",
            MemberPatchIn,
            MemberDetailOut,
            True,
        ),
        (
            "staff.member.deactivate",
            "staff.delete_member",
            MemberRefIn,
            MemberDetailOut,
            False,
        ),
        (
            "staff.member.terminate",
            "staff.delete_member",
            TerminateIn,
            TerminatedOut,
            False,
        ),
        ("staff.role.create", "staff.manage_settings", RoleIn, RoleOut, False),
        ("staff.role.update", "staff.manage_settings", RolePatchIn, RoleOut, False),
        (
            "staff.schedule.create",
            "staff.manage_settings",
            ScheduleIn,
            ScheduleOut,
            False,
        ),
        (
            "staff.schedule.update",
            "staff.manage_settings",
            ScheduleUpdateIn,
            ScheduleOut,
            False,
        ),
        (
            "staff.schedule.set_active",
            "staff.manage_settings",
            SetActiveIn,
            ScheduleOut,
            False,
        ),
        ("staff.schedule.delete", "staff.manage_settings", ScheduleRefIn, DeletedOut, False),
        (
            "staff.time_off.create",
            "staff.manage_time_off",
            TimeOffIn,
            TimeOffDetailOut,
            False,
        ),
        (
            "staff.time_off.request",
            "staff.request_time_off",
            TimeOffRequestIn,
            TimeOffDetailOut,
            False,
        ),
        (
            "staff.time_off.approve",
            "staff.manage_time_off",
            TimeOffRefIn,
            TimeOffDetailOut,
            False,
        ),
        (
            "staff.time_off.reject",
            "staff.manage_time_off",
            TimeOffRefIn,
            TimeOffDetailOut,
            False,
        ),
        (
            "staff.time_off.cancel",
            "staff.request_time_off",
            TimeOffRefIn,
            TimeOffDetailOut,
            False,
        ),
        (
            "staff.settings.update",
            "staff.manage_settings",
            SettingsIn,
            SettingsOut,
            False,
        ),
    ],
)
def test_declarations(name, permission, input, output, expose_api):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output, op.expose_api) == (
        "command",
        permission,
        input,
        output,
        expose_api,
    )


# Notifications: after the COMMIT, on the channel of the command's scope only


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=WAIT, stop_after=None):
    return [
        (note.channel, json.loads(note.payload))
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
    ]


@HUB_DB_COMMITTED
def test_a_command_in_scope_b_notifies_the_channel_of_b_only(listen, hub_b):
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        get("staff.member.create")(ctx_for(scope=B), MemberIn(first_name="Ana", last_name="López"))

    assert received(on_b, stop_after=1) == [
        (channel_for(B), {"events": [events.MEMBER_CREATED]})
    ]
    assert received(on_a, timeout=QUIET) == []

    # Positive control: the same listener of A does hear a command run in A.
    get("staff.member.update")(ctx_for(scope=A), MemberPatchIn(id=make_member().id, phone="1"))
    assert received(on_a, stop_after=1) == [
        (channel_for(A), {"events": [events.MEMBER_UPDATED]})
    ]
    assert received(on_b, timeout=QUIET) == []


@HUB_DB_COMMITTED
def test_a_refused_command_notifies_nobody(listen, hub_b):
    with use_hub(hub_b):
        member = Member.objects.create(first_name="Ana", last_name="López", status=Member.Status.INACTIVE)
        on_b = listen(B)
        with pytest.raises(Conflict):
            get("staff.member.deactivate")(ctx_for(scope=B), MemberRefIn(id=member.id))
    assert received(on_b, timeout=QUIET) == []
