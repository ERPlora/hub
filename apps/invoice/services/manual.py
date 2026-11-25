"""Manual invoices (INVOICE-F03): issued by hand, today or on an earlier day the series still takes, with the VAT
computed by the server and closed once per rate.
"""

import datetime as dt
from decimal import Decimal

from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import operation

from apps.invoice import assistant_cards, fiscal
from apps.invoice.models import Invoice, InvoiceSeries
from apps.invoice.queries.series import FULL
from apps.invoice.schemas.invoices import InvoiceCreateIn, InvoiceOut
from apps.invoice.services.issuer import _configured_issuer, _issuer_copy
from apps.invoice.services.issuing import GENERAL_REGIME, _issue, _line_values
from apps.invoice.services.numbering import SERIES_NOT_FOUND, series_of_year
from apps.invoice.services.recipient import _chosen_card, _recipient
from apps.invoice.services.writes import _detail, _today
from apps.sale.queries.business import TICKET_LIMIT, business_country, money_text
from apps.sale.queries.checkout import tax_category_name
from apps.tax.queries.calculation import round_half_up
from apps.tax.queries.jurisdiction import business_tax_kind
from apps.tax.queries.naming import resolve_category_text
from apps.tax.queries.resolution import resolve_tax
from base import operations as base_operations

SERIES_INACTIVE = _("This series is not active: activate it or choose another one.")


SERIES_NOT_ISSUABLE = _(
    "A manual invoice is numbered in an invoice (F1) or ticket (F2) series."
)


SERIES_OTHER_YEAR = _(
    "That series numbers another year: a manual invoice is numbered in a series of the year of its date."
)


ISSUE_DATE_IN_FUTURE = _("An invoice cannot be dated after today.")


ISSUE_DATE_BEFORE_LAST = _(
    "An invoice cannot be dated before the last one of its series, which is of %(date)s."
)


DUE_DATE_BEFORE_ISSUE = _("The due date cannot be before the invoice's date.")


TICKET_OVER_LIMIT = _(
    "Above %(limit)s a ticket cannot be issued: issue an invoice (F1) with the customer's details."
)


UNKNOWN_CATEGORY = _("There is no tax category «%(category)s».")


NO_TAX_RULE = _(
    "No tax rule applies that day to the tax category «%(category)s». Create its rule in Taxes › Rules."
)


LINE_UNDERFLOW = _(
    "Line %(line)s: %(quantity)s at that price comes to 0.00, so no invoice was issued."
)


DESCRIPTION_MAX_LENGTH = 500


def _manual_series(
    data: InvoiceCreateIn, year: int, ctx: OperationContext
) -> InvoiceSeries:
    if data.series_id is not None:
        series = InvoiceSeries.objects.filter(pk=data.series_id).first()
        if series is None:
            raise NotFound(str(SERIES_NOT_FOUND), code="invoice.series_not_found")
        if series.year != year:
            raise Conflict(
                str(SERIES_OTHER_YEAR),
                code="invoice.series_other_year",
                fields={"series_id": str(SERIES_OTHER_YEAR)},
            )
    elif data.series_code:
        series = series_of_year(data.series_code.strip().upper(), year, ctx)
    else:
        series = InvoiceSeries.objects.filter(
            year=year, is_default=True
        ).first() or series_of_year(FULL, year, ctx)
    if not series.is_active:
        raise Conflict(str(SERIES_INACTIVE), code="invoice.series_inactive")
    if series.invoice_type not in ("F1", "F2"):
        raise Conflict(str(SERIES_NOT_ISSUABLE), code="invoice.series_not_issuable")
    return series


def _issue_date(data: InvoiceCreateIn) -> dt.date:
    """The day the invoice is dated: today, or the earlier one chosen."""
    today = _today()
    issue_date = data.issue_date or today
    if issue_date > today:
        raise _refused_date("issue_date", "invoice.issue_date_in_future", str(ISSUE_DATE_IN_FUTURE))
    if data.due_date is not None and data.due_date < issue_date:
        raise _refused_date("due_date", "invoice.due_date_before_issue", str(DUE_DATE_BEFORE_ISSUE))
    return issue_date


def _refused_date(field: str, code: str, message: str) -> Conflict:
    return Conflict(message, code=code, fields={field: message})


def _follows_the_last(series: InvoiceSeries, issue_date: dt.date) -> None:
    """The dates of a series go in the order of its numbers (RD 1619/2012 art. 6.1.a). Its row stays locked until the
    number is taken, so an invoice being issued meanwhile counts."""
    InvoiceSeries.objects.select_for_update().get(pk=series.pk)
    last = series.invoices.order_by("-sequence").values_list("issue_date", flat=True).first()
    if last is not None and issue_date < last:
        message = str(ISSUE_DATE_BEFORE_LAST) % {"date": date_format(last, "SHORT_DATE_FORMAT")}
        raise _refused_date("issue_date", "invoice.issue_date_before_last", message)


