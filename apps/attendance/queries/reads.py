"""What every read of the time clock shares, and services/ too: who reads someone else's days, the settings until the
business saves its own, a person's name, the business's calendar day and how a list pages."""

import datetime as dt

from django.db.models import Q
from django.utils import timezone
from live.context import OperationContext

from apps.attendance.models import AttendanceSettings
from base.models import HubUser
from base.business import business_zone

from .people import actor_user

VIEW_ALL = "attendance.view_all"
#: Who reads someone else's working day: whoever sees the team, and whoever may correct it.
READS_ANY_DAY = (VIEW_ALL, "attendance.correct")
#: Who reads someone else by id: whoever reads any day, and whoever clocks others in and out.
READS_ANY_PERSON = (*READS_ANY_DAY, "attendance.clock_others")
#: The settings until the business saves its own (the old module's table defaults).
DEFAULTS = {
    "require_location": False,
    "geofence_radius_m": 100,
    "workplace_lat": None,
    "workplace_lng": None,
    "auto_close_after_hours": 12,
}


def user_name(person: HubUser | None) -> str:
    if person is None:
        return ""
    return (person.name or person.username).strip()


def saved_settings() -> AttendanceSettings | None:
    return AttendanceSettings.objects.filter(slot=1).first()


def settings_values(row: AttendanceSettings | None) -> dict:
    values = dict(DEFAULTS)
    if row is not None:
        values.update({key: getattr(row, key) for key in DEFAULTS})
    return {
        **values,
        "workplace_set": values["workplace_lat"] is not None
        and values["workplace_lng"] is not None,
        "saved": row is not None,
        "updated_at": row.updated_at if row is not None else None,
    }


def review_hours() -> int:
    """After how many hours an open day waits for review (the settings, 12 until saved)."""
    return settings_values(saved_settings())["auto_close_after_hours"]


def _reads_any(ctx: OperationContext, permissions: tuple[str, ...]) -> bool:
    return any(ctx.has(permission) for permission in permissions)


def _own_days(ctx: OperationContext) -> Q | None:
    user = actor_user(ctx)
    return None if user is None else Q(member__user_id=user.pk)


def _page(rows: list, total: int, params) -> dict:
    return {
        "rows": rows,
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
    }


def business_date(instant: dt.datetime) -> dt.date:
    """The business's calendar day of an instant, on its clock (hub#779)."""
    return timezone.localdate(instant, business_zone())
