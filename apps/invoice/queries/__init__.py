"""Read operations of the invoice app (``READ ONLY``), and how a document is read.

``rows.invoice_row`` and ``rows.invoice_detail`` are the one way a document becomes an output: the lists, the
detail, the document of a sale and every write (services/) answer with them, so what the screen shows and what the
assistant reads never drift apart; the same for ``series.series_row`` and ``issuer.issuer_row``.
``rows.document_of_sale`` finds the document in force of a sale (its full invoice when its ticket was replaced).
``documents.render_document`` writes the printable A4 document (``templates/invoice/invoice.html``) in the reader's
language.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    public as public,
    invoices as invoices,
    export as export,
    pdf as pdf,
    refunds as refunds,
    series as series,
    rectifying as rectifying,
    numbering as numbering,
    issuer as issuer,
    platform_invoices as platform_invoices,
    documents as documents,
    fiscal_archive as fiscal_archive,
    overdue as overdue,
    ownership as ownership,
    platform_reading as platform_reading,
    rows as rows,
)
