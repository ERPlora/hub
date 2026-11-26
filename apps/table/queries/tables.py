"""The tables of the room (``table.table.list``, ``table.table.get``) in natural order (2 before 10), and whether a new
check may sit at one.
"""

import datetime as dt

from django.db.models import CharField, F, Func, Q, Value
from django.db.models.functions import Lower
from django.utils import timezone
from live.context import OperationContext
from live.operations import operation

from apps.table.models import Table
from .floor import live_sessions, table_rows, tables_now
from .lookups import find_table, find_zone
from .paging import _page
from apps.table.schemas.tables import TableListIn, TableRefIn
from apps.table.schemas.floor import TableOut, TablePage
from base.ordering import list_order_for

#: Width every run of digits of a table number is padded to, to sort numbers as numbers.
NATURAL_PAD = 12

TABLE_ORDER = {
    "number": ("number_sort", "number_lower"),
    "name": ("name",),
    "zone_name": ("zone__name",),
    "capacity": ("capacity",),
    "status": ("status_now",),
}


def natural_key(expression) -> Func:
    """``number`` with every run of digits left-padded to 12, so text order is natural order.

    ``Barra 2 Bis`` → ``Barra 000000000002 Bis``."""
    padded = Func(
        expression,
        Value("([0-9]+)"),
        Value("0" * NATURAL_PAD + r"\1"),
        Value("g"),
        function="regexp_replace",
        output_field=CharField(),
    )
    return Func(
        padded,
        Value("0*([0-9]{%d})" % NATURAL_PAD),
        Value(r"\1"),
        Value("g"),
        function="regexp_replace",
        output_field=CharField(),
    )


def seatable(table: Table, now: dt.datetime, *, occupied_ok: bool = False) -> bool:
    """Whether a new check may sit at ``table`` now: in service, not blocked and, unless a split
    asks for it, without a live check."""
    if table.is_deleted or not table.is_active or table.blocked:
        return False
    if table.zone_id is not None and (
        table.zone.is_deleted or not table.zone.is_active
    ):
        return False
    return occupied_ok or not live_sessions().filter(table=table).exists()


@operation(
    "table.table.list",
    kind="query",
    permission="table.view_table",
    input=TableListIn,
    output=TablePage,
    expose_api=True,
    ai={
        "description": "List the tables of the room in natural order (2 before 10), each with its status right now "
        "(available, occupied, reserved, blocked), its guests and since when, who serves it, its customer, what it has "
        "run up, whether it asked for the bill and its next reservation of today. Filter by zone, status or number.",
        "asks": {
            "en": (
                "which tables are free right now?",
                "what tables are occupied?",
                "show me all the tables and how they are",
            ),
            "es": (
                "¿qué mesas están libres ahora?",
                "¿qué mesas tengo ocupadas?",
                "enséñame cómo están todas las mesas",
            ),
        },
    },
)
def list_tables(ctx: OperationContext, params: TableListIn) -> dict:  # noqa: C901
    now = timezone.now()
    rows = (
        tables_now(now)
        .select_related("zone")
        .annotate(
            number_sort=Lower(natural_key(F("number"))), number_lower=Lower("number")
        )
    )
    if params.search and params.search.strip():
        text = params.search.strip()
        rows = rows.filter(Q(number__icontains=text) | Q(name__icontains=text))
    if params.number:
        rows = rows.filter(number__icontains=params.number.strip())
    if params.name:
        rows = rows.filter(name__icontains=params.name.strip())
    if params.zone_id:
        rows = rows.filter(zone_id=params.zone_id)
    if params.zone:
        rows = rows.filter(zone=find_zone(None, params.zone))
    if params.status:
        rows = rows.filter(status_now=params.status)
    if params.shape:
        rows = rows.filter(shape=params.shape)
    if params.is_active is not None:
        rows = rows.filter(is_active=params.is_active)
    if params.in_service is not None:
        rows = rows.filter(serving=params.in_service)
    if params.capacity_min is not None:
        rows = rows.filter(capacity__gte=params.capacity_min)
    if params.capacity_max is not None:
        rows = rows.filter(capacity__lte=params.capacity_max)
    return _page(
        rows.order_by(*list_order_for(params.sort, columns=TABLE_ORDER, nulls_last=True)),
        params,
        lambda items: table_rows(items, now),
    )


@operation(
    "table.table.get",
    kind="query",
    permission="table.view_table",
    input=TableRefIn,
    output=TableOut,
    expose_api=True,
    ai={
        "description": "Get one table by its id or its number («table 4», with its zone if the number repeats): its "
        "status right now, its open checks (two after a split), guests, waiter, customer and next reservation.",
        "asks": {
            "en": (
                "how's table 4 doing?",
                "is table 7 on the terrace free?",
                "who's serving table 2?",
            ),
            "es": (
                "¿cómo está la mesa 4?",
                "¿está libre la 7 de la terraza?",
                "¿quién atiende la mesa 2?",
            ),
        },
    },
)
def get_table(ctx: OperationContext, params: TableRefIn) -> dict:
    now = timezone.now()
    shown = tables_now(now).select_related("zone")
    return table_rows([find_table(params.id, params.table, params.zone, rows=shown)], now)[0]
