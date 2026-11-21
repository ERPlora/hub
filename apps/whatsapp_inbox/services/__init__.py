"""Write operations of the WhatsApp inbox: one operation, one transaction, its events in the outbox.

What erplora.com pushes (a message, a delivery status, the channel's state and templates) runs as the
system through ``whatsapp_inbox.receive``, which no role holds; what the team does (send, read,
assign, change the status, link a card, notes, erase) runs as the person.

Nothing waits for erplora.com inside a transaction (WORKBOOK «Reglas que no se rompen»). Sending keeps the
message ``queued`` in a short transaction and hands it over after the COMMIT (``deliveries.deliver``): a claim
(``message.claim_delivery``, ``sending``), the HTTP call with no transaction and no lock, and the answer in
another short transaction (``message.record_delivery``: ``sent``, ``failed`` with erplora.com's reason, or
still ``sending`` with why, to retry with the same key). Erasing does the same with the number erplora.com has
to forget (``erasing.forget``), and a template with its registration and deletion at Meta
(``template_handover.submit_template``, ``template_handover.remove_template``). Each hand-over runs in a
thread of the process's own (``base.outbound``), never in the loop that committed: the worker's relay and tick
go on for every hub while erplora.com answers. What a crash or a stopping worker leaves half-way, the worker's
``delivery.resume`` hands over again. A message is never «sent» without Meta's id.
"""

from . import (
    channel as channel,
    conversations as conversations,
    customer_reactions as customer_reactions,
    deliveries as deliveries,
    erasing as erasing,
    notes as notes,
    received as received,
    sending as sending,
    template_handover as template_handover,
    template_samples as template_samples,
    templates as templates,
    writes as writes,
)
