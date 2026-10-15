"""Live queries of the attendance app and the events that re-run them after the COMMIT.

Who is in now (``attendance.presence.list``) is live: it follows every clocking, break, correction and
flag. Staff's events repaint the names (a rename) and unlink the clock of a terminated person. The CSV
export is a one-shot read: not subscribable.
"""

from live.live_registry import live

from apps.attendance.events import (
    CLOCKED_IN,
    MEMBER_CREATED,
    MEMBER_TERMINATED,
    MEMBER_UPDATED,
    RECORD_ALL,
    RECORD_CORRECTED,
    SETTINGS_UPDATED,
)

# A record newly linked to the account (created) lets the clock work at once; a termination unlinks it.
live("attendance.record.current", on=[*RECORD_ALL, MEMBER_CREATED, MEMBER_UPDATED, MEMBER_TERMINATED])
live("attendance.record.list", on=[*RECORD_ALL, MEMBER_UPDATED])
live("attendance.record.detail", on=[*RECORD_ALL, MEMBER_UPDATED])
live("attendance.correction.list", on=[RECORD_CORRECTED])
# A terminated record is nobody who is in.
live("attendance.presence.list", on=[*RECORD_ALL, MEMBER_UPDATED, MEMBER_TERMINATED])
# The «Person» filter: who exists in Staff, and whoever left but has days (a first clock-in adds none
# new, but a person terminated after it keeps showing).
live(
    "attendance.person.list",
    on=[CLOCKED_IN, MEMBER_CREATED, MEMBER_UPDATED, MEMBER_TERMINATED],
)
live("attendance.settings.get", on=[SETTINGS_UPDATED])
