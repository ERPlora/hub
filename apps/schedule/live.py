"""Live queries of the schedule app and the events that re-run them after the COMMIT."""

from live.live_registry import live

from apps.schedule.events import (
    HOURS_ALL,
    OVERRIDE_ALL,
    SETTINGS_UPDATED,
    SPECIAL_DAY_ALL,
    WEEK_UPDATED,
)

# The week's order comes from the settings.
live("schedule.week.get", on=[WEEK_UPDATED, SETTINGS_UPDATED])
live("schedule.special_day.list", on=SPECIAL_DAY_ALL)
live("schedule.override.list", on=OVERRIDE_ALL)
# The «default week» flag is set by a saved day or a confirmation.
live("schedule.settings.get", on=[SETTINGS_UPDATED, WEEK_UPDATED])
# Whatever changes when the business is open (the appointment book follows the hours of its range).
live("schedule.business.is_open", on=HOURS_ALL)
live("schedule.hours.for_range", on=HOURS_ALL)
