"""The movements of the vouchers sold: each session spent or given back and each adjustment, with who
made it and, for a session of the till, the sale it was spent in."""

import datetime as dt
from uuid import UUID

from django.db.models import Case, DateTimeField, F, Q, When
from django.utils import timezone
from live.context import OperationContext
from live.operations import operation

from apps.service.models.grants import Grant, GrantAdjustment, Redemption
from apps.service.queries.packages import find_package
from apps.service.queries.reads import CUSTOMER_VIEW
from apps.service.queries.sale_numbers import name_the_sales
from apps.service.schemas.movements import MovementListIn, MovementPage
from apps.staff.models import Member


@operation(
    "service.movement.list",
    kind="query",
    permission="service.view_package_balance",
    input=MovementListIn,
    output=MovementPage,
    expose_api=True,
    ai={
        "description": "The movements of a voucher of the catalog, most recent first: every session spent and every "
        "courtesy (adjusted) or correction (corrected), of every customer, with who and why.",
        "asks": {
            "en": ("what has happened with the massage voucher?", "who has spent sessions of the laser pack?"),
            "es": ("¿qué movimientos ha tenido el bono de masajes?", "¿quién ha gastado sesiones del bono de láser?"),
        },
    },
)
def list_movements(ctx: OperationContext, params: MovementListIn) -> dict:
    package = find_package(params.package_id, params.package, include_deleted=True)
    now = timezone.now()
    sessions = (
        Redemption.objects.filter(grant__package=package)
        .select_related("grant__customer", "service", "member")
        .annotate(at=_session_moment(now))
    )
    adjustments = GrantAdjustment.objects.filter(grant__package=package).select_related(
        "grant__customer"
    )
    take = params.offset + params.limit
    latest = list(sessions.order_by("-at", "-id")[:take])
    rows = [_session_row(ctx, session, now) for session in latest]
    rows += [
        _adjustment_row(ctx, adjustment)
        for adjustment in adjustments.order_by("-created_at", "-id")[:take]
    ]
    rows.sort(key=lambda row: (row["at"], row["id"]), reverse=True)
    shown = rows[params.offset : take]
    _name_the_sales(ctx, shown, {session.id: session.order_line_id for session in latest})
    _name_the_members(shown)
    return {
        "rows": shown,
        "total": sessions.count() + adjustments.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


def _movement(ctx: OperationContext, grant: Grant) -> dict:
    customer = grant.customer
    visible = ctx.has(CUSTOMER_VIEW) and customer.deleted_at is None
    return {
        "grant_id": grant.id,
        "customer_id": customer.id,
        "customer_name": customer.name if visible else None,
    }


def _lapsed(now: dt.datetime) -> Q:
    """A hold past its deadline that the hourly task has not marked yet: it reads as expired."""
    return Q(status=Redemption.Status.HELD, hold_until__lte=now)


def _session_moment(now: dt.datetime):
    """When a session took its last step: given back, released or expired, delivered, or held."""
    ended = [
        Redemption.Status.RELEASED,
        Redemption.Status.EXPIRED,
        Redemption.Status.RETURNED,
    ]
    return Case(
        When(status__in=ended, ended_at__isnull=False, then=F("ended_at")),
        When(_lapsed(now), then=F("hold_until")),
        When(
            status=Redemption.Status.CONSUMED,
            settled_at__isnull=False,
            then=F("settled_at"),
        ),
        default=F("redeemed_at"),
        output_field=DateTimeField(),
    )


def session_kind(session: Redemption, now: dt.datetime) -> str:
    if session.status == Redemption.Status.HELD and session.hold_until <= now:
        return Redemption.Status.EXPIRED
    return session.status


def _session_actor(session: Redemption, kind: str, ended: bool) -> str:
    """Who took the session's last step; a hold that lapsed on its own was the platform's."""
    if not ended:
        return session.actor
    if kind == Redemption.Status.EXPIRED:
        return session.ended_by or "system"
    return session.ended_by


def _session_row(ctx: OperationContext, session: Redemption, now: dt.datetime) -> dict:
    kind = session_kind(session, now)
    ended = kind in (
        Redemption.Status.RELEASED,
        Redemption.Status.EXPIRED,
        Redemption.Status.RETURNED,
    )
    return {
        **_movement(ctx, session.grant),
        "id": session.id,
        "kind": kind,
        "at": session.at,
        "service_id": session.service_id,
        "service_name": session.service.name if session.service else None,
        "member_id": session.member_id,
        "member_name": session.member.full_name if session.member else None,
        "sale_id": session.sale_id,
        "appointment_id": session.appointment_id,
        "note": session.note,
        "actor": _session_actor(session, kind, ended),
        "uses_delta": 0 if ended else -1,
        "days_delta": 0,
        "reason": session.return_reason if kind == Redemption.Status.RETURNED else "",
    }


def _adjustment_row(ctx: OperationContext, adjustment: GrantAdjustment) -> dict:
    return {
        **_movement(ctx, adjustment.grant),
        "id": adjustment.id,
        "kind": "corrected" if adjustment.uses_delta < 0 else "adjusted",
        "at": adjustment.created_at,
        "service_id": None,
        "service_name": None,
        "member_id": None,
        "member_name": None,
        "sale_id": None,
        "appointment_id": None,
        "note": "",
        "actor": adjustment.actor,
        "uses_delta": adjustment.uses_delta,
        "days_delta": adjustment.days_delta,
        "reason": adjustment.reason,
    }


def _served_by(sale, check_line_id: UUID) -> UUID | None:
    """Who served the line of ``sale`` that spent the session: its own professional, else the check's, as Sales
    counts each line's production."""
    line = next((line for line in sale.lines if line.order_line_id == check_line_id), None)
    return (line.staff_id if line else None) or sale.staff_id


def _name_the_sales(ctx: OperationContext, rows: list[dict], check_lines: dict[UUID, UUID | None]) -> None:
    """A session spent in a sale says it by the number Sales names it by; one of the till (it has a check line and
    never says its own professional) also says who served that line. One spent by hand keeps the professional it
    said."""
    sales = name_the_sales(ctx, rows)
    for row in rows:
        sale = sales.get(row["sale_id"])
        check_line_id = check_lines.get(row["id"])
        if sale is not None and check_line_id:
            row["member_id"] = _served_by(sale, check_line_id)


def _name_the_members(rows: list[dict]) -> None:
    """The name of the professional a session of the till got from its sale, as Staff says it now."""
    unnamed = {row["member_id"] for row in rows if row["member_id"] and row["member_name"] is None}
    names = {member.id: member.full_name for member in Member.objects.filter(pk__in=unnamed)}
    for row in rows:
        if row["member_name"] is None and row["member_id"] in names:
            row["member_name"] = names[row["member_id"]]
