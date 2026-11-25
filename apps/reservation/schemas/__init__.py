"""Input and output schemas of the reservation app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. A record is named
by its id or as a person says it (assistant, voice): a reservation by its guest's name or phone and its
day («Ana's reservation tomorrow»), a table by its number («5») and, when the number repeats, its zone, a
customer by their name or phone, a slot by its weekday and start, a waitlist entry by its guest. Every
input refuses a field it does not declare; an edit changes only the fields it sends. A reservation's day
and time are the business's wall clock (``2026-10-15``, ``21:00``).

Each id a write takes is marked with the read that names its record (``names``, base/assistant/cards.py ``REFERS``,
checked at start by ``base.E009``): the assistant's card says which reservation, entry, slot, blocked date,
customer or table, as the person who confirms reads it, never by the id. Reservation's own records by the
``label`` its reads by id answer (as the book's dialogs say them), a customer by the name of their card
(Customers) and a table by its number (Tables).

The inputs of the reactions to Customers' events read only what they need from its payload and ignore the
rest, never refuse it.
"""

from . import (
    availability as availability,
    blocked_dates as blocked_dates,
    fields as fields,
    reactions as reactions,
    reservations as reservations,
    settings as settings,
    slots as slots,
    waitlist as waitlist,
)
