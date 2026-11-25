"""Read operations of Online orders (``READ ONLY``): the tables with the code each one's QR carries, and the row of a
table and its code that a regeneration answers with too.

The tables are Tables' own, read by its operations' names (``base.operations.call``) with the permission of whoever
asks: whoever may not see the tables does not see their codes either.
"""

from live.context import OperationContext
from live.operations import operation

from apps.online_order.models import TableCode
from apps.online_order.schemas import TableCodeListIn, TableCodePage
from base.operations import call
from base.qr import public_url


def page_url(ctx: OperationContext, code: str) -> str:
    """The address of the table's page that ``code`` opens: ``/p/<slug>/order/<code>`` on the hub's public address."""
    slug = ctx.scope.key
    return f"{public_url(slug, ctx.request)}p/{slug}/order/{code}"


def code_row(ctx: OperationContext, table, code: TableCode | None) -> dict:
    """A table as Tables answers it, with its code (or none yet)."""
    return {
        "table_id": table.id,
        "table": table.label,
        "number": table.number,
        "zone_name": table.zone_name,
        "code": code.code if code else None,
        "url": page_url(ctx, code.code) if code else None,
        "issued_at": code.issued_at if code else None,
    }


@operation(
    "online_order.qr_code.list",
    kind="query",
    permission="online_order.view_qr_code",
    input=TableCodeListIn,
    output=TableCodePage,
    expose_api=True,
    ai={
        "description": "Lists the tables in the floor plan's order (2 before 10), each with its zone and, once its "
        "QR has been generated, the code its QR carries, the address of the table's ordering page and when the code "
        "was generated; a table without a code has none yet. A page at a time.",
        "asks": {
            "en": (
                "which tables already have their ordering QR code?",
                "give me the address of the QR code of each table",
            ),
            "es": (
                "¿qué mesas tienen ya su código QR para pedir?",
                "dame la dirección del código QR de cada mesa",
            ),
        },
    },
)
def list_qr_codes(ctx: OperationContext, params: TableCodeListIn) -> dict:
    tables = call(ctx, "table.table.list", {"limit": params.limit, "offset": params.offset})
    codes = TableCode.objects.in_bulk([table.id for table in tables.rows], field_name="table_id")
    return {
        "rows": [code_row(ctx, table, codes.get(table.id)) for table in tables.rows],
        "total": tables.total,
        "limit": params.limit,
        "offset": params.offset,
    }
