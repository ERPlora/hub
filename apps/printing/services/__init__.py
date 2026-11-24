"""Write operations of the printing app: one operation = one transaction, with its events in the outbox.

The queue's state machine: a job waits ``pending``; a device takes it (``claim``: ``sent``, one more hand-out, a 90 s
lease) with ``SELECT … FOR UPDATE SKIP LOCKED``, so two devices never take the same one; the device confirms it
(``done``) or reports its failure (back to ``pending``, or ``failed`` after 5 hand-outs); a lease that runs out puts it
back in the queue at the next claim. A person retries a failed (or unanswered) job or cancels it, stamped. A job that
ended (printed, cancelled or failed) is forgotten 30 days later by the hourly prune, the platform's own (PRINTING-F20).

Every app that prints calls ``printing.job.create`` by name inside its own transaction; the job is the
structured document the app's renderer paints, never bytes.

Only a device set up to print takes, confirms and fails jobs, and only those of the printers it reaches: a
session that prints is not enough, or a waiter's phone would drain the till's receipts. Whoever sets up the
printers sets the device up — from the device («Print from this device»), or by printing from it — and changes
or retires it from any device. The device is known by the digest of its own id, which no screen shows.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    printers as printers,
    settings as settings,
    queueing as queueing,
    claims as claims,
    devices as devices,
    job_actions as job_actions,
    prune as prune,
    writes as writes,
)
