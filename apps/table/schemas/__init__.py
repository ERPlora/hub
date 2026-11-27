"""Input and output schemas of the table app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. A record is
named by its id or, as a person says it (assistant, voice), by its number or its name: a table by its
number («4») and, when the number repeats, its zone («the terrace»); a zone by its name; a customer by
their name or phone. Every input refuses a field it does not declare; an edit changes only the fields
it sends. Moments travel ISO 8601 with their zone; money in cents.

Each id a write takes is marked with the read that names its record (``names``, base/assistant/cards.py ``REFERS``,
checked at start by ``base.E009``): the assistant's card says which zone, table, check, check of Sales, customer,
reservation or line, as the person who confirms reads it, never by the id. A table by its number with its zone
(«5 (Terrace)»: the number repeats across zones), a check by where it is, a reservation by the name its hold paints
on the table (Tables does not require Reservations) and a line by its name.

The inputs of the reactions to other apps' events (Sales, Customers, Reservations) read only what they
need from the emitter's payload and ignore the rest, never refuse it.
"""

from . import (
    fields as fields,
    floor as floor,
    floor_plan as floor_plan,
    holds as holds,
    sessions as sessions,
    settings as settings,
    tables as tables,
    waiters as waiters,
    zones as zones,
)
