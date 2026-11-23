"""The charged sales, their lines and payments, and whether the database holds any."""

from decimal import Decimal
from uuid import UUID

from django.db.models import Count, Exists, OuterRef, Q, QuerySet, StringAgg, Subquery, Sum, TextField, Value
from django.db.models.functions import Coalesce
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import AI, operation

from apps.sale.models import FiscalStatus, Refund, RefundLine, Sale, SaleLine, SalePayment
from apps.sale.queries.ownership import SALES
from apps.sale.queries.payment_methods import method_display_name
from apps.sale.queries.receipt_codes import paper_code
from apps.sale.schemas.sales import SaleByKeyIn, SaleByKeyOut, SaleListIn, SaleOut, SalePage, SaleRefIn
from base.business import currency_decimals
from base.ordering import list_order

SALE_NOT_FOUND = _("That sale does not exist.")


def find_sale(
    sale_id: UUID | None, number: str | None, *, lock: bool = False, among: QuerySet[Sale] | None = None
) -> Sale:
    """The sale of that id or number among ``among`` (every sale by default); one outside it does not exist."""
    sales = Sale.objects.all() if among is None else among
    if lock:
        sales = sales.select_for_update()
    sale = (
        sales.filter(pk=sale_id).first()
        if sale_id is not None
        else sales.filter(number=(number or "").strip()).first()
    )
    if sale is None:
        raise NotFound(str(SALE_NOT_FOUND), code="sale.sale_not_found")
    return sale


def visible_sale(ctx: OperationContext, sale_id: UUID | None, number: str | None, *, lock: bool = False) -> Sale:
    """``find_sale`` among the sales the caller sees (``SALES``): someone else's, for a person who sees only theirs,
    is the same 404 as one that does not exist."""
    return find_sale(sale_id, number, lock=lock, among=SALES.visible(ctx))


def returned_by_line(sale: Sale) -> dict[UUID, Decimal]:
    totals = (
        RefundLine.objects.filter(sale_line__sale=sale)
        .values("sale_line_id")
        .annotate(q=Sum("quantity"))
    )
    return {row["sale_line_id"]: row["q"] for row in totals}


def sale_line_row(line: SaleLine, returned: Decimal) -> dict:
    return {
        "id": line.id,
        "position": line.position,
        "order_line_id": line.order_line_id,
        "product_id": line.product_id,
        "department_id": line.department_id,
        "name": line.name,
        "sku": line.sku,
        "is_service": line.is_service,
        "unit": line.unit,
        "quantity": line.quantity,
        "unit_price": line.unit_price,
        "price_quantity": line.price_quantity,
        "pricing_unit": line.pricing_unit,
        "discount_percent": line.discount_percent,
        "is_gift": line.is_gift,
        "gift_reason": line.gift_reason,
        "notes": line.notes,
        "staff_id": line.staff_id,
        "service_id": line.service_id,
        "paid_by_voucher": line.paid_by_voucher,
        "voucher_name": line.voucher_name,
        "tax_category_key": line.tax_category_key,
        "tax_rate": line.tax_rate,
        "tax_country_code": line.tax_country_code,
        "tax_region_code": line.tax_region_code,
        "tax_rule_id": line.tax_rule_id,
        "net_amount": line.net_amount,
        "tax_amount": line.tax_amount,
        "line_total": line.line_total,
        "returned_quantity": returned,
        "modifiers": line.modifiers,
        "parent_line_id": line.parent_line_id,
        "combo_id": line.combo_id,
        "combo_name": line.combo_name,
        "components": line.components,
    }


def sessions_to_return(sale: Sale) -> int:
    """Lines of ``sale`` paid with a voucher whose session has not come back (a refund returns a line of
    one unit whole)."""
    return sale.lines.filter(
        voucher_session_id__isnull=False, refunds__isnull=True
    ).count()


def documents_pending(sale: Sale) -> bool:
    """A fiscal document of ``sale`` waits: its own, its void's or one of its refunds'."""
    return (
        FiscalStatus.PENDING in (sale.invoice_status, sale.void_invoice_status)
        or sale.refunds.filter(invoice_status=FiscalStatus.PENDING).exists()
    )


_TENDER_SEPARATOR = " + "


def tender_methods(sale: Sale) -> list[str]:
    """The methods ``sale`` was paid with, once each and in the order they were tendered, as the reader reads them;
    none when nothing was tendered."""
    names = dict.fromkeys(payment.method_name for payment in sale.payments.all())
    return [method_display_name(name) for name in names]


