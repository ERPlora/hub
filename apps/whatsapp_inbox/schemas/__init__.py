"""Input and output schemas of the WhatsApp inbox's operations (OpenAPI, live params, 422 per field).

Every field has a description: these schemas are also the JSON Schema of the assistant's tools and the
contract of erplora.com's doors (WORKBOOK «Contrato con el SaaS»). A conversation can be named by its
``id`` or, when the id is not known (by voice, by text), by its number or by the customer's name
(``conversation``); a person of the team by their id or their name, username or email.
"""

from . import (
    agents as agents,
    channel as channel,
    conversations as conversations,
    customer_reactions as customer_reactions,
    deliveries as deliveries,
    erasing as erasing,
    fields as fields,
    health as health,
    messages as messages,
    notes as notes,
    received as received,
    sending as sending,
    template_handover as template_handover,
    template_samples as template_samples,
    templates as templates,
)
