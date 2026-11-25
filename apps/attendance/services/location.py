"""Where the device that clocks is: the counter or someone's own phone, how far from the workplace, and whether
a personal device is within the radius."""

from typing import Any

from django.utils.translation import gettext_lazy as _
from geopy.distance import geodesic
from live.context import OperationContext
from live.errors import Conflict

from apps.attendance.models import Record
from apps.attendance.schemas import PositionIn
from base import access
from base.queries.devices import device_of

LOCATION_REQUIRED = _(
    "Your location is needed to clock in from this device. Allow it, or clock in at the counter."
)
WORKPLACE_NOT_SET = _(
    "The workplace location is not set yet, so this device cannot clock in. Ask a manager to set it in "
    "the time clock settings, or clock in at the counter."
)
OUTSIDE_RADIUS = _(
    "You are %(distance)s m from the workplace, outside the allowed %(radius)s m. Move closer to clock "
    "in, or clock in at the counter."
)


def device_source(ctx: OperationContext) -> str:
    """The device that clocks: the counter POS (``shared``) or someone's own phone (``personal``).

    It is the platform's to say, never the payload's: the mode an administrator chose on the session's
    device (BASE-F62, «Settings › This device»). A browser the hub does not know, and a caller without one
    (an integration's API key, the system), clock as the shared one, the strict fallback of the old module:
    the location is never asked for (ATTENDANCE-F03).
    """
    device = device_of(ctx.request)
    if device is not None and device.mode == access.PERSONAL:
        return Record.Source.PERSONAL
    return Record.Source.SHARED


def _measure(values: dict, data: PositionIn, source: str, mine: bool) -> dict[str, Any]:
    """What is kept of where the device is (ATTENDANCE-F03).

    With the workplace set, the distance the Hub measures, inside/outside and the accuracy. The exact
    coordinates only when the business requires the location and the person clocks their own day from a
    personal device: nobody asked for them otherwise (nor for a manager's, clocking someone else, F12), and
    the day keeps them as long as the record (four years, art. 34.9 ET).
    """
    has_position = data.lat is not None and data.lng is not None
    distance = within = None
    if has_position and values["workplace_set"]:
        distance = geodesic((values["workplace_lat"], values["workplace_lng"]), (data.lat, data.lng)).meters
        within = distance <= values["geofence_radius_m"]
        distance = round(distance, 1)
    keep = has_position and mine and values["require_location"] and source == Record.Source.PERSONAL
    return {
        "lat": data.lat if keep else None,
        "lng": data.lng if keep else None,
        "accuracy_m": data.accuracy_m if has_position else None,
        "distance_m": distance,
        "within_radius": within,
    }


def _check_radius(values: dict, source: str, where: dict[str, Any], mine: bool) -> None:
    """ATTENDANCE-F03: a personal device must be within the radius when the business asks for it.

    Only for the person's own clock-in: a manager clocking someone else vouches for them (ATTENDANCE-F12, as
    Homebase and Deputy), wherever the manager is."""
    if not mine or not values["require_location"] or source != Record.Source.PERSONAL:
        return
    if not values["workplace_set"]:
        raise Conflict(str(WORKPLACE_NOT_SET), code="attendance.workplace_not_set")
    if where["distance_m"] is None:
        raise Conflict(str(LOCATION_REQUIRED), code="attendance.location_required")
    if not where["within_radius"]:
        raise Conflict(
            str(OUTSIDE_RADIUS) % {"distance": round(where["distance_m"]), "radius": values["geofence_radius_m"]},
            code="attendance.outside_radius",
        )
