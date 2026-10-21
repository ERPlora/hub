"""Live queries of the printing app and the events that re-run them after the COMMIT.

A job that changes state re-runs the queue, the printers' state and the summary by function; a printer
that changes re-runs everything that names it (and the settings, which forget it when it changes
function); the settings re-run what shows the printer chosen for each function. The devices that print re-run
when one is set up, changed or retired, when one takes a job and when a printer they reach changes.
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
# A claim stamps the device's last news; a printer renamed or deactivated shows in the rows of its devices.
live("printing.device.list", on=[*E.DEVICE_EVENTS, E.JOB_CLAIMED, E.PRINTER_UPDATED])
