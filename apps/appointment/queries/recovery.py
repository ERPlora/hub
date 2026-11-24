"""What a separate copy of the business gives back (hub#1284; BASE-F114, APPOINTMENT-F01)."""

from uuid import UUID

from django.db.models import Exists, OuterRef
from django.utils import timezone
from psycopg import sql

from apps.appointment.models import Appointment, AppointmentService, Recurring, RecurringService
from apps.customer.queries import card_in_business, cards_in_copy
from apps.service.queries import recovery

from .business import today

#: A series' rule, as its create takes it.
RULE_FIELDS = ("frequency", "day_of_week", "time", "duration_minutes", "start_date", "end_date", "max_occurrences")
#: What an appointment of a separate copy is read with (``appointments_in_copy``): each a column since ``0001_initial``.
COPY_FIELDS = ("id", "customer", "staff", "start", "duration_minutes", "notes", "internal_notes", "source")
#: What the appointment kept of its customer when it was booked: who she is when the copy no longer has her card live.
KEPT_OF_THE_CUSTOMER = ("customer_name", "customer_phone", "customer_email")
#: Still booked: a cancelled one, a no-show or one done is not lacking from the agenda.
BOOKED = [Appointment.Status.PENDING.value, Appointment.Status.CONFIRMED.value]


def appointments_in_copy(conn) -> list[dict]:
    """hub#1284: each appointment of a separate copy of the business still to come and still booked (pending or
    confirmed, neither deleted nor charged: a charged one is the till's), by its start, with its ``id`` there, what
    ``appointment.appointment.create`` takes (its services in their order, its professional, its start, its minutes,
    its notes and how it was booked), the card of its customer there (``customer_card``, ``_card_of``) and every
    service of the copy as Services reads it (``services_in_copy``, hub#1341: read once, the same list in each), which
    ``appointments_not_in_business`` matches the business's by; nothing where the app's table is not there. One gone by
    is not read: it was charged or not, and the agenda books none in the past. ``conn`` is the copy's direct, read-only
    connection (``recoverable_from_copy`` on this app's config: the copy is no business and has no alias), so it is
    read by its own SQL over the models' names, never the ORM."""
    table = Appointment._meta.db_table
    if conn.execute("SELECT to_regclass(%s)", [table]).fetchone()[0] is None:
        return []
    read = (*COPY_FIELDS, *KEPT_OF_THE_CUSTOMER)
    names = (*read, "status", "deleted_at", "charged_at", "sale_id")
    column = {field: sql.Identifier(Appointment._meta.get_field(field).column) for field in names}
    query = sql.SQL(
        "SELECT {} FROM {} WHERE {} IS NULL AND {} IS NULL AND {} IS NULL AND {} = ANY(%s) AND {} > %s ORDER BY {}, {}"
    ).format(
        sql.SQL(", ").join(column[field] for field in read),
        sql.Identifier(table),
        column["deleted_at"],
        column["charged_at"],
        column["sale_id"],
        column["status"],
        column["start"],
        column["start"],
        column["id"],
    )
    rows = [dict(zip(read, row, strict=True)) for row in conn.execute(query, [BOOKED, timezone.now()])]
    services = _lines_in_copy(conn, AppointmentService, "appointment", [row["id"] for row in rows])
    cards = {card["id"]: card for card in cards_in_copy(conn)}
    # All of them, never the appointments' alone: Services matches by the whole copy (``services_in_business``).
    copy_services = recovery.services_in_copy(conn) if rows else []
    return [
        {
            "id": row["id"],
            "customer_card": _card_of(cards.get(row["customer"]), row),
            "staff_id": row["staff"],
            "services": services.get(row["id"], []),
            "start": row["start"],
            "duration_minutes": row["duration_minutes"],
            "notes": row["notes"],
            "internal_notes": row["internal_notes"],
            "source": row["source"],
            "services_in_copy": copy_services,
        }
        for row in rows
    ]


def _lines_in_copy(conn, lines, owner: str, ids: list[UUID]) -> dict[UUID, list[dict]]:
    """``{id of an appointment or a series of the copy: its services in their order}``, as its create takes them, of
    ``ids``: ``lines`` is the model of its services (``AppointmentService``, ``RecurringService``), ``owner`` its field
    that points at the appointment or the series."""
    if not ids:
        return {}
    column = {field: sql.Identifier(lines._meta.get_field(field).column) for field in (owner, "service", "position")}
    query = sql.SQL("SELECT {}, {} FROM {} WHERE {} = ANY(%s) ORDER BY {}, {}").format(
        column[owner],
        column["service"],
        sql.Identifier(lines._meta.db_table),
        column[owner],
        column[owner],
        column["position"],
    )
    services: dict[UUID, list[dict]] = {}
    for record, service in conn.execute(query, [ids]):
        services.setdefault(record, []).append({"service_id": service})
    return services


