"""Input and output schemas of the verifactu app's operations (OpenAPI, live params, 422 per field, and the JSON
Schema of the assistant's tools: every field says what it is).

Made for voice: a record is named by its id or by the **number of its invoice** (``TICKET-2026-000012``: its
latest record); an issuer by its tax ID (by default, Invoicing's issuer). Money is whole cents with a sign; dates
are ISO ``YYYY-MM-DD``.
"""

from . import (
    aeat_records as aeat_records,
    authorisation as authorisation,
    chains as chains,
    config as config,
    contingency as contingency,
    diagnostics as diagnostics,
    events as events,
    fields as fields,
    own_certificate as own_certificate,
    records as records,
    stats as stats,
)
