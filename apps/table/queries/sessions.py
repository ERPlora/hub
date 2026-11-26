"""The checks of the room (``table.session.*``), each with its status as Sales leaves it: an open or parked check whose
check of Sales ended reads closed. And the lines of a table's check, and whether a check of Sales is still open.
"""

import datetime as dt
from uuid import UUID

from django.db.models import (
    Case,
    CharField,
    DateTimeField,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.sale.models import Order, OrderLine, Sale
from apps.table.models import TableSession
from .floor import ENDED, _customers, table_label
from .lookups import find_session
from .paging import _page
from apps.table.schemas.sessions import (
    ByOrderIn,
    LineOut,
    LineRefIn,
    SessionListIn,
    SessionOut,
    SessionPage,
    SessionRefIn,
    SessionsOut,
)
from base.business import business_zone, currency_decimals
from base.ordering import list_order_for

LINE_NOT_FOUND = _("That line is not on the check of any table.")

SESSION_ORDER = {
    "opened_at": ("opened_at",),
    "closed_at": ("closed_now",),
    "table_number": ("table__number",),
    "zone_name": ("table__zone__name",),
    "guests_count": ("guests_count",),
    "paid_total": ("paid_total",),
    "status": ("status_now",),
}
#: The checks still alive (seated or parked): Sales ending their check ends them.
LIVE_STATUSES = [TableSession.Status.OPEN, TableSession.Status.PARKED]


def check_label(session: TableSession) -> str:
    """Where a check is: its table with its zone («5 (Terrace)»), or parked."""
    return table_label(session.table) if session.table_id else str(TableSession.Status.PARKED.label)


def order_is_open(order_id: UUID | None) -> bool:
    return (
        order_id is not None
        and Order.objects.filter(pk=order_id, status=Order.Status.OPEN).exists()
    )


def sessions_now():
    """The checks of the room (never the deleted ones), each with its status as Sales leaves it: an open
    or parked check whose check of Sales ended reads closed, at the hour Sales closed it; and what it charged,
    in the currency its sales were charged in (the business's then: its country does not change once it sells)."""
    order = Order.objects.filter(pk=OuterRef("order_id"))
    charges = Sale.objects.filter(order_id=OuterRef("order_id")).exclude(
        status=Sale.Status.VOIDED
    )
    paid = (
        charges.order_by()
        .values("order_id")
        .annotate(total=Sum("total"))
        .values("total")[:1]
    )
    return (
        TableSession.objects.filter(is_deleted=False)
        .select_related("table", "table__zone")
        .annotate(
            order_state=Subquery(order.values("status")[:1], output_field=CharField()),
            order_closed_at=Subquery(
                order.values("closed_at")[:1], output_field=DateTimeField()
            ),
            paid_total=Subquery(paid, output_field=IntegerField()),
            paid_currency=Subquery(
                charges.order_by("pk").values("currency")[:1],
                output_field=CharField(),
            ),
        )
        .annotate(
            status_now=Case(
                When(
                    Q(status__in=LIVE_STATUSES, order_state__in=ENDED),
                    then=Value("closed"),
                ),
                default=F("status"),
                output_field=CharField(),
            ),
            closed_now=Case(
                When(
                    Q(status__in=LIVE_STATUSES, order_state__in=ENDED),
                    then=F("order_closed_at"),
                ),
                default=F("closed_at"),
                output_field=DateTimeField(),
            ),
        )
    )


def session_rows(sessions: list[TableSession]) -> list[dict]:
    customers = _customers([s.order_id for s in sessions])
    out = []
    for session in sessions:
        table = session.table
        customer_id, customer_name = customers.get(session.order_id, (None, None))
        out.append(
            {
                "id": session.pk,
                "table_id": session.table_id,
                "table_number": table.number if table else None,
                "label": check_label(session),
                "zone_id": table.zone_id if table else None,
                "zone_name": table.zone.name if table and table.zone_id else None,
                "order_id": session.order_id,
                "guests_count": session.guests_count,
                "status": session.status_now,
                "waiter_id": session.waiter_id,
                "waiter_name": session.waiter_name,
                "opened_at": session.opened_at,
                "closed_at": session.closed_now,
                "notes": session.notes,
                "split_from_id": session.split_from_id,
                "transferred_from_id": session.transferred_from_id,
                "merged_into_id": session.merged_into_id,
                "paid_total": session.paid_total,
                "currency": session.paid_currency,
                "currency_decimals": (
                    currency_decimals(session.paid_currency)
                    if session.paid_currency
                    else None
                ),
                "customer_id": customer_id,
                "customer_name": customer_name,
            }
        )
    return out


def session_out(session: TableSession) -> dict:
    """One check as ``table.session.list`` paints it, read again now (also after a write)."""
    return session_rows([sessions_now().get(pk=session.pk)])[0]


@operation(
    "table.session.list",
    kind="query",
    permission="table.view_session",
    input=SessionListIn,
    output=SessionPage,
    expose_api=True,
    ai={
        "description": "List the checks of the room (open, closed, transferred, merged, parked), newest first, with "
        "their table, zone, waiter, guests, times and what their check of Sales charged.",
        "asks": {
            "en": (
                "which table checks are still open?",
                "show me today's closed table checks",
                "show me the history of table checks",
            ),
            "es": (
                "¿qué cuentas de mesa siguen abiertas?",
                "enséñame las cuentas de mesa cerradas hoy",
                "enséñame el historial de cuentas de mesa",
            ),
        },
    },
)
def list_sessions(ctx: OperationContext, params: SessionListIn) -> dict:
    rows = sessions_now()
    for text in (params.search, params.table_number):
        if text and text.strip():
            rows = rows.filter(table__number__icontains=text.strip())
    if params.status:
        rows = rows.filter(status_now=params.status)
    if params.zone_id:
        rows = rows.filter(table__zone_id=params.zone_id)
    if params.waiter_id:
        rows = rows.filter(waiter_id=params.waiter_id)
    if params.table_id:
        rows = rows.filter(table_id=params.table_id)
    zone = business_zone()
    if params.opened_from:
        rows = rows.filter(
            opened_at__gte=dt.datetime.combine(
                params.opened_from, dt.time.min, tzinfo=zone
            )
        )
    if params.opened_to:
        until = dt.datetime.combine(
            params.opened_to + dt.timedelta(days=1), dt.time.min, tzinfo=zone
        )
        rows = rows.filter(opened_at__lt=until)
    ordered = rows.order_by(*list_order_for(params.sort, columns=SESSION_ORDER, nulls_last=True))
    return _page(ordered, params, session_rows)


@operation(
    "table.session.get",
    kind="query",
    permission="table.view_session",
    input=SessionRefIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Get one table check by its id, or the open check of a table by its number («table 4»), with "
        "its check of Sales, guests, waiter, customer and what it charged.",
        "asks": {
            "en": (
                "how many guests are on table 4's check?",
                "since when has table 5's check been open?",
            ),
            "es": (
                "¿cuántos comensales tiene la cuenta de la mesa 4?",
                "¿desde cuándo está abierta la cuenta de la mesa 5?",
            ),
        },
    },
)
def get_session(ctx: OperationContext, params: SessionRefIn) -> dict:
    return session_rows(
        [find_session(params.id, params.table, params.zone, rows=sessions_now())]
    )[0]


