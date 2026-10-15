"""Events of the attendance app (``attendance.<entity>.<fact>``) and its reaction to Staff's events.

services.py records them in the outbox, in the command's transaction; live.py names the ones that re-run
each live query. They carry ids only: never a position or the reason of a correction (personal data).

Reaction: a staff member's termination closes their open working day (ATTENDANCE-F13), through an
operation of this app run as the system, in its own transaction. The outbox relay (phase 2, in the
worker) hands each delivered event to ``react``; the operation closes nothing when the person has no
open day, so a repeated delivery changes nothing.
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

from apps.staff import events as staff_events

CLOCKED_IN = "attendance.record.clocked_in"
CLOCKED_OUT = "attendance.record.clocked_out"
BREAK_STARTED = "attendance.break.started"
BREAK_ENDED = "attendance.break.ended"
RECORD_CORRECTED = "attendance.record.corrected"
RECORD_FLAGGED = "attendance.record.flagged"
SETTINGS_UPDATED = "attendance.settings.updated"

ALL = [
    CLOCKED_IN,
    CLOCKED_OUT,
    BREAK_STARTED,
    BREAK_ENDED,
    RECORD_CORRECTED,
    RECORD_FLAGGED,
    SETTINGS_UPDATED,
]
#: Every event that changes a working day (and so who is in now).
RECORD_ALL = [
    CLOCKED_IN,
    CLOCKED_OUT,
    BREAK_STARTED,
    BREAK_ENDED,
    RECORD_CORRECTED,
    RECORD_FLAGGED,
]
PRESENCE = RECORD_ALL

# Staff's events (its WORKBOOK fixes their payload: the member's id).
MEMBER_CREATED = staff_events.MEMBER_CREATED
MEMBER_UPDATED = staff_events.MEMBER_UPDATED
MEMBER_TERMINATED = staff_events.MEMBER_TERMINATED

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {
    MEMBER_TERMINATED: "attendance.record.close_for_terminated",
}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
