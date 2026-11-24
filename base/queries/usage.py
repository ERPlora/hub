"""What a business uses of its plan (``base.plan.usage``, and the bell's reasons to upgrade) and what each hub used on
a night, for the SaaS (``base.usage.list``)."""

import dataclasses
import datetime as dt
from collections.abc import Iterable
from typing import Any

from django.db.models import Q, Max, Min, Sum
from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import OperationError
from live.operations import AI, INTERNAL, operation

from base import activation, files, home, meter
from base.people import FREE_ROLES
from base.apps_on import active_apps
from base.models import Hub, Membership
from base.models.sessions import SessionOwner
from base.permissions import ADMINISTER_HUB
from base.registry import internal_only
from base.schemas.usage import PlanUsageIn, PlanUsageOut, UsageListIn, UsageListOut
from base.tenancy import limits as tenancy_limits
from control.models import HubActivityDaily, HubUsageDaily, HubVisit, UsageRun

from .apps import app_limit


#: From here on what a plan includes is close to its limit: for the files, the same number as erplora.com's panel
#: (``STORAGE_WARNING_PERCENT``), so both say the same of the same figure.
NEAR_PERCENT = 80
#: Who counts as active now, among all the tasks; a window of activity, not presence.
ACTIVE_NOW = dt.timedelta(minutes=5)
#: The days the requests with no room are told for: today and the 6 before it.
BUSY_WINDOW_DAYS = 7


@operation(
    "base.plan.usage",
    kind="query",
    permission=ADMINISTER_HUB,
    input=PlanUsageIn,
    output=PlanUsageOut,
    ai=AI(
        description=(
            "Reads what this business uses of its plan and whether it should upgrade: the plan it is on, the space its "
            "files take up, its apps, people and devices, and the messages of its apps this month, each against what the "
            "plan includes; its capacity (what it does at once against what it really has, and the times it fell short "
            "in the last 7 days); the requests served this month, the people active now and in 30 days, and the size of "
            "its database. A figure that is null has not been measured yet: say so, never read it as a zero. The "
            "assistant's own messages of the month are read with base.assistant.usage. Files and the database are "
            "measured every night."
        ),
        asks={
            "en": (
                "how much space do I have left?",
                "how many requests have we had this month?",
                "how many people are active now?",
                "does my plan fall short?",
            ),
            "es": (
                "¿cuánto espacio me queda?",
                "¿cuántas peticiones llevamos este mes?",
                "¿cuántas personas están usando el Hub ahora?",
                "¿se me queda corto el plan?",
            ),
        },
    ),
)
def plan_usage(ctx: OperationContext, data: PlanUsageIn) -> dict:
    """What «Usage and plan» of System says: the limits of the plan the SaaS's last photo carries (``plan``:
    ``max_users``, ``max_devices``, ``max_apps``; 0 = no limit) against the people of the business (its active members
    but the accountancy firm: the ones the SaaS counts), the devices in use (those with a session open on this hub: the
    ones the cap on devices keeps)
    and the apps it chose; what the last night measured (``database``, ``files``, the 30 days of ``activity``);
    what is counted during the day (``base.meter``: ``connections``, ``requests``, who is active now), as control has it
    plus what this process has not written yet; and what its apps say their plan includes (``meters``). The assistant's
    messages wait on erplora.com, so the screen asks ``base.assistant.usage`` apart. Memory and CPU cannot be attributed
    to a business. For who runs the business."""
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    state, plan, known = _plan_of(hub)
    people = Membership.objects.filter(host=ctx.scope.key, user__is_active=True).exclude(role__in=FREE_ROLES).count()
    devices = (
        SessionOwner.objects.filter(host=ctx.scope.key, session__expire_date__gt=timezone.now())
        .exclude(device_id=None)
        .values("device_id")
        .distinct()
        .count()
    )
    demo = hub is not None and hub.is_demo
    last = None if demo else _last_night(hub)
    counted = _counted_during_the_day(hub) if hub is not None and not demo else _NOTHING_COUNTED
    shown = {config.label for config in home.shown_modules(demo_hub=demo)}
    return {
        "known": known,
        "demo": demo,
        "plan_slug": _plan_slug(plan) if known else None,
        "people": {"used": people, "limit": _limit(plan, "max_users") if known else None},
        "devices": {"used": devices, "limit": _limit(plan, "max_devices") if known else None},
        "apps": {
            "used": activation.chosen_on(activation.states_of(ctx.scope), among=shown),
            "limit": app_limit(hub) if known else None,
        },
        "database": _database_usage(last),
        "files": _files_usage(state, known, last),
        "connections": _connections_usage(hub, known, counted),
        "requests": {"this_month": counted.requests_this_month, "since": counted.requests_since},
        "activity": _activity_usage(hub, demo, last, counted),
        "meters": _apps_meters(ctx, hub, home.home_modules(active_apps(ctx.scope), demo_hub=demo)),
    }


