"""Write operations of the verifactu app: one operation = one transaction, with its events in the outbox.

- **Sealing** (``sealing._seal``): the record's chain head (``Chain``, one per issuer and environment) is locked with
  ``select_for_update`` in the record's transaction, so two invoices at once queue, take consecutive sequences
  and never share a previous fingerprint; a refusal rolls the number back. The record copies the invoice's
  figures, computes its fingerprint and its QR and, with the producer's details, builds its XML and validates it
  against the AEAT's schemas: what cannot be declared is never sealed.
- **Sending** (``sending._send``): per chain, the queue's control row (``SendControl``) is taken with
  ``SKIP LOCKED`` (two passes never send the same chain; sealing never waits for the network), the AEAT's waiting
  time is respected, the chain's unsent records go together in order (≤ 1,000) under one header and the AEAT's
  answer, as the gateway hands it back, settles each one. Nothing is ever taken as accepted without that answer.
- A sealed record is never edited in its figures nor its XML: it is corrected with a new one.

The clock is the business's (``base.business.business_zone``): ``FechaHoraHusoGenRegistro`` carries its offset.
"""

from . import (
    aeat_query as aeat_query,
    authorisation as authorisation,
    certificate_proof as certificate_proof,
    chains as chains,
    config as config,
    contingency as contingency,
    diagnostics as diagnostics,
    own_certificate as own_certificate,
    records as records,
    sealing as sealing,
    sending as sending,
    writes as writes,
)
