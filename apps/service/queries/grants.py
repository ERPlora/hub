"""The vouchers sold: one found and held by its id, its balance, computed from its sessions and its
adjustments, its rows and its reads."""

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

from babel.dates import format_date
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.customer.queries import find_customer
from apps.service.models import Grant, GrantAdjustment, Redemption
from apps.service.queries.packages import find_package
from apps.service.queries.reads import CUSTOMER_VIEW, _page
from apps.service.schemas import (
    ByIdIn,
    GrantDetailOut,
    SessionDetailOut,
    SessionRefIn,
    GrantListIn,
    GrantPage,
    OrphanPage,
    PageIn,
)
from base.business import babel_locale, business_zone

SESSION_NOT_FOUND = _("That voucher session does not exist in this business.")

GRANT_NOT_FOUND = _("That voucher sale does not exist in this business.")


def lock_grant(grant_id: UUID) -> None:
    """Locks the row of a voucher sold until the end of the command's transaction (or ``NotFound``)."""
    if not Grant.objects.select_for_update().filter(pk=grant_id).exists():
        raise NotFound(str(GRANT_NOT_FOUND), code="service.grant_not_found")


def find_grant(grant_id: UUID) -> Grant:
    """A voucher sold with its balance read now (after ``lock_grant`` in a command: what the lock let through)."""
    grant = grants().filter(pk=grant_id).first()
    if grant is None:
        raise NotFound(str(GRANT_NOT_FOUND), code="service.grant_not_found")
    return grant


def _adjusted(field: str, condition: Q | None = None):
    rows = GrantAdjustment.objects.filter(grant=OuterRef("pk"))
    if condition is not None:
        rows = rows.filter(condition)
    total = rows.values("grant").annotate(total=Sum(field)).values("total")[:1]
    return Coalesce(
        Subquery(total, output_field=IntegerField()),
        Value(0),
        output_field=IntegerField(),
    )


def live_sessions(now: dt.datetime) -> Q:
    """The sessions that count against a balance ``now``: delivered, or held and inside their deadline."""
    return Q(status=Redemption.Status.CONSUMED) | Q(
        status=Redemption.Status.HELD, hold_until__gt=now
    )


def grants(now: dt.datetime | None = None):
    """Vouchers sold with what their balance needs ``now``: sessions spent or held, sessions added and
    taken, days added."""
    now = now or timezone.now()
    spent = (
        Redemption.objects.filter(live_sessions(now), grant=OuterRef("pk"))
        .values("grant")
        .annotate(n=Count("id"))
        .values("n")[:1]
    )
    return Grant.objects.select_related("package", "customer").annotate(
        used=Coalesce(
            Subquery(spent, output_field=IntegerField()),
            Value(0),
            output_field=IntegerField(),
        ),
        uses_added=_adjusted("uses_delta", Q(uses_delta__gt=0)),
        uses_taken=_adjusted("uses_delta", Q(uses_delta__lt=0)),
        days_added=_adjusted("days_delta"),
    )


@dataclass(frozen=True)
class Balance:
    max_uses: int | None
    remaining: int | None
    expires_at: dt.datetime | None
    is_expired: bool


def balance(grant: Grant, now: dt.datetime | None = None) -> Balance:
    """What a voucher sold (annotated by ``grants()``) has left and when it expires, ``now``."""
    now = now or timezone.now()
    total = (
        None
        if grant.max_uses is None
        else grant.max_uses + grant.uses_added + grant.uses_taken
    )
    expires_at = (
        None
        if grant.validity_days is None
        else grant.granted_at
        + dt.timedelta(days=grant.validity_days + grant.days_added)
    )
    return Balance(
        max_uses=total,
        remaining=None if total is None else total - grant.used,
        expires_at=expires_at,
        is_expired=expires_at is not None and now > expires_at,
    )


