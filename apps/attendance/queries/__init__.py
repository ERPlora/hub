"""Read operations of the attendance app, and the lookups services.py shares (WORKBOOK «Servicios»).

Every query runs READ ONLY. Who sees what: whoever clocks sees their own working days and their history
(the law makes them accessible to the worker); ``attendance.view_all`` sees the team. «Own» is every day
of a staff record linked to the caller's user (a rehired person keeps their old days). Durations are
computed here, in seconds, as of the moment the query runs (``as_of``); the screens make them run on
from there. A day waiting for review has no worked time: «until now» would count days nobody worked.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them (who a clock-in is for, the days, the CSV, the corrections, who is in, the people, the settings), and the
# helpers follow.
from . import (
    people as people,
    records as records,
    exports as exports,
    corrections as corrections,
    presence as presence,
    person_filter as person_filter,
    settings as settings,
    days as days,
    reads as reads,
)
