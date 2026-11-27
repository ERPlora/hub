"""The people who have opened checks of the room (``table.waiter.list``): the waiter filter of the list of checks."""

from django.db.models import Max
from django.db.models.functions import Lower
from live.context import OperationContext
from live.operations import operation

from apps.table.models import TableSession
from base.text_search import contains_text
from .paging import _page
from apps.table.schemas.waiters import WaiterListIn, WaiterPage


@operation(
    "table.waiter.list",
    kind="query",
    permission="table.view_session",
    input=WaiterListIn,
    output=WaiterPage,
    ai={
        "description": "List the people who have opened checks of the room (the waiter filter), by name.",
        "asks": {
            "en": (
                "which waiters have opened table checks?",
                "which waiters have been serving tables today?",
            ),
            "es": (
                "¿qué camareros han abierto cuentas de mesa?",
                "dime los camareros que han llevado mesas",
            ),
        },
    },
)
def list_waiters(ctx: OperationContext, params: WaiterListIn) -> dict:
    rows = (
        TableSession.objects.filter(is_deleted=False)
        .exclude(waiter_id="")
        .values("waiter_id")
        .annotate(name=Max("waiter_name"))
    )
    if params.search and params.search.strip():
        rows = rows.filter(contains_text(params.search.strip(), "name"))
    rows = rows.order_by(Lower("name"), "waiter_id")
    return _page(
        rows,
        params,
        lambda items: [
            {"id": item["waiter_id"], "name": item["name"] or item["waiter_id"]}
            for item in items
        ],
    )
