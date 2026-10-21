"""Events of the printing app (``printing.<entity>.<fact>``) and its reactions: none.

services.py records them in the outbox, in the command's transaction; live.py names the ones that re-run
each live query. They carry ids only, never the document (it may hold a customer's name or tax id).
``printing.job.queued`` is also the nudge base's ``/ws/print`` turns into a ``wake`` for the devices
(WORKBOOK «Contrato con la plataforma»).

No reactions: whoever prints calls ``printing.job.create`` by name, inside its own transaction.
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

SETTINGS_UPDATED = "printing.settings.updated"
PRINTER_CREATED = "printing.printer.created"
PRINTER_UPDATED = "printing.printer.updated"
JOB_QUEUED = "printing.job.queued"
JOB_CLAIMED = "printing.job.claimed"
JOB_PRINTED = "printing.job.printed"
JOB_FAILED = "printing.job.failed"
JOB_RETRIED = "printing.job.retried"
JOB_CANCELLED = "printing.job.cancelled"
#: The hourly prune forgot the jobs that ended over 30 days ago (PRINTING-F20); it carries how many.
JOB_PRUNED = "printing.job.pruned"
#: A device was set up to print (or printed for the first time from it, by whoever sets up printers), changed
#: (its name or its printers) or retired (PRINTING-F18). They carry the registration's id, never the device's own.
DEVICE_REGISTERED = "printing.device.registered"
DEVICE_UPDATED = "printing.device.updated"
DEVICE_RETIRED = "printing.device.retired"

ALL = [
    SETTINGS_UPDATED,
    PRINTER_CREATED,
    PRINTER_UPDATED,
    JOB_QUEUED,
    JOB_CLAIMED,
    JOB_PRINTED,
    JOB_FAILED,
    JOB_RETRIED,
    JOB_CANCELLED,
    JOB_PRUNED,
    DEVICE_REGISTERED,
    DEVICE_UPDATED,
    DEVICE_RETIRED,
]
#: Every change of the devices that print.
DEVICE_EVENTS = [DEVICE_REGISTERED, DEVICE_UPDATED, DEVICE_RETIRED]
#: Every change of the queue: what re-runs the screens that show it.
JOB_EVENTS = [JOB_QUEUED, JOB_CLAIMED, JOB_PRINTED, JOB_FAILED, JOB_RETRIED, JOB_CANCELLED, JOB_PRUNED]

#: Event of another app → the operation of this app that reacts to it: none (see above).
REACTIONS: dict[str, str] = {}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope``; ``None``: it reacts to none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