def _card_of(card: dict | None, row: dict) -> dict:
    """The customer of an appointment or a series of the copy as Customers matches her (``card_in_business``): the
    copy's live card (``cards_in_copy``), or, when the copy no longer has it live, what the appointment or the series
    kept of her (a series keeps her name alone)."""
    if card is None:
        kept = {field.removeprefix("customer_"): row.get(field, "") for field in KEPT_OF_THE_CUSTOMER}
        card = {"id": row["customer"]} | kept
    return {field: card[field] for field in ("id", "name", "phone", "email")}


def appointments_deleted_in_business(appointments: list[dict]) -> list[dict]:
    """hub#1326: the appointments of a separate copy (``appointments_in_copy``) the business still holds deleted
    (APPOINTMENT-F11), in their order, for ``appointment.appointment.restore``: the same appointment back, with its
    number, its history and its series. The same by its id, whatever the copy says of it. Never one booked again since,
    as the business holds it: a live one of its customer at its moment, or of its series on its date (that one
    stays)."""
    live = Appointment.objects.filter(deleted_at__isnull=True)
    again = live.filter(customer_id=OuterRef("customer_id"), start=OuterRef("start"))
    rebooked = live.filter(recurring_id=OuterRef("recurring_id"), occurrence_date=OuterRef("occurrence_date"))
    held = set(
        Appointment.objects.filter(pk__in=[one["id"] for one in appointments], deleted_at__isnull=False)
        .exclude(Exists(again))
        .exclude(Exists(rebooked))
        .values_list("pk", flat=True)
    )
    return [one for one in appointments if one["id"] in held]


def appointments_not_in_business(appointments: list[dict]) -> list[dict]:
    """hub#1284: the appointments of a separate copy (``appointments_in_copy``) the business lacks, in their order, each
    as ``appointment.appointment.create`` takes it here, with its ``id`` there. Not lacking: one the business holds,
    live or deleted, whatever became of it since (moved, cancelled, done: it stays as it is; a deleted one comes back the
    same, ``appointments_deleted_in_business``, hub#1326), and one booked again, by hand or brought back already (a live
    appointment of the same customer at the same moment). Lacking: one gone altogether.

    Its customer is the business's card of hers by Customers' own rule (``card_in_business``: the same card, the one it
    was merged into or the one made again); without one, the copy's, which the create refuses with why: an appointment
    never comes back for a customer the business does not have. Each of its services is the business's by Services' own
    rule, given every service of the copy (``services_in_business``, hub#1341: the same one, or the one made again, by
    hand or brought back by Services first, the apps going in the order of their ``requires``); without one, the
    copy's, which the create refuses with why. Its professional, by her id (one who leaves keeps hers): the create
    refuses one not bookable any more, as it refuses a moment that does not fit the agenda now."""
    held = set(Appointment.objects.filter(pk__in=[one["id"] for one in appointments]).values_list("pk", flat=True))
    # The same list in each (``appointments_in_copy``): every service of the copy, matched once.
    services = recovery.services_in_business(appointments[0]["services_in_copy"]) if appointments else {}
    lacking = []
    for one in appointments:
        if one["id"] in held:
            continue
        customer = card_in_business(one["customer_card"]) or one["customer_card"]["id"]
        if Appointment.objects.filter(deleted_at__isnull=True, customer_id=customer, start=one["start"]).exists():
            continue
        lacking.append(_as_created_here(one, customer, services))
    return lacking


def _as_created_here(one: dict, customer: UUID, services: dict[UUID, UUID]) -> dict:
    """An appointment or a series of the copy as its create takes it in the business, with its ``id`` there: for
    ``customer``, the business's card of hers, and each of its services the business's (``services``, from
    ``services_in_business``) or, without one, the copy's, which the create refuses with why."""
    create = {key: value for key, value in one.items() if key not in ("id", "customer_card", "services_in_copy")}
    create["services"] = [
        {"service_id": services.get(line["service_id"], line["service_id"])} for line in one["services"]
    ]
    return {"id": one["id"], "customer_id": customer} | create


#: What a series of a separate copy is read with (``series_in_copy``): each a column since ``0001_initial``.
SERIES_COPY_FIELDS = ("id", "customer", "customer_name", "staff", *RULE_FIELDS)


