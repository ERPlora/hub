"""What every read of the service app shares: the platform's own permission, how a person's name for a
record resolves, the rows a write holds and how a list pages."""

from django.db.models import Q
from live.errors import Conflict, NotFound

#: Run only by the platform (events.py, a recovery): no role holds it, so no person and no API key reaches it.
SYSTEM = "service.system"

#: How many names an ambiguous reference lists.
MAX_CANDIDATES = 5
#: Who may read a customer's name (the Customers app's permission).
CUSTOMER_VIEW = "customer.view"


def _first_match(rows, said: str) -> list:
    """The rows of the first lookup that matches (an exact name, else a part of it), at most six."""
    for lookup in (Q(name__iexact=said), Q(name__icontains=said)):
        found = list(rows.filter(lookup).order_by("name", "id")[: MAX_CANDIDATES + 1])
        if found:
            return found
    return []


def held_rows(rows) -> list:
    """``rows``, each held until the command commits, taken in the same read and in id order, for a write that
    names them (a service put in a category or in a voucher, a voucher sold): their «Delete», archiving one or
    the Hub admin's deletion waits for that write, and in the order a move of the tree takes them, so the two
    never wait for each other in a circle. One taken away meanwhile is read once that ends: gone, or as it was
    left. ``FOR NO KEY UPDATE`` is the ORM's lightest lock: another write that names the same row waits its
    turn, while the database's own checks of what names it go on."""
    return list(rows.order_by("id").select_for_update(no_key=True, of=("self",)))


def _resolve(  # noqa: PLR0913
    rows,
    item_id,
    said,
    *,
    lock,
    hold=False,
    missing,
    missing_code,
    ambiguous,
    ambiguous_code,
    named=None,
):
    """The row named by ``item_id`` (in ``rows``), or by ``said`` (in ``named``, ``rows`` by default):
    ``lock`` takes it to change it, ``hold`` to name it (``held_rows``)."""
    if item_id is None:
        candidates = _first_match(rows if named is None else named, said or "")
        if len(candidates) > 1:
            names = ", ".join(
                candidate.name for candidate in candidates[:MAX_CANDIDATES]
            )
            raise Conflict(
                str(ambiguous) % {"said": said, "names": names}, code=ambiguous_code
            )
        item_id = candidates[0].pk if candidates else None
    found = rows.filter(pk=item_id)
    if lock:
        found = found.select_for_update(of=("self",))
    elif hold:
        found = found.select_for_update(no_key=True, of=("self",))
    row = found.first()
    if row is None:
        raise NotFound(str(missing), code=missing_code)
    return row


def _bounds(**lookups) -> dict:
    """The lookups whose value was given (a filter left empty narrows nothing)."""
    return {lookup: value for lookup, value in lookups.items() if value is not None}


def _page(queryset, params, row) -> dict:
    return {
        "rows": [
            row(item) for item in queryset[params.offset : params.offset + params.limit]
        ],
        "total": queryset.count(),
        "limit": params.limit,
        "offset": params.offset,
    }
