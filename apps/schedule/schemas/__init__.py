"""Input and output schemas of the schedule app's operations (OpenAPI, live params, 422 per field, and the
JSON Schema of the assistant's tools: every field says what it is).

The rules of a set of intervals live once, in ``intervals.check_intervals`` (engine.py underneath): the weekly day,
the special day and the temporary change refuse the same things with the same words, under
``intervals``. A day of the week is a number (0 = Monday) or its name in English or Spanish, so the
assistant can be spoken to.
"""

from . import (
    fields as fields,
    hours as hours,
    intervals as intervals,
    is_open as is_open,
    overrides as overrides,
    settings as settings,
    special_days as special_days,
    week as week,
)