def tender_names(sale: Sale) -> str:
    """``tender_methods`` said in one line: «Cash + Card»."""
    return _TENDER_SEPARATOR.join(tender_methods(sale))


def sale_detail(sale: Sale, *, already: bool = False) -> dict:
    returned = returned_by_line(sale)
    return {
        "id": sale.id,
        "number": sale.number,
        "business_day": sale.business_day,
        "status": sale.status,
        "document_type": sale.document_type,
        "order_id": sale.order_id,
        "customer_id": sale.customer_id,
        "customer_name": sale.customer_name,
        "customer_tax_id": sale.customer_tax_id,
        "customer_address": sale.customer_address,
        "staff_id": sale.staff_id,
        "appointment_id": sale.appointment_id,
        "tax_included": sale.tax_included,
        "currency": sale.currency,
        "currency_decimals": currency_decimals(sale.currency),
        "subtotal": sale.subtotal,
        "tax_total": sale.tax_total,
        "discount_percent": sale.discount_percent,
        "discount_amount": sale.discount_amount,
        "gift_total": sale.gift_total,
        "total": sale.total,
        "tendered_total": sale.tendered_total,
        "change_total": sale.change_total,
        "refunded_total": sale.refunded_total,
        "refundable_total": sale.refundable_total,
        "sessions_to_return": sessions_to_return(sale)
        if sale.status == Sale.Status.COMPLETED
        else 0,
        "payment_method_name": tender_names(sale),
        "breakdown": sale.tax_breakdown,
        "notes": sale.notes,
        "voided_at": sale.voided_at,
        "voided_by": sale.voided_by,
        "void_reason": sale.void_reason,
        "invoice_status": sale.invoice_status,
        "invoice_id": sale.invoice_id,
        "invoice_number": sale.invoice_number,
        "invoice_type": sale.invoice_type,
        "receipt_code": paper_code(sale),
        "void_invoice_status": sale.void_invoice_status,
        "void_invoice_number": sale.void_invoice_number,
        "documents_pending": documents_pending(sale),
        "created_at": sale.created_at,
        "created_by": sale.created_by,
        "lines": [
            sale_line_row(line, returned.get(line.id, Decimal(0)))
            for line in sale.lines.order_by("position", "id")
        ],
        "payments": [
            {
                "id": payment.id,
                "position": payment.position,
                "method_id": payment.method_id,
                "method_name": method_display_name(payment.method_name),
                "method_type": payment.method_type,
                "amount": payment.amount,
                "tendered": payment.tendered,
                "change": payment.change,
                "reference": payment.reference,
                "extra": payment.extra,
                "extra_label": payment.extra_label,
            }
            for payment in sale.payments.order_by("position", "id")
        ],
        "already": already,
    }


@operation(
    "sale.sale.get",
    kind="query",
    permission="sale.view_sale",
    input=SaleRefIn,
    output=SaleOut,
    expose_api=True,
    ai=AI(
        description="Get a sale by its id or its number (e.g. 20261014-0007): header, lines with their VAT, tenders with "
        "tendered and change, the tax breakdown, what was refunded and, if voided, why.",
        asks={
            "en": (
                "show me sale 20261014-0007",
                "what was on the last ticket?",
                "how did they pay sale 12?",
            ),
            "es": (
                "enséñame la venta 20261014-0007",
                "¿qué llevaba el último ticket?",
                "¿cómo pagaron la venta 12?",
            ),
        },
    ),
)
def get_sale(ctx: OperationContext, params: SaleRefIn) -> dict:
    with translation.override(ctx.language):
        return sale_detail(visible_sale(ctx, params.sale_id, params.sale))


@operation(
    "sale.sale.by_idempotency_key",
    kind="query",
    permission="sale.view_sale",
    input=SaleByKeyIn,
    output=SaleByKeyOut,
    ai=AI(
        description="Find the sale recorded with a charge attempt's key: a charge whose answer was lost resolves to the "
        "very sale it created instead of a second one.",
        asks={
            "en": (
                "the card charge froze, did it go through?",
                "did that payment get recorded or should I charge again?",
            ),
            "es": (
                "se quedó colgado al cobrar, ¿entró el cobro?",
                "¿se llegó a guardar el pago o lo cobro otra vez?",
            ),
        },
    ),
)
def sale_by_key(ctx: OperationContext, params: SaleByKeyIn) -> dict:
    sale = SALES.visible(ctx).filter(idempotency_key=params.idempotency_key).first()
    with translation.override(ctx.language):
        return {"found": sale is not None, "sale": sale_detail(sale) if sale else None}