def _rule_key(category_key: str, *, field: str, on: dt.date) -> fiscal.FiscalKey:
    resolution = resolve_tax(category_key=category_key, on=on)
    if resolution is None:
        message = str(NO_TAX_RULE) % {"category": tax_category_name(category_key)}
        raise Conflict(message, code="invoice.no_tax_rule", fields={field: message})
    return fiscal.FiscalKey(
        tax=resolution.tax_kind,
        regime=resolution.regime_key,
        cls=resolution.operation_class,
        exempt_reason=resolution.exempt_reason,
        rate=resolution.root.rate_pct,
        surcharge_rate=sum(
            (rule.rate_pct for rule in resolution.components[1:]), Decimal(0)
        ),
    )


@operation(
    "invoice.invoice.create",
    kind="command",
    permission="invoice.add_invoice",
    input=InvoiceCreateIn,
    output=InvoiceOut,
    ai={
        "asks": {
            "en": (
                "make an invoice for Carpintería Lema for two hours of work at 50 €",
                "issue an invoice by hand to Fontanería Ortega",
                "make an invoice for Carpintería Lema dated yesterday, due in 30 days",
            ),
            "es": (
                "hazle una factura a Carpintería Lema por dos horas de trabajo a 50 €",
                "emite a mano una factura para Fontanería Ortega",
                "hazle una factura a Carpintería Lema con fecha de ayer y vencimiento a 30 días",
            ),
        },
        "description": "Issue an invoice by hand, numbered in its series (an invoice F1 needs the "
        "customer's name, tax ID and address; a ticket series issues a simplified F2). It is dated today unless "
        "issue_date says an earlier day, and it has no due date unless due_date says one. Each line: description, "
        "quantity, unit price WITHOUT VAT in cents, and its VAT % or its tax category. The server computes the VAT, "
        "closed once per rate. An issued invoice is never edited: it is corrected with a rectifying invoice.",
        "risk": "high",
        "summary": assistant_cards.lines,
    },
)
def create(ctx: OperationContext, data: InvoiceCreateIn) -> dict:
    card = _chosen_card(ctx, data)
    issuer = _configured_issuer()
    issue_date = _issue_date(data)
    series = _manual_series(data, issue_date.year, ctx)
    _follows_the_last(series, issue_date)
    recipient = _recipient(ctx, data, full=series.invoice_type == "F1", card=card)
    lines, values = [], []
    # A rate typed without a category is of the business's territory (TAX-F11): IGIC in the Canary Islands.
    typed_kind = business_tax_kind()
    for index, item in enumerate(data.lines):
        category = ""
        if item.tax_category_key:
            field = f"lines.{index}.tax_category_key"
            category, _matched = resolve_category_text(item.tax_category_key)
            if category is None:
                message = str(UNKNOWN_CATEGORY) % {"category": item.tax_category_key}
                raise InvalidPayload(
                    message,
                    code="invoice.unknown_tax_category",
                    fields={field: message},
                )
            key = _rule_key(category, field=field, on=issue_date)
        else:
            key = fiscal.FiscalKey(
                tax=typed_kind,
                regime=GENERAL_REGIME,
                cls="subject",
                exempt_reason="",
                rate=item.tax_rate,
            )
        base = round_half_up(item.quantity * item.unit_price)
        if item.unit_price > 0 and base == 0:
            message = str(LINE_UNDERFLOW) % {
                "line": index + 1,
                "quantity": item.quantity,
            }
            raise Conflict(
                message,
                code="invoice.line_amount_underflow",
                fields={f"lines.{index}.quantity": message},
            )
        lines.append(
            fiscal.Line(key=key, base=base, tax=0, total=base, category=category)
        )
        values.append(
            {
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": Decimal(item.unit_price),
                "tax_category_key": category,
                "product_id": item.product_id,
            }
        )
    closed = fiscal.close_manual(lines)
    _within_ticket_limit(series, closed.total)
    invoice = _issue(
        ctx,
        series=series,
        invoice_type=series.invoice_type,
        entries=closed.entries,
        lines=[
            _line_values(line, **extra)
            for line, extra in zip(closed.lines, values, strict=True)
        ],
        tolerance=closed.tolerance,
        recipient=recipient,
        issuer=_issuer_copy(issuer),
        issue_date=issue_date,
        operation_date=issue_date,
        due_date=data.due_date,
        source_type=Invoice.Source.MANUAL,
        currency=base_operations.business_currency(ctx.scope),
        notes=data.notes,
        description=_operation_text(item.description for item in data.lines),
    )
    return _detail(ctx, invoice)


def _operation_text(parts) -> str:
    """VeriFactu's DescripcionOperacion of a manual invoice: its concepts, at most 500 characters."""
    return ", ".join(parts)[:DESCRIPTION_MAX_LENGTH]


def _within_ticket_limit(series: InvoiceSeries, total: int) -> None:
    """A ticket (F2) up to the till's own limit (RD 1619/2012 art. 4; Sales' ``TICKET_LIMIT``)."""
    limit = TICKET_LIMIT.get(business_country())
    if series.invoice_type == "F2" and limit is not None and total > limit:
        raise Conflict(
            str(TICKET_OVER_LIMIT) % {"limit": money_text(limit)},
            code="invoice.ticket_over_limit",
        )
