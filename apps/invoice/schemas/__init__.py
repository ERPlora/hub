"""Input and output schemas of the invoice app's operations (OpenAPI, live params, 422 per field, and the
JSON Schema of the assistant's tools: every field says what it is).

Made for voice: a document is named by its id or its number (``FACT-2026-000012``), a sale by its id or
its number of the day (``20261014-0003``), a customer by its id or by its name, phone or email (the
Customers app's reference), a series by its id or its code. A Spanish tax ID is checked with python-stdnum (NIF, NIE or CIF; the EU VAT number
with document type 02); a foreign one is taken as written. Money is whole cents; rates are percentages
with two decimals; quantities have three decimals, as the sale's.
"""

from . import (
    document_issuer as document_issuer,
    export as export,
    fields as fields,
    invoices as invoices,
    issuer as issuer,
    numbering as numbering,
    platform as platform,
    public as public,
    rectifying as rectifying,
    refunds as refunds,
    series as series,
)