@operation(
    "table.session.by_order",
    kind="query",
    permission="table.view_session",
    input=ByOrderIn,
    output=SessionsOut,
    expose_api=True,
    ai={
        "description": "Find the table of a check of Sales: the table checks that hold it, newest first.",
        "asks": {
            "en": (
                "which table is this check at?",
                "what table is Ana's check sitting at?",
            ),
            "es": (
                "¿en qué mesa está esta cuenta?",
                "¿a qué mesa pertenece la cuenta de Ana?",
            ),
        },
    },
)
def sessions_by_order(ctx: OperationContext, params: ByOrderIn) -> dict:
    rows = (
        sessions_now()
        .filter(order_id=params.order_id)
        .order_by("-opened_at", "-id")[:100]
    )
    return {"rows": session_rows(list(rows))}


@operation(
    "table.session.line",
    kind="query",
    permission="table.view_session",
    input=LineRefIn,
    output=LineOut,
    expose_api=True,
    ai={
        "description": "Get one line of the check of Sales of a table check by its id: its name and quantity, as "
        "«Split check» lists it.",
        "asks": {
            "en": (
                "what is that line on the table's check?",
                "show me that line of table 4's check",
            ),
            "es": (
                "¿qué es esa línea de la cuenta de la mesa?",
                "¿cuántas unidades lleva esa línea de la mesa?",
            ),
        },
    },
)
def get_line(ctx: OperationContext, params: LineRefIn) -> dict:
    held = TableSession.objects.filter(is_deleted=False, order_id__isnull=False).values("order_id")
    line = OrderLine.objects.live().filter(pk=params.id, order_id__in=held).first()
    if line is None:
        raise NotFound(str(LINE_NOT_FOUND), code="table.line_not_found")
    return {"id": line.id, "name": line.name, "quantity": line.quantity, "unit": line.unit}
