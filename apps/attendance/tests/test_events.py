"""The attendance app's event vocabulary (``attendance.<entity>.<fact in the past tense>``) and its one
reaction: a staff member's termination closes their open working day (ATTENDANCE-F13)."""

import re

import pytest
from live.operations import NAME_RE

from apps.attendance import events
from apps.attendance.models import Correction, Record
from apps.attendance.schemas import ClosedOut

from .conftest import A, make_member, utc

PAST_FACT = re.compile(r"^attendance\.(record|break|settings)\.[a-z_]+ed(_in|_out)?$")


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str) and value.startswith("attendance.")
    }


def test_the_seven_events():
    assert declared() == {
        "CLOCKED_IN": "attendance.record.clocked_in",
        "CLOCKED_OUT": "attendance.record.clocked_out",
        "BREAK_STARTED": "attendance.break.started",
        "BREAK_ENDED": "attendance.break.ended",
        "RECORD_CORRECTED": "attendance.record.corrected",
        "RECORD_FLAGGED": "attendance.record.flagged",
        "SETTINGS_UPDATED": "attendance.settings.updated",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_all_lists_every_event_once():
    assert events.ALL == list(declared().values())


def test_the_groups():
    # Who is in now changes with every clocking, break, correction and flag.
    assert events.PRESENCE == [
        events.CLOCKED_IN,
        events.CLOCKED_OUT,
        events.BREAK_STARTED,
        events.BREAK_ENDED,
        events.RECORD_CORRECTED,
        events.RECORD_FLAGGED,
    ]
    assert events.RECORD_ALL == events.PRESENCE


def test_the_staff_events_it_follows_are_staffs():
    from apps.staff import events as staff_events

    assert events.MEMBER_CREATED == staff_events.MEMBER_CREATED
    assert events.MEMBER_UPDATED == staff_events.MEMBER_UPDATED
    assert events.MEMBER_TERMINATED == staff_events.MEMBER_TERMINATED


def test_it_reacts_only_to_a_termination():
    assert events.REACTIONS == {
        "staff.member.terminated": "attendance.record.close_for_terminated",
    }
    assert events.react(A, "staff.member.created", {"id": "x"}) is None


@pytest.mark.django_db
def test_a_termination_closes_the_open_day_with_a_system_correction(clock):
    ana = make_member(status="terminated")
    day = Record.objects.create(
        member=ana,
        clock_in_at=utc("2026-10-06T08:00"),
        work_date=utc("2026-10-06T08:00").date(),
    )
    clock("2026-10-06T12:00")

    result = events.react(A, "staff.member.terminated", {"id": str(ana.id)})

    assert isinstance(result, ClosedOut) and result.record.id == day.id
    day.refresh_from_db()
    assert (day.status, day.clock_out_at) == ("closed", utc("2026-10-06T12:00"))
    trail = Correction.objects.get(record=day)
    assert trail.created_by is None and trail.new_status == "closed"
