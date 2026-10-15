"""The schedule app's event vocabulary: ``schedule.<entity>.<fact in the past tense>``."""

import re

from live.operations import NAME_RE

from apps.schedule import events

PAST_FACT = re.compile(r"^schedule\.(week|special_day|override|settings)\.[a-z_]+ed$")


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str)
    }


def test_the_eight_events():
    assert declared() == {
        "WEEK_UPDATED": "schedule.week.updated",
        "SPECIAL_DAY_CREATED": "schedule.special_day.created",
        "SPECIAL_DAY_UPDATED": "schedule.special_day.updated",
        "SPECIAL_DAY_DELETED": "schedule.special_day.deleted",
        "OVERRIDE_CREATED": "schedule.override.created",
        "OVERRIDE_UPDATED": "schedule.override.updated",
        "OVERRIDE_DELETED": "schedule.override.deleted",
        "SETTINGS_UPDATED": "schedule.settings.updated",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_all_lists_every_event_once_and_the_groups_used_by_live_py():
    assert events.ALL == list(declared().values())
    assert events.SPECIAL_DAY_ALL == [
        value for value in events.ALL if value.startswith("schedule.special_day.")
    ]
    assert events.OVERRIDE_ALL == [
        value for value in events.ALL if value.startswith("schedule.override.")
    ]
    # Every event but the settings' changes when the business is open.
    assert events.HOURS_ALL == [
        value for value in events.ALL if value != events.SETTINGS_UPDATED
    ]