def session_value(grant_id: UUID) -> int | None:
    """What the next session delivered of a voucher sold is worth (SERVICE-F24), with its row locked by the caller:
    what is left of the price paid ÷ the sessions not delivered yet, half up, so 100.00 in 3 sessions is 33.33 + 33.34
    + 33.33 and what is delivered adds up to what was paid, to the cent, through courtesies, corrections and sessions
    given back. An unlimited voucher has no sessions to divide by: ``None``. A paid voucher that does not say the line
    that charged it is worth 0: that money may already count for who sold it (a voucher from before this, one granted
    without its sale), and nothing counts twice."""
    grant = grants().get(pk=grant_id)
    if grant.amount and grant.sale_line_id is None:
        return 0
    total = balance(grant).max_uses
    if total is None:
        return None
    delivered = Redemption.objects.filter(grant_id=grant_id, status=Redemption.Status.CONSUMED).aggregate(
        count=Count("id"), value=Coalesce(Sum("value"), 0)
    )
    amount_left = max(grant.amount - delivered["value"], 0)
    sessions_left = max(total - delivered["count"], 1)
    return (2 * amount_left + sessions_left) // (2 * sessions_left)


def _named(*parts: str | None) -> str:
    """How a person tells a voucher or a session apart: what is known of it, what is not left out."""
    return " · ".join(part for part in parts if part)


def _customer_name(ctx: OperationContext, grant: Grant) -> str | None:
    customer = grant.customer
    return (
        customer.name
        if ctx.has(CUSTOMER_VIEW) and customer.deleted_at is None
        else None
    )


def grant_row(
    ctx: OperationContext, grant: Grant, now: dt.datetime | None = None
) -> dict:
    fields = (
        "id",
        "package_id",
        "customer_id",
        "granted_at",
        "source",
        "sale_id",
        "amount",
        "net_amount",
        "tax_amount",
        "note",
        "voided_at",
        "voided_by",
        "void_reason",
        "used",
        "uses_added",
        "days_added",
    )
    state = balance(grant, now)
    voided = grant.voided_at is not None
    return {
        **{field: getattr(grant, field) for field in fields},
        "package_name": grant.package.name,
        "customer_name": _customer_name(ctx, grant),
        "customer_deleted_at": grant.customer.deleted_at,
        "uses_removed": -grant.uses_taken,
        "max_uses": state.max_uses,
        "remaining": state.remaining,
        "expires_at": state.expires_at,
        "is_expired": state.is_expired,
        "status": "voided" if voided else "active",
        "can_void": not voided and grant.used == 0,
        "can_adjust": not voided
        and (grant.max_uses is not None or grant.validity_days is not None),
    }


def session_rows(ids) -> list[dict]:
    """``SessionOut`` of each session, in the order given, with its voucher's balance read now."""
    wanted = list(dict.fromkeys(ids))
    now = timezone.now()
    sessions = {
        session.id: session for session in Redemption.objects.filter(pk__in=wanted)
    }
    owners = {
        grant.id: grant
        for grant in grants(now).filter(
            pk__in={session.grant_id for session in sessions.values()}
        )
    }
    rows = []
    for session_id in wanted:
        session = sessions[session_id]
        grant = owners[session.grant_id]
        state = balance(grant, now)
        rows.append(
            {
                "id": session.id,
                "grant_id": grant.id,
                "package_id": grant.package_id,
                "package_name": grant.package.name,
                "customer_id": grant.customer_id,
                "service_id": session.service_id,
                "status": session.status,
                "order_line_id": session.order_line_id,
                "hold_until": session.hold_until,
                "sale_id": session.sale_id,
                "value": session.value,
                "remaining": state.remaining,
                "voucher_expired": state.is_expired,
            }
        )
    return rows


def load_grant(ctx: OperationContext, grant_id: UUID) -> dict:
    return grant_row(ctx, find_grant(grant_id))


@operation(
    "service.grant.list",
    kind="query",
    permission="service.view_package_balance",
    input=GrantListIn,
    output=GrantPage,
    expose_api=True,
    ai={
        "description": "List the vouchers sold, most recent first: the ones of a package, or the ones a customer owns "
        "(by name or phone), with the sessions used and left, the expiry and whether it was voided.",
        "asks": {
            "en": ("which vouchers has Inés bought?", "who has bought the laser pack?"),
            "es": ("¿qué bonos tiene comprados Inés?", "¿quién ha comprado el bono de láser?"),
        },
    },
)
def list_grants(ctx: OperationContext, params: GrantListIn) -> dict:
    sold = grants()
    if params.package_id or params.package:
        sold = sold.filter(
            package=find_package(
                params.package_id, params.package, include_deleted=True
            )
        )
    if params.customer_id or params.customer:
        card = find_customer(ctx, params.customer_id, params.customer, live=False)
        # A card merged into this one (Customers keeps the chain one level deep) still shows its
        # vouchers until the reaction to customer.customer.merged moves them.
        sold = sold.filter(Q(customer=card) | Q(customer__merged_into=card))
    if params.status is not None:
        sold = sold.filter(voided_at__isnull=params.status == "active")
    now = timezone.now()
    return _page(
        sold.order_by("-granted_at", "-id"),
        params,
        lambda grant: grant_row(ctx, grant, now),
    )


