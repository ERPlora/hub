"""Instants are stored with their zone (UTC) and read on the business's clock. An appointment copies what
it was booked with — the customer's name and contact, each service's name, price and length, the
professional's name — so that changing a card or the catalog later never rewrites what was booked.
Money is in cents. Deleting an appointment or a series is logical (``deleted_at``): what points at them
keeps pointing.

One module per responsibility, each imported here so that Django registers its models, in this order.
"""

from . import (
    settings as settings,
    numbering as numbering,
    audit as audit,
    series as series,
    appointments as appointments,
    blocked_times as blocked_times,
)
