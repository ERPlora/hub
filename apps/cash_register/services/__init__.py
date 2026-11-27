"""Write operations of the cash register app: one operation = one transaction, with its events in the outbox.

Opening numbers the session with its day's counter (``UPDATE … RETURNING``, in the same transaction: a
refused open never burns a number) and one open session at a time is the database's (a partial unique
index): two opens at once open one. Closing, recording and counting lock the session's row first
(``select_for_update``), so two closes at once close it once and nothing lands in a session being closed.
Closing copies the shift's sale lines into the session: a closed session never moves again. Printing a
session's report puts it in Printing's queue by its operation's name (``printing.job.create``): Printing off
or absent, or no active receipt printer in it, is nothing queued, and the screen prints through the browser.
"""

# Not alphabetical: importing a module registers its operations, and this is the order the registry lists them.
from . import (
    settings as settings,
    registers as registers,
    sessions as sessions,
    movements as movements,
    counts as counts,
    reports as reports,
)
