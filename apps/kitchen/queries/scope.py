"""The stations and how a person names them: one station by its id or its name, or the scope of the board."""

from dataclasses import replace
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.errors import Conflict, NotFound

from apps.kitchen.models import Station
from apps.kitchen.queries.reads import MAX_CANDIDATES
from apps.kitchen.queries.views import ItemView, TicketView
from base.text_search import contains_text

STATION_NOT_FOUND = _("That station does not exist in this business.")
STATION_AMBIGUOUS = _("“%(said)s” matches several stations: %(names)s. Say which one.")
NONE_SAID = "none"

#: The whole board (no station chosen): «Todas», the pass.
ALL = object()


def station_map() -> dict[UUID, Station]:
    return {station.id: station for station in Station.objects.all()}


def find_station(station_id: UUID | None, said: str | None) -> Station:
    """A live station by its id, else by its exact name, else the only one whose name contains it."""
    stations = Station.objects.filter(is_deleted=False)
    if station_id is not None:
        found = stations.filter(pk=station_id).first()
        if found is None:
            raise NotFound(str(STATION_NOT_FOUND), code="kitchen.station_not_found")
        return found
    text = (said or "").strip()
    exact = list(stations.filter(name__iexact=text)[:2])
    candidates = exact or list(
        stations.filter(contains_text(text, "name")).order_by("name", "id")[
            : MAX_CANDIDATES + 1
        ]
    )
    if not candidates:
        raise NotFound(str(STATION_NOT_FOUND), code="kitchen.station_not_found")
    if len(candidates) > 1:
        names = ", ".join(station.name for station in candidates[:MAX_CANDIDATES])
        raise Conflict(
            str(STATION_AMBIGUOUS) % {"said": text, "names": names},
            code="kitchen.station_ambiguous",
        )
    return candidates[0]


def find_scope(said: str | None):
    """``ALL`` (every station), ``None`` («none»: the dishes with no station) or a station's id."""
    text = (said or "").strip()
    if not text:
        return ALL
    if text.casefold() == NONE_SAID:
        return None
    try:
        station_id = UUID(text)
    except ValueError:
        return find_station(None, text).id
    # Only a live station: a tablet that remembers one deleted since is told so and goes back to every
    # station, instead of an empty board for ever.
    return find_station(station_id, None).id


def in_scope(item: ItemView, scope) -> bool:
    return scope is ALL or item.station_id == scope


def scoped(view: TicketView, scope) -> TicketView:
    """The ticket with the dishes of one station only (all of them with no station chosen)."""
    if scope is ALL:
        return view
    return replace(view, items=[item for item in view.items if in_scope(item, scope)])
