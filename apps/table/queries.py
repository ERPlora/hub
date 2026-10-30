"""Read operations of the table app (``READ ONLY``): the zones, the live floor, the checks of the room,
the waiters, the setup status and the settings.

A table's status is computed here, never stored: **occupied** when it has a live check (open, with its
check of Sales still open or without one), else **blocked** when it is out of service, else
**reserved** when a live hold is already within its window (from ``RESERVED_LEAD`` before it starts
until it ends), else **available**. Phase 1 has no relay of events: a check of Sales charged in full
or voided is read here, so the plan and the list of checks are right on every read (WORKBOOK «Para
quien lo mantiene»). services.py reuses the same helpers inside its own transaction.

Every list pages (``limit`` ≤ 100) with ``id`` as the last tie-break. The ``find_*`` helpers resolve
how a person names a record (assistant, voice): by id, else an exact name or number, else the only one
that contains it; several → 409 ``*_ambiguous`` naming them.
"""

import datetime as dt
from collections import defaultdict
from uuid import UUID

from django.db.models import (
    BooleanField,
    Case,
    CharField,
    Count,
    DateTimeField,
    Exists,
    ExpressionWrapper,
    F,
    Func,
    IntegerField,
    Max,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.customer.models import OrderLink
from apps.sale.models import Order, OrderLine, Sale
from apps.table.models import Hold, Table, TableSession, TableSettings, Zone
from apps.table.schemas import (
    ByOrderIn,
    FloorStatusOut,
    HoldByReservationIn,
    HoldOut,
    LineOut,
    LineRefIn,
    NoIn,
    SessionListIn,
    SessionOut,
    SessionPage,
    SessionRefIn,
    SessionsOut,
    SettingsOut,
    TableListIn,
    TableOut,
    TablePage,
    TableRefIn,
    WaiterListIn,
    WaiterPage,
    ZoneListIn,
    ZoneOut,
    ZonePage,
    ZoneRefIn,
)
from base.business import currency_decimals

#: A reservation paints its table Reserved this long before it starts (WORKBOOK «Referencia adoptada»).
RESERVED_LEAD = dt.timedelta(minutes=60)
#: How many names an ambiguous reference lists.
MAX_CANDIDATES = 5
#: Width every run of digits of a table number is padded to, to sort numbers as numbers.
NATURAL_PAD = 12

ZONE_NOT_FOUND = _("That zone does not exist in this business.")
ZONE_AMBIGUOUS = _("“%(said)s” matches several zones: %(names)s. Say which one.")
TABLE_NOT_FOUND = _("That table does not exist in this business.")
TABLE_AMBIGUOUS = _(
    "“%(said)s” matches several tables: %(names)s. Say which one (with its zone)."
)
SESSION_NOT_FOUND = _("That table check does not exist in this business.")
SESSION_NOT_ACTIVE = _(
    "That check is not open: it does not exist in this business, or it has already been closed, "
    "transferred, merged or parked."
)
SESSION_AMBIGUOUS = _("Table %(number)s has %(count)s open checks: say which one.")
TABLE_LABEL = _("%(number)s (%(zone)s)")
NO_ZONE = _("no zone")
HOLD_NOT_FOUND = _(
    "That hold is not there any more: it was released, it expired, or that booking never held a table."
)
LINE_NOT_FOUND = _("That line is not on the check of any table.")

ZONE_ORDER = {
    "sort_order": ("sort_order",),
    "name": ("name",),
    "color": ("color",),
    "table_count": ("table_count",),
    "available_count": ("available_count",),
    "is_active": ("is_active",),
}
TABLE_ORDER = {
    "number": ("number_sort", "number_lower"),
    "name": ("name",),
    "zone_name": ("zone__name",),
    "capacity": ("capacity",),
    "status": ("status_now",),
}
SESSION_ORDER = {
    "opened_at": ("opened_at",),
    "closed_at": ("closed_now",),
    "table_number": ("table__number",),
    "zone_name": ("table__zone__name",),
    "guests_count": ("guests_count",),
    "paid_total": ("paid_total",),
    "status": ("status_now",),
}
ENDED = [Order.Status.COMPLETED, Order.Status.VOIDED]
#: The checks still alive (seated or parked): Sales ending their check ends them.
LIVE_STATUSES = [TableSession.Status.OPEN, TableSession.Status.PARKED]


# --- The business's clock ------------------------------------------------------------------------


def business_zone():
    """The business's time zone (phase 1: ``settings.TIME_ZONE``; the Hub keeps no zone yet)."""
    return timezone.get_current_timezone()


def zone_name() -> str:
    zone = business_zone()
    return getattr(zone, "key", str(zone))


def end_of_today(now: dt.datetime) -> dt.datetime:
    """Midnight at the end of the business's today."""
    local = timezone.localtime(now, business_zone())
    tomorrow = local.date() + dt.timedelta(days=1)
    return dt.datetime.combine(tomorrow, dt.time.min, tzinfo=business_zone())


# --- Shared with services.py, inside the command's own transaction --------------------------------


def current_settings() -> TableSettings:
    """The room settings; the factory ones (unsaved) if they were never saved."""
    return TableSettings.objects.first() or TableSettings()


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


def natural_key(expression) -> Func:
    """``number`` with every run of digits left-padded to 12, so text order is natural order.

    ``Barra 2 Bis`` → ``Barra 000000000002 Bis`` (the old module's ``number_sort``, tables#68)."""
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


def _first_match(rows, field: str, said: str) -> list:
    for lookup in (Q(**{f"{field}__iexact": said}), Q(**{f"{field}__icontains": said})):
        found = list(rows.filter(lookup).order_by(field, "id")[: MAX_CANDIDATES + 1])
        if found:
            return found
    return []


def _locked(rows, lock: bool):
    return rows.select_for_update(of=("self",)) if lock else rows


def find_zone(
    zone_id: UUID | None, said: str | None, *, lock: bool = False, rows=None
) -> Zone:
    """A live zone by id, or by its name (exact, else the only one that contains it). It comes from
    ``rows`` when given (e.g. with what its detail shows): one read, so a deletion committed meanwhile is
    either not seen yet or not found, never a row that vanished between two reads."""
    zones = Zone.objects.filter(is_deleted=False)
    if zone_id is None:
        candidates = _first_match(zones, "name", (said or "").strip())
        if len(candidates) > 1:
            names = ", ".join(zone.name for zone in candidates[:MAX_CANDIDATES])
            raise Conflict(
                str(ZONE_AMBIGUOUS) % {"said": said, "names": names},
                code="table.zone_ambiguous",
            )
        zone_id = candidates[0].pk if candidates else None
    found_in = zones if rows is None else rows.filter(is_deleted=False)
    zone = _locked(found_in.filter(pk=zone_id), lock).first()
    if zone is None:
        raise NotFound(str(ZONE_NOT_FOUND), code="table.zone_not_found")
    return zone


def table_label(table: Table) -> str:
    return str(TABLE_LABEL) % {
        "number": table.number,
        "zone": table.zone.name if table.zone_id else NO_ZONE,
    }


def check_label(session: TableSession) -> str:
    """Where a check is: its table with its zone («5 (Terrace)»), or parked."""
    return table_label(session.table) if session.table_id else str(TableSession.Status.PARKED.label)


def find_table(
    table_id: UUID | None,
    said: str | None,
    zone_said: str | None = None,
    *,
    lock: bool = False,
    rows=None,
) -> Table:
    """A table in use or not (never a deleted one) by id, or by its number (or name) and, when the
    number repeats in several zones, its zone; from ``rows`` when given, in one read (as ``find_zone``)."""
    tables = Table.objects.filter(is_deleted=False).select_related("zone")
    if table_id is None:
        said = (said or "").strip()
        named = tables
        if zone_said:
            named = named.filter(zone=find_zone(None, zone_said))
        candidates = list(
            named.filter(number__iexact=said).order_by("number", "id")[
                : MAX_CANDIDATES + 1
            ]
        )
        if not candidates:
            candidates = _first_match(named, "name", said) if said else []
        if len(candidates) > 1:
            names = ", ".join(
                table_label(table) for table in candidates[:MAX_CANDIDATES]
            )
            raise Conflict(
                str(TABLE_AMBIGUOUS) % {"said": said, "names": names},
                code="table.table_ambiguous",
            )
        table_id = candidates[0].pk if candidates else None
    found_in = tables if rows is None else rows.filter(is_deleted=False)
    table = _locked(found_in.filter(pk=table_id), lock).first()
    if table is None:
        raise NotFound(str(TABLE_NOT_FOUND), code="table.table_not_found")
    return table


def find_session(
    session_id: UUID | None,
    table_said: str | None,
    zone_said: str | None = None,
    *,
    lock: bool = False,
    rows=None,
) -> TableSession:
    """A table check by id (any status, never a deleted one), or the live check at the table named; from
    ``rows`` when given, in one read (as ``find_zone``)."""
    sessions = TableSession.objects.filter(is_deleted=False).select_related(
        "table", "table__zone"
    )
    if session_id is None:
        table = find_table(None, table_said, zone_said)
        live = list(
            live_sessions()
            .filter(table=table)
            .order_by("opened_at", "id")[:MAX_CANDIDATES]
        )
        if not live:
            raise Conflict(str(SESSION_NOT_ACTIVE), code="table.session_not_active")
        if len(live) > 1:
            raise Conflict(
                str(SESSION_AMBIGUOUS) % {"number": table.number, "count": len(live)},
                code="table.session_ambiguous",
            )
        session_id = live[0].pk
    found_in = sessions if rows is None else rows.filter(is_deleted=False)
    session = _locked(found_in.filter(pk=session_id), lock).first()
    if session is None:
        raise NotFound(str(SESSION_NOT_FOUND), code="table.session_not_found")
    return session


def order_is_open(order_id: UUID | None) -> bool:
    return (
        order_id is not None
        and Order.objects.filter(pk=order_id, status=Order.Status.OPEN).exists()
    )


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


def _page(queryset, params, row) -> dict:
    items = list(queryset[params.offset : params.offset + params.limit])
    return {
        "rows": row(items),
        "total": queryset.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


def _ordered(queryset, sort: str, columns: dict):
    descending = sort.startswith("-")
    fields = columns[sort.lstrip("-")]
    order = [
        F(field).desc(nulls_last=True) if descending else F(field).asc(nulls_last=True)
        for field in fields
    ]
    return queryset.order_by(*order, "-id" if descending else "id")


def zone_rows(zones: list[Zone]) -> list[dict]:
    return [
        {
            "id": zone.id,
            "name": zone.name,
            "description": zone.description,
            "color": zone.color,
            "sort_order": zone.sort_order,
            "is_active": zone.is_active,
            "table_count": zone.table_count,
            "available_count": zone.available_count,
        }
        for zone in zones
    ]


def zones_now(now: dt.datetime):
    """The live zones with their tables in use and, of them, the free ones right now."""
    in_use = (
        tables_now(now)
        .filter(zone=OuterRef("pk"), is_active=True)
        .order_by()
        .values("zone")
    )
    count = in_use.annotate(n=Count("pk")).values("n")[:1]
    free = in_use.filter(status_now="available").annotate(n=Count("pk")).values("n")[:1]
    return Zone.objects.filter(is_deleted=False).annotate(
        table_count=Coalesce(Subquery(count, output_field=IntegerField()), 0),
        available_count=Coalesce(Subquery(free, output_field=IntegerField()), 0),
    )


def table_rows(tables: list[Table], now: dt.datetime) -> list[dict]:
    """The rows of ``tables`` (annotated by ``tables_now``) with their live checks and their next hold."""
    ids = [table.pk for table in tables]
    checks = defaultdict(list)
    for session in live_sessions().filter(table_id__in=ids).order_by("opened_at", "id"):
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
                "guests": sum(s.guests_count for s in seated) if seated else None,
                "since": seated[0].opened_at if seated else None,
                "waiter_name": seated[0].waiter_name if seated else "",
                "checks": [_check_row(s, customers) for s in seated],
                "hold": _hold_row(hold, now) if hold else None,
            }
        )
    return out


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


