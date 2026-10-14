"""The staff app's event vocabulary: ``staff.<entity>.<fact in the past tense>``."""

import re

from live.operations import NAME_RE

from apps.staff import events

PAST_FACT = re.compile(r"^staff\.(member|role|schedule|time_off|settings)\.[a-z_]+ed$")


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str)
    }


def test_the_fourteen_events():
    assert declared() == {
        "MEMBER_CREATED": "staff.member.created",
        "MEMBER_UPDATED": "staff.member.updated",
        "MEMBER_DEACTIVATED": "staff.member.deactivated",
        "MEMBER_TERMINATED": "staff.member.terminated",
        "ROLE_CREATED": "staff.role.created",
        "ROLE_UPDATED": "staff.role.updated",
        "SCHEDULE_CREATED": "staff.schedule.created",
        "SCHEDULE_UPDATED": "staff.schedule.updated",
        "SCHEDULE_DELETED": "staff.schedule.deleted",
        "TIME_OFF_CREATED": "staff.time_off.created",
        "TIME_OFF_APPROVED": "staff.time_off.approved",
        "TIME_OFF_REJECTED": "staff.time_off.rejected",
        "TIME_OFF_CANCELLED": "staff.time_off.cancelled",
        "SETTINGS_UPDATED": "staff.settings.updated",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_all_lists_every_event_once():
    assert events.ALL == list(declared().values())


def test_the_groups_used_by_live_py():
    assert events.MEMBER_ALL == [
        value for value in events.ALL if value.startswith("staff.member.")
    ]
    assert events.SCHEDULE_ALL == [
        value for value in events.ALL if value.startswith("staff.schedule.")
    ]
    assert events.TIME_OFF_ALL == [
        value for value in events.ALL if value.startswith("staff.time_off.")
    ]
