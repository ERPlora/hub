"""Live queries of the printing app and the events that re-run them after the COMMIT.

A job that changes state re-runs the queue, the printers' state and the summary by function; a printer
that changes re-runs everything that names it (and the settings, which forget it when it changes
function); the settings re-run what shows the printer chosen for each function.
"""

from live.live_registry import live

from apps.printing import events as E

PRINTERS = [E.PRINTER_CREATED, E.PRINTER_UPDATED, *E.JOB_EVENTS]

live("printing.settings.get", on=[E.SETTINGS_UPDATED, E.PRINTER_UPDATED])
live("printing.printer.list", on=PRINTERS)
live("printing.printer.get", on=PRINTERS)
live("printing.printer.status", on=[*PRINTERS, E.SETTINGS_UPDATED])
live("printing.job.list", on=[*E.JOB_EVENTS, E.PRINTER_UPDATED])
live("printing.job.summary", on=[*PRINTERS, E.SETTINGS_UPDATED])