def hold_row(hold: Hold) -> dict:
    return {
        "id": hold.pk,
        "table_id": hold.table_id,
        "source": hold.source,
        "source_ref": hold.source_ref,
        "held_from": hold.held_from,
        "held_until": hold.held_until,
        "party_size": hold.party_size,
        "label": hold.label,
        "status": hold.status,
    }


def session_out(session: TableSession) -> dict:
    """One check as ``table.session.list`` paints it, read again now (also after a write)."""
    return session_rows([sessions_now().get(pk=session.pk)])[0]


# --- Zones ---------------------------------------------------------------------------------------


@operation(
    "table.zone.list",
    kind="query",
    permission="table.view_zone",
    input=ZoneListIn,
    output=ZonePage,
    expose_api=True,
    ai={
        "description": "List the zones of the room (dining room, terrace, bar…) with their tables and how many are free."
    },
)
def list_zones(ctx: OperationContext, params: ZoneListIn) -> dict:
    zones = zones_now(timezone.now())
    for text in (params.search, params.name):
        if text and text.strip():
            zones = zones.filter(name__icontains=text.strip())
    if params.color:
        zones = zones.filter(color=params.color)
    if params.is_active is not None:
        zones = zones.filter(is_active=params.is_active)
    return _page(_ordered(zones, params.sort, ZONE_ORDER), params, zone_rows)


