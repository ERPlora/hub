"""Read operations of the verifactu app, one module per entity or use case, and the read helpers ``services.py``
shares: importing each module here registers its operations.

Every query runs ``READ ONLY`` (``@operation(kind="query")``) and can be followed live (``live.py``). Lists page
(``limit`` ≤ 100) in a stable order with the id as tie-break.
"""

from . import (
    aeat_records as aeat_records,
    app_hooks as app_hooks,
    authorisation as authorisation,
    chains as chains,
    config as config,
    contingency as contingency,
    country as country,
    diagnostics as diagnostics,
    events as events,
    reads as reads,
    records as records,
    route as route,
    stats as stats,
)
