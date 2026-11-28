"""Input and output schemas of the cash register app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. Money travels
in whole cents and an amount is never negative: the type says whether it comes in or goes out. What a
person names aloud is accepted besides the id: a session by its number, a drawer by its name; and when
an operation on the open session names none, it is the open one («close the till»).
"""

from . import (
    app_lines as app_lines,
    closing as closing,
    counts as counts,
    currency as currency,
    fields as fields,
    movements as movements,
    registers as registers,
    sessions as sessions,
    settings as settings,
)