@operation(
    "service.grant.get",
    kind="query",
    permission="service.view_package_balance",
    input=ByIdIn,
    output=GrantDetailOut,
    expose_api=True,
    ai={
        "description": "Get one voucher sold by its id: its package, its owner, the day it was sold and its balance. "
        "The voucher's id comes from service.grant.list (by its owner's name or phone, or its package).",
        "asks": {
            "en": ("get me the details of the voucher we sold Pilar", "what's the balance of Inés's laser voucher?"),
            "es": ("dame los detalles del bono que le vendimos a Pilar", "¿qué saldo tiene el bono de láser de Inés?"),
        },
    },
)
def get_grant(ctx: OperationContext, data: ByIdIn) -> dict:
    grant = find_grant(data.id)
    sold_on = format_date(timezone.localdate(grant.granted_at, business_zone()), "medium", locale=babel_locale(ctx.language))
    return {**grant_row(ctx, grant), "label": _named(grant.package.name, _customer_name(ctx, grant), sold_on)}


@operation(
    "service.session.get",
    kind="query",
    permission="service.view_package_balance",
    input=SessionRefIn,
    output=SessionDetailOut,
    expose_api=True,
    ai={
        "description": "Get one session of a voucher sold by its id: the voucher it comes from, its owner, the service "
        "it pays and whether it is held, spent, released, expired or returned. The id of the session a line of a check "
        "holds is that line's voucher_session_id, from sale.order.get.",
        "asks": {
            "en": ("is that session of Inés's voucher still held?", "what happened to that voucher session?"),
            "es": (
                "¿en qué estado está la sesión del bono de Inés?",
                "¿esa sesión del bono ya se gastó o sigue retenida?",
            ),
        },
    },
)
def get_session(ctx: OperationContext, data: SessionRefIn) -> dict:
    session = Redemption.objects.select_related("service", "grant__package", "grant__customer").filter(pk=data.id).first()
    if session is None:
        raise NotFound(str(SESSION_NOT_FOUND), code="service.session_not_found")
    service = session.service.name if session.service else None
    label = _named(session.grant.package.name, _customer_name(ctx, session.grant), service)
    return {**session_rows([session.id])[0], "label": label}


@operation(
    "service.grant.list_orphans",
    kind="query",
    permission="service.view_orphan_grant",
    input=PageIn,
    output=OrphanPage,
    expose_api=True,
    ai={
        "description": "List the live vouchers whose customer card was deleted or erased, most recent first, with "
        "what is left and the customer's reference (no personal data).",
        "asks": {
            "en": ("which vouchers have no customer left?", "show me the vouchers whose client was erased"),
            "es": ("¿qué bonos se han quedado sin clienta?", "enséñame los bonos de fichas borradas"),
        },
    },
)
def list_orphans(ctx: OperationContext, params: PageIn) -> dict:
    orphans = grants().filter(
        voided_at__isnull=True,
        customer__deleted_at__isnull=False,
        customer__merged_into__isnull=True,
    )
    now = timezone.now()

    def row(grant: Grant) -> dict:
        state = balance(grant, now)
        return {
            "id": grant.id,
            "package_id": grant.package_id,
            "package_name": grant.package.name,
            "customer_id": grant.customer_id,
            "customer_deleted_at": grant.customer.deleted_at,
            "granted_at": grant.granted_at,
            "amount": grant.amount,
            "remaining": state.remaining,
            "is_expired": state.is_expired,
        }

    return _page(orphans.order_by("-customer__deleted_at", "-id"), params, row)