@operation(
    "table.zone.get",
    kind="query",
    permission="table.view_zone",
    input=ZoneRefIn,
    output=ZoneOut,
    expose_api=True,
    ai={
        "description": "Get one zone of the room by its id or its name, with its tables and the free ones."
    },
)
def get_zone(ctx: OperationContext, params: ZoneRefIn) -> dict:
    return zone_rows([find_zone(params.id, params.zone, rows=zones_now(timezone.now()))])[0]


# --- Tables --------------------------------------------------------------------------------------


@operation(
    "table.table.list",
    kind="query",
    permission="table.view_table",
    input=TableListIn,
    output=TablePage,
    expose_api=True,
    ai={
        "description": "List the tables of the room in natural order (2 before 10), each with its status right now "
        "(available, occupied, reserved, blocked), its guests and since when, who serves it, its customer and its next "
        "reservation of today. Filter by zone, status or number."
    },
)
def list_tables(ctx: OperationContext, params: TableListIn) -> dict:
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
        _ordered(rows, params.sort, TABLE_ORDER),
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
        "status right now, its open checks (two after a split), guests, waiter, customer and next reservation."
    },
)
def get_table(ctx: OperationContext, params: TableRefIn) -> dict:
    now = timezone.now()
    shown = tables_now(now).select_related("zone")
    return table_rows([find_table(params.id, params.table, params.zone, rows=shown)], now)[0]


