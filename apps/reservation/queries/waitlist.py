"""The waitlist (``reservation.waitlist.list``, ``.get``), in the order people were written down.
"""

from live.context import OperationContext
from live.operations import operation

from apps.reservation.queries.lookups import _guest_matches, _phone_matches, find_entry, waiting_entries
from apps.reservation.queries.rows import _page, entry_label, entry_out
from apps.reservation.schemas.waitlist import WaitlistDetailOut, WaitlistListIn, WaitlistPage, WaitlistRefIn
from base.ordering import list_order_for

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
