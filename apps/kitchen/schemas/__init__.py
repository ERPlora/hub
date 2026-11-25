"""Input and output schemas of the kitchen app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. A record is named
by its id or, as a person says it (assistant, voice), by its number or its name: a ticket by its number
(«12», «#0012», «20261014-0012») or its label («Table 4»); a station by its name («grill») or «none» for
the dishes with no station; a product or a category of Inventory by its name. Every input refuses a field
it does not declare; an edit changes only the fields it sends. Moments travel ISO 8601 with their zone;
money in cents.

The inputs of the reactions to Sales' events read only what they need from the emitter's payload and
ignore the rest, never refuse it.
"""

from . import (
    board as board,
    fields as fields,
    history as history,
    rounds as rounds,
    routing as routing,
    settings as settings,
    stations as stations,
    tickets as tickets,
)
