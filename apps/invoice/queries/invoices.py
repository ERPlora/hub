"""Invoices (INVOICE-F16, F17, F18, F20): the list, one document, the document of a sale and its printable A4 page;
and the rate a typed line of a manual invoice starts with (INVOICE-F03).
"""

from django.db.models import F, Q
from django.utils import translation
from live.context import OperationContext
from live.operations import operation

from apps.invoice.queries.documents import render_document
from apps.invoice.queries.overdue import OVERDUE, overdue
from apps.invoice.queries.ownership import INVOICES
from apps.invoice.queries.rows import _page, document_of_sale, find_invoice, invoice_detail, invoice_row, with_links
from apps.invoice.schemas.invoices import (
    BySourceIn,
    BySourceOut,
    DocumentIn,
    DocumentOut,
    InvoiceFiltersIn,
    InvoiceGetIn,
    InvoiceListIn,
    InvoiceOut,
    InvoicePage,
    LineDefaultsIn,
    LineDefaultsOut,
)
from apps.sale.queries.sales import visible_sale
from apps.tax.queries.jurisdiction import business_tax_kind
from apps.tax.queries.resolution import resolve_tax

#: A sort column → its ordering; every one ends with the newest first, then the id.
_SORTS = {
    "issued_at": ["issued_at"],
    "issue_date": ["issue_date", "issued_at"],
    "number": ["series_code", "year", "sequence"],
    "customer_name": ["customer_name"],
    "total_amount": ["total_amount"],
    "status": ["status"],
    "invoice_type": ["invoice_type"],
    "series_code": ["series_code", "year", "sequence"],
}


def _ordering(sort: str, direction: str) -> list:
    columns = [
        F(column).desc() if direction == "desc" else F(column).asc()
        for column in _SORTS[sort]
    ]
    tie = (
        [F("issued_at").desc(), F("id").desc()]
        if direction == "desc"
        else [F("issued_at").asc(), F("id").asc()]
    )
    return [*columns, *tie]


def filter_invoices(ctx: OperationContext, params: InvoiceFiltersIn):
    """The invoices the caller sees that match the list's search and filters."""
    invoices = INVOICES.visible(ctx)
    if params.search:
        text = params.search.strip()
        invoices = invoices.filter(
            Q(number__icontains=text)
            | Q(customer_name__icontains=text)
            | Q(customer_tax_id__icontains=text)
        )
    if params.status == OVERDUE:
        invoices = invoices.filter(overdue())
    exact = {
        "status": params.status if params.status != OVERDUE else None,
        "invoice_type": params.invoice_type,
        "series_code": params.series_code.strip().upper()
        if params.series_code
        else None,
        "source_type": params.source_type,
        "customer_id": params.customer_id,
        "issue_date__gte": params.issue_date_from,
        "issue_date__lte": params.issue_date_to,
        "total_amount__gte": params.total_amount_from,
        "total_amount__lte": params.total_amount_to,
    }
    return invoices.filter(
        **{lookup: value for lookup, value in exact.items() if value is not None}
    )


@operation(
    "invoice.invoice.list",
    kind="query",
    permission="invoice.view_invoice",
    input=InvoiceListIn,
    output=InvoicePage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which invoices have we issued this month?",
                "show me the invoices of Carpintería Lema that are still pending",
                "which invoices are overdue?",
            ),
            "es": (
                "¿qué facturas hemos emitido este mes?",
                "busca las facturas de Carpintería Lema que siguen pendientes",
                "¿qué facturas están vencidas sin cobrar?",
            ),
        },
        "description": "List the invoices, the last issued first: search by number, customer's name or tax ID; filter "
        "by status (issued, paid, cancelled; overdue: not paid and past its due date), type (F1, F2 ticket, F3, R1–R5), "
        "series, source, issue dates and total (cents). Pages of up to 100."
    },
)
def list_invoices(ctx: OperationContext, params: InvoiceListIn) -> dict:
    invoices = filter_invoices(ctx, params)
    invoices = with_links(invoices).order_by(*_ordering(params.sort, params.dir))
    return _page(invoices, params, invoice_row)


