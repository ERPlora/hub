"""Ninja routes of the invoice app: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``): an invoice's id or number travels in the input, because a route
takes one parameter, the operation's input (none when the input has no fields). ``invoice.issuer.sync`` has no route: only the system calls it
(the SaaS's photo of the hub, through the platform).
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.invoice import queries, services
from apps.invoice.schemas import (
    AllocationsIn,
    BySourceIn,
    DocumentIn,
    FromRefundIn,
    FromSaleIn,
    FromVoidIn,
    GapsIn,
    InvoiceCreateIn,
    InvoiceGetIn,
    InvoiceListIn,
    IssuerIn,
    MarkPaidIn,
    RectificationPreviewIn,
    RectifyIn,
    RefundGetIn,
    SeriesCreateIn,
    SeriesListIn,
    SeriesPeekIn,
    SeriesUpdateIn,
    SubstituteIn,
)

router = Router(tags=["invoice"])


# Invoices


@bind(router, "invoice.invoice.list", "/invoice/invoices")
async def invoice_list(request, params: Query[InvoiceListIn]):
    return await run_operation(request, queries.list_invoices, params)


@bind(router, "invoice.invoice.get", "/invoice/invoices/detail")
async def invoice_get(request, params: Query[InvoiceGetIn]):
    return await run_operation(request, queries.get_invoice, params)


@bind(router, "invoice.invoice.by_source", "/invoice/invoices/by_source")
async def invoice_by_source(request, params: Query[BySourceIn]):
    return await run_operation(request, queries.by_source, params)


@bind(router, "invoice.invoice.document", "/invoice/invoices/document")
async def invoice_document(request, params: Query[DocumentIn]):
    return await run_operation(request, queries.document, params)


@bind(router, "invoice.invoice.print", "/invoice/invoices/print")
async def invoice_print(request, data: DocumentIn):
    return await run_operation(request, services.print_invoice, data)


@bind(router, "invoice.invoice.line_defaults", "/invoice/invoices/line_defaults")
async def invoice_line_defaults(request):
    return await run_operation(request, queries.line_defaults)


@bind(router, "invoice.invoice.create", "/invoice/invoices", status=201)
async def invoice_create(request, data: InvoiceCreateIn):
    return await run_operation(request, services.create, data)


@bind(router, "invoice.invoice.create_from_sale", "/invoice/invoices/from_sale")
async def invoice_create_from_sale(request, data: FromSaleIn):
    return await run_operation(request, services.create_from_sale, data)


@bind(router, "invoice.invoice.substitute", "/invoice/invoices/substitute")
async def invoice_substitute(request, data: SubstituteIn):
    return await run_operation(request, services.substitute, data)


@bind(router, "invoice.invoice.mark_paid", "/invoice/invoices/mark_paid")
async def invoice_mark_paid(request, data: MarkPaidIn):
    return await run_operation(request, services.mark_paid, data)


@bind(
    router,
    "invoice.invoice.rectification_preview",
    "/invoice/invoices/rectification_preview",
)
async def invoice_rectification_preview(
    request, params: Query[RectificationPreviewIn]
):
    return await run_operation(request, queries.rectification_preview, params)


@bind(router, "invoice.invoice.rectify", "/invoice/invoices/rectify")
async def invoice_rectify(request, data: RectifyIn):
    return await run_operation(request, services.rectify, data)


@bind(
    router,
    "invoice.invoice.rectify_from_refund",
    "/invoice/invoices/rectify_from_refund",
)
async def invoice_rectify_from_refund(request, data: FromRefundIn):
    return await run_operation(request, services.rectify_from_refund, data)


@bind(
    router, "invoice.invoice.rectify_from_void", "/invoice/invoices/rectify_from_void"
)
async def invoice_rectify_from_void(request, data: FromVoidIn):
    return await run_operation(request, services.rectify_from_void, data)


# Refunds of the Sales app, as an invoice names them


@bind(router, "invoice.refund.get", "/invoice/refunds/detail")
async def refund_get(request, params: Query[RefundGetIn]):
    return await run_operation(request, queries.get_refund, params)


# Series


@bind(router, "invoice.series.list", "/invoice/series")
async def series_list(request, params: Query[SeriesListIn]):
    return await run_operation(request, queries.list_series, params)


@bind(router, "invoice.series.peek_next", "/invoice/series/peek_next")
async def series_peek_next(request, params: Query[SeriesPeekIn]):
    return await run_operation(request, queries.peek_next, params)


@bind(router, "invoice.series.get", "/invoice/series/detail")
async def series_get(request, params: Query[SeriesPeekIn]):
    return await run_operation(request, queries.get_series, params)


@bind(router, "invoice.series.create", "/invoice/series", status=201)
async def series_create(request, data: SeriesCreateIn):
    return await run_operation(request, services.create_series, data)


@bind(router, "invoice.series.update", "/invoice/series/update")
async def series_update(request, data: SeriesUpdateIn):
    return await run_operation(request, services.update_series, data)


# Numbering


@bind(router, "invoice.numbering.status", "/invoice/numbering/status")
async def numbering_status(request):
    return await run_operation(request, queries.numbering_status)


@bind(router, "invoice.numbering.gaps", "/invoice/numbering/gaps")
async def numbering_gaps(request, params: Query[GapsIn]):
    return await run_operation(request, queries.numbering_gaps, params)


@bind(router, "invoice.numbering.allocations", "/invoice/numbering/allocations")
async def numbering_allocations(request, params: Query[AllocationsIn]):
    return await run_operation(request, queries.allocations, params)


# The issuer


@bind(router, "invoice.issuer.get", "/invoice/issuer")
async def issuer_get(request):
    return await run_operation(request, queries.get_issuer)


@bind(router, "invoice.issuer.update", "/invoice/issuer")
async def issuer_update(request, data: IssuerIn):
    return await run_operation(request, services.update_issuer, data)
