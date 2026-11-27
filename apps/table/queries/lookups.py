"""How a person names a zone, a table or a check (the assistant, the voice): by id, else an exact name or number, else
the only one that contains it; several → 409 ``*_ambiguous`` naming them. The writes (services/) find their rows the
same way, locked inside their own transaction.
"""

from uuid import UUID

from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from live.errors import Conflict, NotFound

from apps.table.models import Table, TableSession, Zone
from base.text_search import contains_text
from .floor import live_sessions, table_label

#: How many names an ambiguous reference lists.
MAX_CANDIDATES = 5

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


def _first_match(rows, field: str, said: str) -> list:
    for lookup in (Q(**{f"{field}__iexact": said}), contains_text(said, field)):
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
