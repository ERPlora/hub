"""Write operations of the invoice app: one operation = one transaction, with its events in the outbox.

Every document goes through ``_issue``: the issuer is copied, the breakdown is audited, the number is
taken from its series with ``UPDATE … RETURNING`` (the row stays locked until the COMMIT, so two
documents of a series queue and a refused one leaves no gap) and the document, its lines and
``invoice.invoice.issued`` are written together. A document is never edited: only ``status`` and
``paid_at`` move (paid, cancelled when rectified whole). The operations that act on a sale or on a
document lock its row first, so a repeated or simultaneous request waits and answers what the first one
did, without spending a number. The clock is ``_now()``, and a day is its date on the business's (``business_zone``).
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    public as public,
    issuer as issuer,
    manual as manual,
    from_sale as from_sale,
    substitution as substitution,
    rectifying as rectifying,
    paying as paying,
    series as series,
    platform_invoices as platform_invoices,
    paper as paper,
    writes as writes,
    numbering as numbering,
    issuing as issuing,
    recipient as recipient,
)
