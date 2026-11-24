"""How a row of Services says the sale it names: by the number Sales names it by, from Sales' read of that sale as the
caller reads it. Services does not require Sales and copies nothing of it."""

from uuid import UUID

from live.context import OperationContext
from live.errors import AppInactive, NotFound, PermissionDenied
from live.operations import UnknownOperation

from apps.service.queries.records import SALE_GET
from base.operations import call


def _readable_sale(ctx: OperationContext, sale_id: UUID):
    """``None`` when the caller cannot read the sale: Sales off or absent, no permission to see sales, or a sale not
    theirs to see, which Sales answers as one that does not exist."""
    try:
        return call(ctx, SALE_GET, {"sale_id": str(sale_id)})
    except (UnknownOperation, AppInactive, PermissionDenied, NotFound):
        return None


def name_the_sales(ctx: OperationContext, rows: list[dict]) -> dict:
    """Sets each row's ``sale_number`` from its ``sale_id`` (``None`` when it names no sale or the caller cannot read
    it), reading each sale once. Returns what was read of each sale, by its id, for whatever else a row says of it."""
    sales = {sale_id: _readable_sale(ctx, sale_id) for sale_id in {row["sale_id"] for row in rows} - {None}}
    for row in rows:
        sale = sales.get(row["sale_id"])
        row["sale_number"] = sale.number if sale else None
    return sales