def series_in_copy(conn) -> list[dict]:
    """hub#1327: each series of a separate copy of the business still booking (neither deleted nor paused, with its
    professional and not ended by its end date: one that books nothing is not lacking, as a cancelled appointment is
    not), by its id, with its ``id`` there, what ``appointment.recurring.create`` takes (its services in their order,
    its professional and its rule), the card of its customer there (``customer_card``, ``_card_of``) and every service
    of the copy as Services reads it (``services_in_copy``: read once, the same list in each), which
    ``series_not_in_business`` matches the business's by; nothing where the app's table is not there. ``conn`` is the
    copy's direct, read-only connection, so it is read by its own SQL over the models' names, never the ORM."""
    table = Recurring._meta.db_table
    if conn.execute("SELECT to_regclass(%s)", [table]).fetchone()[0] is None:
        return []
    column = {
        field: sql.Identifier(Recurring._meta.get_field(field).column)
        for field in (*SERIES_COPY_FIELDS, "deleted_at", "is_active")
    }
    query = sql.SQL(
        "SELECT {} FROM {} WHERE {} IS NULL AND {} AND {} IS NOT NULL AND ({} IS NULL OR {} >= %s) ORDER BY {}"
    ).format(
        sql.SQL(", ").join(column[field] for field in SERIES_COPY_FIELDS),
        sql.Identifier(table),
        column["deleted_at"],
        column["is_active"],
        column["staff"],
        column["end_date"],
        column["end_date"],
        column["id"],
    )
    rows = [dict(zip(SERIES_COPY_FIELDS, row, strict=True)) for row in conn.execute(query, [today()])]
    if not rows:
        return []
    services = _lines_in_copy(conn, RecurringService, "recurring", [row["id"] for row in rows])
    cards = {card["id"]: card for card in cards_in_copy(conn)}
    copy_services = recovery.services_in_copy(conn)
    return [
        {
            "id": row["id"],
            "customer_card": _card_of(cards.get(row["customer"]), row),
            "staff_id": row["staff"],
            "services": services.get(row["id"], []),
            **{field: row[field] for field in RULE_FIELDS},
            "services_in_copy": copy_services,
        }
        for row in rows
    ]


#: What makes two series of a customer the same one: they repeat the same way, on the same day, at the same time.
SAME_RULE = ("frequency", "day_of_week", "time")


def _made_again(customer: UUID, rule: dict) -> bool:
    """Whether the business holds a live series of ``customer`` with ``rule``'s ``SAME_RULE``: the same series made
    again since, by hand or brought back already, whoever does it."""
    same = {field: rule[field] for field in SAME_RULE}
    return Recurring.objects.filter(deleted_at__isnull=True, customer_id=customer, **same).exists()


def series_deleted_in_business(series: list[dict]) -> list[dict]:
    """hub#1327: the series of a separate copy (``series_in_copy``) the business still holds deleted (APPOINTMENT-F15),
    in their order, for ``appointment.recurring.restore``: the same series back, with the appointments it booked. The
    same by its id, whatever the copy says of it; never one made again since, as the business holds it (that one
    stays)."""
    held = Recurring.objects.filter(pk__in=[one["id"] for one in series], deleted_at__isnull=False)
    rows = held.values("id", "customer_id", *SAME_RULE)
    back = {row["id"] for row in rows if not _made_again(row["customer_id"], row)}
    return [one for one in series if one["id"] in back]


def series_not_in_business(series: list[dict]) -> list[dict]:
    """hub#1327: the series of a separate copy (``series_in_copy``) the business lacks, in their order, each as
    ``appointment.recurring.create`` takes it here (``_as_created_here``), with its ``id`` there. Not lacking: one the
    business holds, live or deleted (a deleted one comes back the same, ``series_deleted_in_business``), and one made
    again for the business's card of her customer (``_made_again``). Its customer and its services are matched as an
    appointment's are (``appointments_not_in_business``); the create refuses with why what is not there any more, and
    books the dates of its window that still fit, so none where an appointment came back before it."""
    held = set(Recurring.objects.filter(pk__in=[one["id"] for one in series]).values_list("pk", flat=True))
    # The same list in each (``series_in_copy``): every service of the copy, matched once.
    services = recovery.services_in_business(series[0]["services_in_copy"]) if series else {}
    lacking = []
    for one in series:
        if one["id"] in held:
            continue
        customer = card_in_business(one["customer_card"]) or one["customer_card"]["id"]
        if not _made_again(customer, one):
            lacking.append(_as_created_here(one, customer, services))
    return lacking