def _plan_of(hub: Hub | None) -> tuple[dict, dict | None, bool]:
    """The hub's photo, the plan in it and whether that plan can be read."""
    state = hub.state if hub is not None and isinstance(hub.state, dict) else {}
    plan = state.get("plan") if isinstance(state.get("plan"), dict) else None
    return state, plan, plan is not None and all(_is_count(plan.get(field)) for field in ("max_users", "max_devices"))


def _plan_slug(plan: dict) -> str | None:
    slug = plan.get("slug")
    return slug if isinstance(slug, str) and slug else None


def _last_night(hub: Hub | None) -> HubUsageDaily | None:
    """What the last night measured of the hub (``base.usage``)."""
    if hub is None:
        return None
    return HubUsageDaily.objects.filter(hub=hub).order_by("-day").first()


def _database_usage(last: HubUsageDaily | None) -> dict:
    """The size of the business's own database the last night measured (``base.usage``)."""
    return {"bytes": last.db_bytes if last else None, "day": last.day if last else None}


def _is_near(used: int, limit: int) -> bool:
    return used * 100 >= limit * NEAR_PERCENT


def _files_usage(state: dict, known: bool, last: HubUsageDaily | None) -> dict:
    """What the files take up (``s3_bytes``) against the plan's space (BASE-F40, step 3); nothing to compare, no status."""
    limit = files.space_limit(state) if known else None
    used = last.s3_bytes if last else None
    percent = status = None
    if limit is not None and used is not None:
        percent = used * 100 // limit
        status = "full" if used >= limit else "near" if _is_near(used, limit) else "within"
    return {"bytes": used, "day": last.day if last else None, "limit": limit, "percent": percent, "status": status}


@dataclasses.dataclass(frozen=True)
class _Counted:
    """What was counted of a hub during the days (``base.meter``): nothing is ``None``, never a made-up zero."""

    requests_this_month: int | None = None
    requests_since: dt.date | None = None
    peak_today: int | None = None
    busy_last_7_days: int | None = None
    busy_since: dt.date | None = None
    people_now: frozenset[str] = frozenset()


_NOTHING_COUNTED = _Counted()


def _counted_during_the_day(hub: Hub) -> _Counted:
    """What control holds of the hub's days (one query, by its one index) plus what this process has not written yet. A
    count that started after the first day of its period says since when."""
    today = timezone.now().astimezone(dt.UTC).date()
    month_starts = today.replace(day=1)
    week_starts = today - dt.timedelta(days=BUSY_WINDOW_DAYS - 1)
    kept = HubActivityDaily.objects.filter(hub=hub).aggregate(
        first=Min("day"),
        requests=Sum("requests", filter=Q(day__gte=month_starts)),
        busy=Sum("busy_requests", filter=Q(day__gte=week_starts)),
        peak=Max("peak_connections", filter=Q(day=today)),
    )
    pending = meter.unflushed(hub.pk, hub.slug)
    first = kept["first"] or (today if pending != meter.Unflushed() else None)
    return _Counted(
        requests_this_month=None if first is None else (kept["requests"] or 0) + pending.requests,
        requests_since=first if first is not None and first > month_starts else None,
        # A row with no transaction yet is no measure either: a zero here would be a made-up one.
        peak_today=max(kept["peak"] or 0, pending.peak) or None,
        busy_last_7_days=None if first is None else (kept["busy"] or 0) + pending.busy,
        busy_since=first if first is not None and first > week_starts else None,
        people_now=pending.people,
    )


def _connections_usage(hub: Hub | None, known: bool, counted: _Counted) -> dict:
    """Today's highest against what it really has (BASE-F40), by the limiter's own rule (``limits.hub_limits``): a known
    plan whose photo lacks its limits gets Free's, so the screen says that, never «no limit», and ERPlora's own hub, with no
    plan to know, what its row gives it. And the times it fell short: with limits of 1, 3 or 6 a percentage says nothing, a
    Free plan's first operation of the day is its 100 %."""
    platform = hub is not None and hub.is_platform
    limits = (tenancy_limits.hub_limits(hub) or tenancy_limits.FREE) if known or platform else None
    return {
        "peak_today": counted.peak_today,
        "limit": limits.max_transactions if limits else None,
        "busy_last_7_days": counted.busy_last_7_days,
        "busy_since": counted.busy_since,
        "bigger_plan_gives_more": tenancy_limits.bigger_plan_gives_hub_more(hub) if known else False,
    }