# --- Table checks --------------------------------------------------------------------------------


@operation(
    "table.session.list",
    kind="query",
    permission="table.view_session",
    input=SessionListIn,
    output=SessionPage,
    expose_api=True,
    ai={
        "description": "List the checks of the room (open, closed, transferred, merged, parked), newest first, with "
        "their table, zone, waiter, guests, times and what their check of Sales charged."
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
    return _page(_ordered(rows, params.sort, SESSION_ORDER), params, session_rows)


@operation(
    "table.session.get",
    kind="query",
    permission="table.view_session",
    input=SessionRefIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Get one table check by its id, or the open check of a table by its number («table 4»), with "
        "its check of Sales, guests, waiter, customer and what it charged."
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
        "description": "Find the table of a check of Sales: the table checks that hold it, newest first."
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
        "«Split check» lists it."
    },
)
def get_line(ctx: OperationContext, params: LineRefIn) -> dict:
    held = TableSession.objects.filter(is_deleted=False, order_id__isnull=False).values("order_id")
    line = OrderLine.objects.live().filter(pk=params.id, order_id__in=held).first()
    if line is None:
        raise NotFound(str(LINE_NOT_FOUND), code="table.line_not_found")
    return {"id": line.id, "name": line.name, "quantity": line.quantity, "unit": line.unit}


@operation(
    "table.waiter.list",
    kind="query",
    permission="table.view_session",
    input=WaiterListIn,
    output=WaiterPage,
    ai={
        "description": "List the people who have opened checks of the room (the waiter filter), by name."
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
        rows = rows.filter(name__icontains=params.search.strip())
    rows = rows.order_by(Lower("name"), "waiter_id")
    return _page(
        rows,
        params,
        lambda items: [
            {"id": item["waiter_id"], "name": item["name"] or item["waiter_id"]}
            for item in items
        ],
    )


# --- Floor and settings --------------------------------------------------------------------------


@operation(
    "table.floor.status",
    kind="query",
    permission="table.view_table",
    input=NoIn,
    output=FloorStatusOut,
    ai={
        "description": "Whether the floor plan is set up: how many tables are in use and how many zones there are."
    },
)
def floor_status(ctx: OperationContext, params: NoIn) -> dict:
    return {
        "usable_tables": Table.objects.filter(is_deleted=False, is_active=True).count(),
        "zones": Zone.objects.filter(is_deleted=False).count(),
    }


def settings_row(settings: TableSettings) -> dict:
    return {
        "prompt_guests_on_seat": settings.prompt_guests_on_seat,
        "timer_warning_minutes": settings.timer_warning_minutes,
        "timer_critical_minutes": settings.timer_critical_minutes,
        "reserved_lead_minutes": int(RESERVED_LEAD.total_seconds() // 60),
        "timezone": zone_name(),
    }


@operation(
    "table.settings.get",
    kind="query",
    permission="table.view_settings",
    input=NoIn,
    output=SettingsOut,
    ai={
        "description": "Read the room settings: whether seating asks for the guests and when an open check turns "
        "amber and red."
    },
)
def get_settings(ctx: OperationContext, params: NoIn) -> dict:
    return settings_row(current_settings())


# --- Holds ---------------------------------------------------------------------------------------


@operation(
    "table.hold.by_reservation",
    kind="query",
    permission="table.view_table",
    input=HoldByReservationIn,
    output=HoldOut,
    expose_api=True,
    ai={
        "description": "Get the hold a reservation of Reservations keeps on its table, while it holds it: the table, "
        "its window and the name it paints on the table."
    },
)
def hold_by_reservation(ctx: OperationContext, params: HoldByReservationIn) -> dict:
    hold = (
        Hold.objects.filter(
            source=Hold.Source.RESERVATION,
            source_ref=str(params.reservation_id),
            status=Hold.Status.HELD,
            held_until__gt=timezone.now(),
        )
        .order_by("held_from", "id")
        .first()
    )
    if hold is None:
        raise NotFound(str(HOLD_NOT_FOUND), code="table.hold_not_found")
    return hold_row(hold)
