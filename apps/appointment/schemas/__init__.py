"""Input and output schemas of the appointment app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. A customer is
named by her id or, as a person says it, by her name, phone or email; a service and a professional by
their id or their name; an appointment by its id or its number (``APT-…``). A time without a zone is a
wall-clock time of the business («2026-10-19 10:00»); one with a zone is converted to it. Money is in
cents. Every input refuses a field it does not declare; an edit changes only what it sends.
"""

from . import (
    agenda as agenda,
    appointments as appointments,
    availability as availability,
    blocked_times as blocked_times,
    booking as booking,
    changes as changes,
    fields as fields,
    reactions as reactions,
    references as references,
    series as series,
    settings as settings,
)
