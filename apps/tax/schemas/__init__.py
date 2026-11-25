"""Input and output schemas of the tax app's operations (OpenAPI, live params, 422 per field, and the
JSON Schema of the assistant's tools: every field says what it is).
"""

from . import (
    aliases as aliases,
    calculation as calculation,
    categories as categories,
    fields as fields,
    jurisdiction as jurisdiction,
    references as references,
    rules as rules,
    settings as settings,
)
