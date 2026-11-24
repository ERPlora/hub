"""The cards as a CSV file (CUSTOMER-F09): every card the list's search and filters find, not a page."""

import csv
import io
from decimal import Decimal

from live.context import OperationContext
from live.operations import AI, operation

from apps.customer.queries.cards import _customers
from apps.customer.schemas.exports import CustomerExportIn, ExportOut, CustomerExportRow
from base import operations as platform
from base.business import currency_decimals
from base.exports import visible_columns

#: What a spreadsheet runs as a formula when a cell starts with it (OWASP «CSV injection»).
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _cell(value) -> str:
    """One CSV cell as text, with an apostrophe in front of what a spreadsheet would run."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = value.isoformat() if hasattr(value, "isoformat") else str(value)
    return f"'{text}" if text.startswith(FORMULA_STARTS) else text


@operation(
    "customer.customer.export",
    kind="query",
    permission="customer.export",
    input=CustomerExportIn,
    output=ExportOut,
    ai=AI(
        "Exports every customer that matches the search and filters as a CSV file, with contact details, stage, "
        "figures, groups and tags. It hands out personal data.",
        risk="high",
        asks={
            "en": ("download a CSV of every customer", "give me a file with all my customers"),
            "es": ("descárgame los clientes en un CSV", "exporta las clientas a un fichero"),
        },
    ),
)
def export_customers(ctx: OperationContext, params: CustomerExportIn) -> dict:
    cards = _customers(ctx, params).prefetch_related("groups", "tags")
    columns = visible_columns(ctx, CustomerExportRow)
    # «Spent» with the decimals of the business's currency (its country's: 0 in JPY), never two fixed.
    decimals = currency_decimals(platform.business_currency(ctx.scope))
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    count = 0
    for customer in cards:
        values = {
            **{column: getattr(customer, column, None) for column in columns},
            "total_spent": f"{Decimal(customer.total_spent).scaleb(-decimals):.{decimals}f}",
            "groups": "; ".join(sorted(group.name for group in customer.groups.all())),
            "tags": "; ".join(sorted(tag.name for tag in customer.tags.all())),
        }
        writer.writerow([_cell(values[column]) for column in columns])
        count += 1
    return {
        "filename": "customers.csv",
        "content_type": "text/csv",
        "rows": count,
        "csv": buffer.getvalue(),
    }
