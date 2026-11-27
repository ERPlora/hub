"""Input and output schemas of the online booking app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every input field says what it is. A booking is
named by its id, its appointment number (``APT-…``) or as a person says it: the customer (name, phone or
email) and the day. A time without a zone is a wall-clock time of the business («2030-03-05 10:00»). Money is
in cents. Every input refuses a field it does not declare; the settings change only what they send.
"""

from . import (
    bookings as bookings,
    fields as fields,
    public as public,
    reactions as reactions,
    settings as settings,
)