@operation(
    "invoice.invoice.get",
    kind="query",
    permission="invoice.view_invoice",
    input=InvoiceGetIn,
    output=InvoiceOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "open FACT-2025-000317",
                "who was FACT-2025-000317 made out to, and for how much?",
            ),
            "es": (
                "abre la FACT-2025-000317",
                "¿a quién se le hizo la FACT-2025-000317 y por cuánto?",
            ),
        },
        "description": "Read one invoice by its number (or id): its issuer, recipient, lines, tax breakdown, totals, "
        "status, and the documents it rectifies, replaces or is rectified or replaced by."
    },
)
def get_invoice(ctx: OperationContext, params: InvoiceGetIn) -> dict:
    return invoice_detail(find_invoice(ctx, params.invoice_id, params.number))


@operation(
    "invoice.invoice.by_source",
    kind="query",
    permission="invoice.view_invoice",
    input=BySourceIn,
    output=BySourceOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which invoice belongs to sale 20261103-0012?",
                "did sale 20261103-0012 end up with a ticket or a full invoice?",
            ),
            "es": (
                "¿qué factura tiene la venta 20261103-0012?",
                "¿con qué documento se quedó la venta 20261103-0012?",
            ),
        },
        "description": "The invoice in force of a sale (by the sale's number of the day or id): its ticket or invoice, "
        "or the full invoice that replaced its ticket. Found false while it has none."
    },
)
def by_source(ctx: OperationContext, params: BySourceIn) -> dict:
    sale = visible_sale(ctx, params.sale_id, params.sale)
    document = document_of_sale(sale.id)
    return {
        "found": document is not None,
        "invoice": invoice_detail(document) if document else None,
    }


@operation(
    "invoice.invoice.document",
    kind="query",
    permission="invoice.view_invoice",
    input=DocumentIn,
    output=DocumentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "show me FACT-2025-000317 as an A4 page",
                "let me see the sheet of FACT-2025-000317 as it is handed over",
            ),
            "es": (
                "enséñame la FACT-2025-000317 en A4",
                "enséñame la hoja de la FACT-2025-000317 tal como se entrega",
            ),
        },
        "description": "The printable A4 document of an invoice (by its number), a whole HTML page in the reader's "
        "language: issuer, recipient, lines, tax breakdown, totals and what it rectifies. duplicate marks a copy."
    },
)
def document(ctx: OperationContext, params: DocumentIn) -> dict:
    invoice = find_invoice(ctx, params.invoice_id, params.number)
    with translation.override(ctx.language):
        html = render_document(invoice, duplicate=params.duplicate)
    return {"invoice_id": invoice.id, "number": invoice.number, "html": html}


# The general rate of a territory is the one of its generic categories: goods first, then services.
GENERAL_CATEGORIES = ("product.generic", "service.generic")


@operation(
    "invoice.invoice.line_defaults",
    kind="query",
    permission="invoice.add_invoice",
    input=LineDefaultsIn,
    output=LineDefaultsOut,
    ai={
        "asks": {
            "en": (
                "what VAT does a line I type by hand start with?",
                "which rate would a manual invoice line get today?",
            ),
            "es": (
                "¿con qué IVA empieza una línea escrita a mano?",
                "¿qué tipo lleva de entrada una línea de una factura manual?",
            ),
        },
        "description": "The rate a line of a manual invoice starts with when its rate is typed: the territory's "
        "general rate from its own rule in Taxes, or none when the territory has no rule of its own tax. The tax "
        "it is declared with is the territory's, read with tax.settings.get (VAT, IGIC in the Canary Islands, "
        "IPSI in Ceuta and Melilla)."
    },
)
def line_defaults(ctx: OperationContext, params: LineDefaultsIn) -> dict:
    """A typed rate is declared subject, with the territory's tax (TAX-F11): a rule of another tax (a regional one
    kept with another tax; the national VAT never applies in a territory with its own) or an exempt one is never
    proposed."""
    tax = business_tax_kind()
    for key in GENERAL_CATEGORIES:
        resolution = resolve_tax(category_key=key)
        if resolution and resolution.tax_kind == tax and resolution.operation_class == "subject":
            return {"tax_rate": resolution.root.rate_pct}
    return {"tax_rate": None}
