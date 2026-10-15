"""Live queries of the schedule app: every query can be followed live, re-run by the events that change it."""

from live.live_registry import live_registry

from apps.schedule import events, services  # noqa: F401  (registers the operations whose events are cited)

HOURS = [
    events.WEEK_UPDATED,
    events.SPECIAL_DAY_CREATED,
    events.SPECIAL_DAY_UPDATED,
    events.SPECIAL_DAY_DELETED,
    events.OVERRIDE_CREATED,
    events.OVERRIDE_UPDATED,
    events.OVERRIDE_DELETED,
]


def schedule_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("schedule.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_query_and_the_events_that_re_run_it():
    assert schedule_queries() == {
        # The week's order comes from the settings.
        "schedule.week.get": [events.WEEK_UPDATED, events.SETTINGS_UPDATED],
        "schedule.special_day.list": events.SPECIAL_DAY_ALL,
        "schedule.override.list": events.OVERRIDE_ALL,
        # The «default week» flag is set by a saved day or a confirmation.
        "schedule.settings.get": [events.SETTINGS_UPDATED, events.WEEK_UPDATED],
        # Whatever changes when the business is open.
        "schedule.business.is_open": HOURS,
        "schedule.hours.for_range": HOURS,
    }