def _activity_usage(hub: Hub | None, demo: bool, last: HubUsageDaily | None, counted: _Counted) -> dict:
    """Who is active now, in the last visits of every task (yesterday's too: a day may have just changed) and in this
    process's memory, and the people of the 30 days the last night measured."""
    now = timezone.now().astimezone(dt.UTC)
    today = now.date()
    active_now = None
    if hub is not None and not demo:
        recent = HubVisit.objects.filter(
            host=hub.slug,
            day__in=(today, today - dt.timedelta(days=1)),
            last_seen_at__gte=now - ACTIVE_NOW,
        ).values_list("saas_user_id", flat=True)
        active_now = len(set(recent) | counted.people_now)
    return {
        "active_now": active_now,
        "last_30_days": last.active_users_30d if last else None,
        "day": last.day if last else None,
    }


def _apps_meters(ctx: OperationContext, hub: Hub | None, modules: Iterable[Any]) -> list[dict]:
    """What the apps on say their plan includes (``base.home.plan_meters``), read in the business's own database: none in
    a demo, which is not measured."""
    return [] if hub is None or hub.is_demo else home.plan_meters(ctx, modules)


def _plan_motives(ctx: OperationContext, hub: Hub | None, modules: Iterable[Any]) -> int:
    """How many reasons to upgrade the bell can tell (BASE-F40) without asking erplora.com, so never the assistant's: the
    files close to the plan's space or full, a capacity that fell short when a bigger plan would give more, and the
    meters of the apps close to what the plan includes. People, devices and apps at their limit are none: a Free business
    with its one device in use is fine. None without the plan or in a demo."""
    state, _, known = _plan_of(hub)
    if not known or hub is None or hub.is_demo:
        return 0
    files_status = _files_usage(state, known, _last_night(hub))["status"]
    capacity = _connections_usage(hub, known, _counted_during_the_day(hub))
    fell_short = bool(capacity["busy_last_7_days"]) and capacity["bigger_plan_gives_more"]
    meters = sum(
        1
        for meter in _apps_meters(ctx, hub, modules)
        if meter["limit"] and meter["used"] is not None and _is_near(meter["used"], meter["limit"])
    )
    return int(files_status in ("near", "full")) + int(fell_short) + meters


# Not an assistant tool: the platform's door (/internal, the SaaS), no person.
@operation("base.usage.list", kind="query", permission=None, input=UsageListIn, output=UsageListOut, ai=INTERNAL)
def usage_list(ctx: OperationContext, data: UsageListIn) -> dict[str, Any]:
    """One page of what the hubs with their own database used on ``data.day`` (``GET /internal/usage``, the SaaS's
    ``collect_hub_usage``), by hub id, after ``data.cursor``; 409 ``usage_not_ready`` until that night was measured to
    its end (``base.usage``). For the platform only."""
    from base import usage

    internal_only(ctx)
    if not UsageRun.objects.filter(day=data.day, finished_at__isnull=False).exists():
        raise OperationError(gettext("That day has not been measured yet."), code="usage_not_ready", status=409)
    rows = HubUsageDaily.objects.filter(day=data.day).order_by("hub_id")
    if data.cursor is not None:
        rows = rows.filter(hub_id__gt=data.cursor)
    page = list(rows[: usage.PAGE_SIZE + 1])
    more = len(page) > usage.PAGE_SIZE
    page = page[: usage.PAGE_SIZE]
    activity = {
        row.hub_id: row
        for row in HubActivityDaily.objects.filter(day=data.day, hub_id__in=[row.hub_id for row in page])
    }
    return {
        "day": data.day,
        "hubs": [
            {
                "id": row.hub_id,
                "s3_bytes": row.s3_bytes,
                "db_bytes": row.db_bytes,
                "active_users_1d": row.active_users_1d,
                "active_users_30d": row.active_users_30d,
                "requests": activity[row.hub_id].requests if row.hub_id in activity else None,
                "peak_connections": activity[row.hub_id].peak_connections if row.hub_id in activity else None,
                "busy_requests": activity[row.hub_id].busy_requests if row.hub_id in activity else None,
            }
            for row in page
        ],
        "next_cursor": str(page[-1].hub_id) if more else None,
    }


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _limit(plan: dict, field: str) -> int | None:
    """A limit of the plan; 0 is none."""
    return plan[field] or None
