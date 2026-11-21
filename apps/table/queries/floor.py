"""The live floor: whether each table is occupied, blocked, reserved or available right now, and its row as
the plan paints it (``table.table.list``, ``table.table.get`` and the writes that answer with a table)."""

import datetime as dt
from collections import defaultdict

from django.db.models import (
    BooleanField,
    Case,
    CharField,
    Exists,
    ExpressionWrapper,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.customer.models import OrderLink
from apps.sale.models import Order
from apps.table.models import Hold, Table, TableSession
from base.business import business_zone

#: A reservation paints its table Reserved this long before it starts (WORKBOOK «Referencia adoptada»).
RESERVED_LEAD = dt.timedelta(minutes=60)
TABLE_LABEL = _("%(number)s (%(zone)s)")
NO_ZONE = _("no zone")
ENDED = [Order.Status.COMPLETED, Order.Status.VOIDED]


# --- The business's clock ------------------------------------------------------------------------


def end_of_today(now: dt.datetime) -> dt.datetime:
    """Midnight at the end of the business's today."""
    local = timezone.localtime(now, business_zone())
    tomorrow = local.date() + dt.timedelta(days=1)
    return dt.datetime.combine(tomorrow, dt.time.min, tzinfo=business_zone())


# --- Shared with services.py, inside the command's own transaction --------------------------------



def ended_orders():
    """The checks of Sales that are no longer open (charged in full, or voided)."""
    return Order.objects.filter(status__in=ENDED).values("pk")


def live_sessions():
    """The checks seated right now: open, not deleted, and whose check of Sales (if any) is still open."""
    return TableSession.objects.filter(
        status=TableSession.Status.OPEN, is_deleted=False
    ).exclude(order_id__in=ended_orders())


def reserving_holds(now: dt.datetime):
    """The live holds already within their window: they paint their table Reserved."""
    return Hold.objects.filter(
        status=Hold.Status.HELD, held_until__gt=now, held_from__lte=now + RESERVED_LEAD
    )


def tables_now(now: dt.datetime):
    """The tables in use or not (never the deleted ones), each with its status right now."""
    return Table.objects.filter(is_deleted=False).annotate(
        occupied=Exists(live_sessions().filter(table=OuterRef("pk"))),
        reserving=Exists(reserving_holds(now).filter(table=OuterRef("pk"))),
        status_now=Case(
            When(occupied=True, then=Value("occupied")),
            When(blocked=True, then=Value("blocked")),
            When(reserving=True, then=Value("reserved")),
            default=Value("available"),
            output_field=CharField(),
        ),
        serving=ExpressionWrapper(
            Q(is_active=True) & (Q(zone__isnull=True) | Q(zone__is_active=True)),
            output_field=BooleanField(),
        ),
    )


def _bill():
    """What is left to charge on a check of Sales, the figure Open checks shows, read with the check itself."""
    return Subquery(Order.objects.filter(pk=OuterRef("order_id")).values("provisional_total")[:1])


def _bill_requested():
    """Whether the bill of a check of Sales was printed for the table, read with the check itself."""
    return Exists(Order.objects.filter(pk=OuterRef("order_id"), bill_printed_at__isnull=False))


def table_label(table: Table) -> str:
    return str(TABLE_LABEL) % {
        "number": table.number,
        "zone": table.zone.name if table.zone_id else NO_ZONE,
    }


def _customers(order_ids) -> dict:
    """``order_id`` → ``(customer_id, name)`` of the live cards linked to those checks of Sales."""
    links = OrderLink.objects.filter(
        order_id__in=[o for o in order_ids if o], customer__deleted_at__isnull=True
    )
    return {
        link.order_id: (link.customer_id, link.customer.name)
        for link in links.select_related("customer")
    }


# --- Rows ----------------------------------------------------------------------------------------



def table_rows(tables: list[Table], now: dt.datetime) -> list[dict]:
    """The rows of ``tables`` (annotated by ``tables_now``) with their live checks and their next hold."""
    ids = [table.pk for table in tables]
    checks = defaultdict(list)
    seated_now = live_sessions().filter(table_id__in=ids).annotate(bill=_bill(), bill_requested=_bill_requested())
    for session in seated_now.order_by("opened_at", "id"):
        checks[session.table_id].append(session)
    customers = _customers([s.order_id for group in checks.values() for s in group])
    holds = {}
    shown = Hold.objects.filter(
        table_id__in=ids,
        status=Hold.Status.HELD,
        held_until__gt=now,
        held_from__lt=end_of_today(now),
    )
    for hold in shown.order_by("held_from", "id"):
        holds.setdefault(hold.table_id, hold)
    out = []
    for table in tables:
        seated = checks.get(table.pk, [])
        hold = holds.get(table.pk)
        out.append(
            {
                "id": table.pk,
                "number": table.number,
                "label": table_label(table),
                "name": table.name,
                "capacity": table.capacity,
                "shape": table.shape,
                "status": table.status_now,
                "blocked": table.blocked,
                "is_active": table.is_active,
                "zone_id": table.zone_id,
                "zone_name": table.zone.name if table.zone_id else None,
                "in_service": table.serving,
                "position_x": table.position_x,
                "position_y": table.position_y,
                "width": table.width,
                "height": table.height,
                **_seated_row(seated, customers),
                "hold": _hold_row(hold, now) if hold else None,
            }
        )
    return out


def _seated_row(seated: list[TableSession], customers: dict) -> dict:
    """What a table's live checks paint: its guests, since when, who serves it, the checks, the bill and whether it
    was asked for."""
    if not seated:
        return {"guests": None, "since": None, "waiter_name": "", "checks": [], "amount": None, "bill_requested": False}
    return {
        "guests": sum(s.guests_count for s in seated),
        "since": seated[0].opened_at,
        "waiter_name": seated[0].waiter_name,
        "checks": [_check_row(s, customers) for s in seated],
        "amount": sum(s.bill or 0 for s in seated),
        "bill_requested": any(s.bill_requested for s in seated),
    }


def _check_row(session: TableSession, customers: dict) -> dict:
    customer_id, customer_name = customers.get(session.order_id, (None, None))
    return {
        "id": session.pk,
        "order_id": session.order_id,
        "guests_count": session.guests_count,
        "opened_at": session.opened_at,
        "waiter_name": session.waiter_name,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "split_from_id": session.split_from_id,
    }


def _hold_row(hold: Hold, now: dt.datetime) -> dict:
    return {
        "label": hold.label,
        "erased": not hold.label and hold.customer_id is not None,
        "held_from": hold.held_from,
        "held_until": hold.held_until,
        "party_size": hold.party_size,
        "reserving": hold.held_from - RESERVED_LEAD <= now,
    }


def table_out(table: Table) -> dict:
    """One table as ``table.table.list`` paints it, read again now (also after a write)."""
    now = timezone.now()
    row = tables_now(now).select_related("zone").get(pk=table.pk)
    return table_rows([row], now)[0]