_SALE_SORT = {"number": ("business_day", "sequence"), "created_at": ("created_at",)}


def _tender_order() -> Coalesce:
    """What sorting by payment compares: the stored names of a sale's tenders, joined in the order they were tendered."""
    names = (
        SalePayment.objects.filter(sale=OuterRef("pk"))
        .order_by()
        .values("sale")
        .annotate(names=StringAgg("method_name", Value(_TENDER_SEPARATOR), order_by=("position", "id")))
        .values("names")
    )
    return Coalesce(Subquery(names), Value(""), output_field=TextField())


def _paid_with(method_name: str) -> Exists:
    """A sale that took at least one tender of this method, the largest or not."""
    return Exists(SalePayment.objects.filter(sale=OuterRef("pk"), method_name=method_name))


def sale_row(sale: Sale) -> dict:
    return {
        "id": sale.id,
        "number": sale.number,
        "business_day": sale.business_day,
        "created_at": sale.created_at,
        "status": sale.status,
        "document_type": sale.document_type,
        "customer_id": sale.customer_id,
        "customer_name": sale.customer_name,
        "payment_method_name": tender_names(sale),
        "payment_methods": tender_methods(sale),
        "staff_id": sale.staff_id,
        "currency": sale.currency,
        "currency_decimals": currency_decimals(sale.currency),
        "total": sale.total,
        "tax_total": sale.tax_total,
        "refunded_total": sale.refunded_total,
        "refundable_total": sale.refundable_total,
        "sessions_to_return": sale.voucher_lines_left
        if sale.status == Sale.Status.COMPLETED
        else 0,
        "has_refunds": sale.has_refunds,
        "invoice_status": sale.invoice_status,
        "documents_pending": FiscalStatus.PENDING in (sale.invoice_status, sale.void_invoice_status)
        or sale.refunds_pending,
    }


@operation(
    "sale.sale.list",
    kind="query",
    permission="sale.view_sale",
    input=SaleListIn,
    output=SalePage,
    expose_api=True,
    ai=AI(
        description="List the sales, newest first: search by number or customer; filter by status (completed, voided, "
        "refunded), payment method (any of its tenders), customer, professional, business days (inclusive) and total in cents.",
        asks={
            "en": (
                "show me yesterday's sales",
                "what did Ana López buy this month?",
                "find the card sales from Monday",
            ),
            "es": (
                "enséñame las ventas de ayer",
                "¿qué ha comprado Ana López este mes?",
                "busca las ventas pagadas con tarjeta",
            ),
        },
    ),
)
def list_sales(ctx: OperationContext, params: SaleListIn) -> dict:
    sales = SALES.visible(ctx).annotate(
        voucher_lines_left=Count(
            "lines",
            filter=Q(
                lines__voucher_session_id__isnull=False, lines__refunds__isnull=True
            ),
        ),
        has_refunds=Exists(Refund.objects.filter(sale=OuterRef("pk"))),
        refunds_pending=Exists(
            Refund.objects.filter(sale=OuterRef("pk"), invoice_status=FiscalStatus.PENDING)
        ),
    )
    if params.search:
        text = params.search.strip()
        sales = sales.filter(
            Q(number__icontains=text) | Q(customer_name__icontains=text)
        )
    if params.payment_method_name is not None:
        sales = sales.filter(_paid_with(params.payment_method_name))
    exact = {
        "status": params.status,
        "customer_id": params.customer_id,
        "staff_id": params.staff_id,
        "business_day__gte": params.date_from,
        "business_day__lte": params.date_to,
        "total__gte": params.total_min,
        "total__lte": params.total_max,
    }
    sales = sales.filter(
        **{key: value for key, value in exact.items() if value is not None}
    )
    if params.customer_name:
        sales = sales.filter(customer_name__icontains=params.customer_name.strip())
    if params.number:
        sales = sales.filter(number__icontains=params.number.strip())
    columns = (
        (_tender_order(),)
        if params.sort == "payment_method_name"
        else _SALE_SORT.get(params.sort, (params.sort,))
    )
    page = sales.order_by(*list_order(*columns, descending=params.dir == "desc")).prefetch_related("payments")[
        params.offset : params.offset + params.limit
    ]
    with translation.override(ctx.language):
        rows = [sale_row(sale) for sale in page]
    return {
        "rows": rows,
        "total": sales.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


def keeps_fiscal_documents() -> bool:
    """Whether this database holds its sales (``fiscal_documents_kept`` on this app's config), of any status: a draft counts
    too, for what it asks is whether a database can go, and that cannot be undone."""
    return Sale.objects.exists()
