"""Write operations of Online orders: one operation = one transaction, with its event in the outbox."""

import secrets

from django.utils import timezone
from live.context import OperationContext
from live.operations import operation
from live.outbox import record_event

from apps.online_order import events
from apps.online_order.models import TableCode
from apps.online_order.queries import code_row
from apps.online_order.schemas import TableCodeOut
from apps.table.schemas import TableRefIn
from base.operations import call

#: Bytes of randomness in a table's code: 128 bits, 22 characters in the URL.
CODE_BYTES = 16


@operation(
    "online_order.qr_code.regenerate",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="online_order.change_qr_code",
    input=TableRefIn,
    output=TableCodeOut,
    expose_api=True,
    ai={
        "description": "Gives a table, by its id or its number (with its zone if the number repeats), a new code for "
        "its ordering QR: the QR printed before stops working at once and the new one has to be printed. A table "
        "without a code gets its first one. It cannot be undone.",
        "risk": "high",
        "asks": {
            "en": (
                "regenerate the QR code of table 4 on the terrace",
                "someone took a photo of table 7's QR code, give it a new one",
            ),
            "es": (
                "regenera el código QR de la mesa 4 de la terraza",
                "alguien se ha llevado una foto del código QR de la mesa 7, genera otro",
            ),
        },
    },
)
def regenerate_qr_code(ctx: OperationContext, data: TableRefIn) -> dict:
    """One upsert on the table's row: two regenerations at once of a table without a code never collide."""
    table = call(ctx, "table.table.get", data.model_dump(exclude_none=True))
    code = TableCode(table_id=table.id, code=secrets.token_urlsafe(CODE_BYTES), issued_at=timezone.now())
    TableCode.objects.bulk_create(
        [code], update_conflicts=True, unique_fields=["table_id"], update_fields=["code", "issued_at"]
    )
    record_event(ctx, events.QR_CODE_REGENERATED, {"table_id": str(table.id)})
    return code_row(ctx, table, code)
