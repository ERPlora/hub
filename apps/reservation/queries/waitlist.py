"""The waitlist: the list in the order people were written down, and one entry by id or by its guest."""

import datetime as dt
from uuid import UUID

from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.reservation.models import WaitlistEntry
from apps.reservation.queries.naming import _named, _said_day, _said_time, _who
from apps.reservation.queries.reads import MAX_CANDIDATES, _guest_matches, _page, _phone_matches, _when
from apps.reservation.schemas.waitlist import WaitlistDetailOut, WaitlistListIn, WaitlistPage, WaitlistRefIn
from base.ordering import list_order_for

ENTRY_NOT_FOUND = _("That waitlist entry does not exist in this business.")
ENTRY_AMBIGUOUS = _(
    "“%(said)s” is on the waitlist several times: %(matches)s. Say which day."
)


def entry_out(entry: WaitlistEntry) -> dict:
    return {
        "id": entry.pk,
        "customer_id": entry.customer_id,
        "guest_name": entry.guest_name,
        "guest_phone": entry.guest_phone,
        "guest_email": entry.guest_email,
        "date": entry.date,
        "preferred_time": entry.preferred_time,
        "party_size": entry.party_size,
        "notes": entry.notes,
        "is_contacted": entry.is_contacted,
        "contacted_at": entry.contacted_at,
        "is_converted": entry.reservation_id is not None,
        "reservation_id": entry.reservation_id,
        "created_at": entry.created_at,
    }


def entry_label(ctx: OperationContext, entry: WaitlistEntry) -> str:
    """As the waitlist's dialogs say an entry: its guest, the day and the time they would like."""
    return _named(_who(ctx, entry), _said_day(entry.date, ctx.language), _said_time(entry.preferred_time, ctx.language))


def waiting_entries() -> QuerySet[WaitlistEntry]:
    return WaitlistEntry.objects.filter(is_deleted=False)


def find_entry(
    ctx: OperationContext, entry_id: UUID | None, guest: str | None, day: dt.date | None, *, lock: bool = False
) -> WaitlistEntry:
    """A live waitlist entry by id or by its guest (``_guest_matches``) and day; among several, the ones waiting."""
    rows = waiting_entries()
    if entry_id is None:
        named = rows.filter(_guest_matches(ctx, guest or ""))
        if day:
            named = named.filter(date=day)
        candidates = list(
            named.order_by("date", "preferred_time", "created_at", "id")[
                : MAX_CANDIDATES * 4
            ]
        )
        waiting = [item for item in candidates if item.reservation_id is None]
        candidates = waiting or candidates
        if len(candidates) > 1:
            matches = ", ".join(
                f"{item.guest_name} · {_when(item.date, item.preferred_time)}"
                for item in candidates[:MAX_CANDIDATES]
            )
            raise Conflict(
                str(ENTRY_AMBIGUOUS) % {"said": guest, "matches": matches},
                code="reservation.entry_ambiguous",
            )
        entry_id = candidates[0].pk if candidates else None
    if entry_id is not None and lock:
        rows = rows.select_for_update()
    found = rows.filter(pk=entry_id).first() if entry_id is not None else None
    if found is None:
        raise NotFound(str(ENTRY_NOT_FOUND), code="reservation.entry_not_found")
    return found


WAITLIST_SORTS = {
    "position": ("date", "preferred_time", "created_at"),
    "date": ("date", "preferred_time", "created_at"),
    "preferred_time": ("preferred_time", "date", "created_at"),
    "guest_name": ("guest_name",),
    "party_size": ("party_size",),
    "is_contacted": ("is_contacted", "date", "preferred_time", "created_at"),
}


@operation(
    "reservation.waitlist.list",
    kind="query",
    permission="reservation.view_waitlistentry",
    input=WaitlistListIn,
    output=WaitlistPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "who is on the waitlist tonight?",
                "show me Saturday's waitlist",
            ),
            "es": (
                "¿quién está en lista de espera esta noche?",
                "enséñame la lista de espera del sábado",
            ),
        },
        "description": "Lists the waitlist in the order people were written down (day, preferred time, arrival): who, "
        "for how many, contacted or not, and converted into a reservation or still waiting."
    },
)
def list_waitlist(ctx: OperationContext, params: WaitlistListIn) -> dict:
    rows = waiting_entries()
    if params.search:
        rows = rows.filter(_guest_matches(ctx, params.search))
    if params.date_from:
        rows = rows.filter(date__gte=params.date_from)
    if params.date_to:
        rows = rows.filter(date__lte=params.date_to)
    if params.is_contacted is not None:
        rows = rows.filter(is_contacted=params.is_contacted)
    if params.is_converted is not None:
        rows = rows.filter(reservation__isnull=not params.is_converted)
    if params.guest_name:
        rows = rows.filter(guest_name__icontains=params.guest_name)
    if params.guest_phone:
        rows = rows.filter(_phone_matches(params.guest_phone))
    return _page(
        rows.order_by(*list_order_for(params.sort, columns=WAITLIST_SORTS)), params, entry_out
    )


@operation(
    "reservation.waitlist.get",
    kind="query",
    permission="reservation.view_waitlistentry",
    input=WaitlistRefIn,
    output=WaitlistDetailOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "is Luis still on the waitlist?",
                "show me Marta's waitlist entry",
            ),
            "es": (
                "¿sigue Luis en la lista de espera?",
                "¿hemos contactado ya con Marta de la lista de espera?",
            ),
        },
        "description": "Reads one waitlist entry: by id, or by its guest's name or phone (and its day, when they wait "
        "for several); among several, the ones still waiting."
    },
)
def get_entry(ctx: OperationContext, params: WaitlistRefIn) -> dict:
    entry = find_entry(ctx, params.id, params.guest, params.day)
    return {**entry_out(entry), "label": entry_label(ctx, entry)}
