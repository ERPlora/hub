"""The vouchers a customer can pay a service with at the till, the one to spend first on top (SERVICE-F22)."""

import datetime as dt

from django.db.models import DateTimeField, Min, OuterRef, Q, Subquery
from django.utils import timezone
from live.context import OperationContext
from live.operations import operation

from apps.customer.queries.reads import find_customer
from apps.service.models.grants import Grant, Redemption
from apps.service.queries.catalog import find_service
from apps.service.queries.grants import Balance, balance, grants, live_sessions
from apps.service.schemas.tender import TenderOptionPage, TenderOptionsIn


@operation(
    "service.grant.tender_options",
    kind="query",
    permission="service.redeem_package",
    input=TenderOptionsIn,
    output=TenderOptionPage,
    expose_api=True,
    ai={
        "description": "The vouchers a customer (by id, name or phone) owns that can pay a line of a service now: they "
        "cover it, have sessions left and have not expired. The first one is the one the till spends first, with why: "
        "counted sessions before unlimited, then the one expiring first, the one already started, the one with fewest "
        "sessions left, the one bought first.",
        "asks": {
            "en": ("which of Inés's vouchers would pay for a massage?", "what vouchers can Pilar use for her colour?"),
            "es": (
                "¿qué bonos de Inés le sirven para el masaje?",
                "¿qué bono se gastaría primero si Pilar viene a hacerse el tinte?",
            ),
        },
    },
)
def tender_options(ctx: OperationContext, params: TenderOptionsIn) -> dict:
    card = find_customer(ctx, params.customer_id, params.customer, live=False)
    service = find_service(params.service_id, params.service)
    now = timezone.now()
    started = (
        Redemption.objects.filter(live_sessions(now), grant=OuterRef("pk"))
        .values("grant")
        .annotate(first=Min("redeemed_at"))
        .values("first")[:1]
    )
    candidates = (
        grants(now)
        .filter(
            Q(customer=card) | Q(customer__merged_into=card),
            voided_at__isnull=True,
            package__items__service=service,
        )
        .annotate(first_used=Subquery(started, output_field=DateTimeField()))
    )
    eligible = []
    for grant in candidates:
        state = balance(grant, now)
        if state.is_expired or (state.remaining is not None and state.remaining <= 0):
            continue
        eligible.append((grant, state))
    eligible.sort(key=lambda option: _tender_rank(*option))
    reason = _first_reason(eligible)
    rows = [
        {
            "grant_id": grant.id,
            "package_id": grant.package_id,
            "package_name": grant.package.name,
            "granted_at": grant.granted_at,
            "max_uses": state.max_uses,
            "used": grant.used,
            "remaining_before": state.remaining,
            "remaining_after": None if state.remaining is None else state.remaining - 1,
            "is_unlimited": state.max_uses is None,
            "expires_at": state.expires_at,
            "is_default": position == 0,
            "default_reason": reason if position == 0 else "",
            "candidate_count": len(eligible),
        }
        for position, (grant, state) in enumerate(eligible)
    ]
    return {
        "rows": rows[params.offset : params.offset + params.limit],
        "total": len(rows),
        "limit": params.limit,
        "offset": params.offset,
    }


_LAST = dt.datetime.max.replace(tzinfo=dt.UTC)


def _tender_rank(grant: Grant, state: Balance) -> tuple:
    """The order the till spends vouchers in (the old module's tie-break)."""
    return (
        state.max_uses is None,
        state.expires_at or _LAST,
        grant.first_used or _LAST,
        state.remaining if state.remaining is not None else 0,
        grant.granted_at,
        grant.id,
    )


#: The steps of the tie-break, in order, and the reason each one gives when it decides.
_TIE_BREAK = (
    (lambda grant, state: state.max_uses is None, "finite_before_unlimited"),
    (lambda grant, state: state.expires_at, "expires_first"),
    (lambda grant, state: grant.first_used, "already_started"),
    (lambda grant, state: state.remaining, "fewest_sessions_left"),
    (lambda grant, state: grant.granted_at, "oldest_voucher"),
)


def _first_reason(eligible: list) -> str:
    """Why the first option goes first: the first step of the tie-break that tells it from the second."""
    if not eligible:
        return ""
    if len(eligible) == 1:
        return "only_option"
    first, second = eligible[0], eligible[1]
    for step, reason in _TIE_BREAK:
        if step(*first) != step(*second):
            return reason
    return "stable_order"
