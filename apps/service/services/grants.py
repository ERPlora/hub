"""Vouchers sold (SERVICE-F14, F17, F18, F21, F28): granted, voided, adjusted and spent, each write locking the
voucher's row first and reading its balance again afterwards.
"""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.customer.queries.reads import find_customer
from apps.service import grant_card
from apps.service import events
from apps.service.models.catalog import Assignment, Service
from apps.service.models.grants import Grant, GrantAdjustment, Redemption
from apps.service.queries.catalog import find_service
from apps.service.queries.grant_checks import redeem_refusal, void_refusal
from apps.service.queries.grants import balance, find_grant, load_grant, lock_grant, session_value
from apps.service.queries.packages import PACKAGE_NOT_FOUND, find_package
from apps.service.schemas.grants import AdjustIn, GrantIn, GrantOut, RedeemIn, RedemptionOut, VoidIn
from apps.service.services.grant_sales import charged_on, tell_sales
from apps.service.services.writes import _actor
from apps.staff.models import Member
from apps.staff.queries.reads import resolve_member

GRANT_ALREADY_VOIDED = _("That voucher was already voided.")
GRANT_IN_USE = _("That voucher was already used: it cannot be voided.")
GRANT_UNLIMITED = _(
    "That voucher has no session limit: there are no sessions to add or remove."
)
GRANT_NO_EXPIRY = _("That voucher never expires: there is no expiry to extend.")
GRANT_BELOW_USED = _("You cannot take away more sessions than the customer has left.")

#: Why a session cannot be spent (queries.grant_checks.redeem_refusal) → its code and its message.
REDEEM_REFUSALS = {
    "voided": (
        "service.grant_voided",
        _("This voucher was voided: it can no longer be used."),
    ),
    "expired": ("service.grant_expired", _("This voucher has expired.")),
    "no_uses_left": (
        "service.grant_no_uses_left",
        _("This voucher has no sessions left."),
    ),
    "does_not_cover_service": (
        "service.grant_does_not_cover_service",
        _(
            "This voucher does not cover that service. A voucher of haircuts pays for haircuts, not for the shampoo."
        ),
    ),
}


def _grant_payload(grant: Grant) -> dict:
    return {
        "id": str(grant.id),
        "package_id": str(grant.package_id),
        "customer_id": str(grant.customer_id),
    }


@operation(
    "service.grant.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.grant_package",
    input=GrantIn,
    output=GrantOut,
    expose_api=True,
    ai={
        "description": "Grant (sell) a voucher of the catalog to a customer (by name or phone), with the amount paid "
        "and the sale that charged it (and its line, if the sale charged several): its uses and validity are frozen "
        "and its expiry counts from the purchase. If it was charged at the till, say the sale: without it, its "
        "sessions count for nobody's commission.",
        "risk": "normal",
        "summary": grant_card.summary,
        "asks": {
            "en": ("sell Inés the five-massage voucher", "Pilar has bought the laser pack, give it to her"),
            "es": ("véndele a Inés el bono de cinco masajes", "Pilar ha comprado el bono de láser, dáselo"),
        },
    },
)
def create_grant(ctx: OperationContext, data: GrantIn) -> dict:
    package = find_package(data.package_id, data.package, hold=True)
    if not package.is_active:
        raise NotFound(str(PACKAGE_NOT_FOUND), code="service.package_not_found")
    customer = find_customer(ctx, data.customer_id, data.customer, lock=True)
    # A voucher given away charged nothing: no line has anything to leave out.
    sold_on = (
        charged_on(ctx, data.sale_id, data.sale_line_id, data.amount)
        if data.amount and (data.sale_id or data.sale_line_id)
        else None
    )
    grant = Grant.objects.create(
        package=package,
        customer=customer,
        granted_at=data.granted_at or timezone.now(),
        sale_id=sold_on.sale_id if sold_on else data.sale_id,
        sale_line_id=sold_on.line_id if sold_on else None,
        amount=data.amount,
        net_amount=data.net_amount,
        tax_amount=data.tax_amount,
        max_uses=package.max_uses,
        validity_days=package.validity_days,
        note=data.note,
        created_by=_actor(ctx),
    )
    record_event(ctx, events.GRANT_GRANTED, _grant_payload(grant))
    return load_grant(ctx, grant.id)


@operation(
    "service.grant.void",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.void_grant",
    input=VoidIn,
    output=GrantOut,
    expose_api=True,
    ai={
        "description": "Void a voucher sold by mistake, with the reason: only one never used. It can no longer be "
        "spent and stays as a trail; no money moves (a refund is done in Sales). The voucher's id comes from "
        "service.grant.list (by its owner's name or phone, or its package).",
        "risk": "high",
        "asks": {
            "en": ("void Inés's voucher, it was sold by mistake", "void the voucher we just sold to Pilar"),
            "es": (
                "el bono de láser de Inés fue una equivocación, anúlalo",
                "anula el bono que acabamos de venderle a Pilar",
            ),
        },
    },
)
def void_grant(ctx: OperationContext, data: VoidIn) -> dict:
    lock_grant(data.id)
    grant = find_grant(data.id)
    refusal = void_refusal(grant)
    if refusal == "already_voided":
        raise Conflict(str(GRANT_ALREADY_VOIDED), code="service.grant_already_voided")
    if refusal == "in_use":
        raise Conflict(str(GRANT_IN_USE), code="service.grant_in_use")
    Grant.objects.filter(pk=grant.pk).update(
        voided_at=timezone.now(),
        voided_by=_actor(ctx),
        void_reason=data.reason,
        updated_at=timezone.now(),
    )
    if grant.sale_line_id is not None:
        tell_sales(
            ctx, "sale.sale.voucher_unsold", {"line_id": grant.sale_line_id, "amount": grant.amount}
        )
    record_event(ctx, events.GRANT_VOIDED, _grant_payload(grant))
    return load_grant(ctx, grant.id)


@operation(
    "service.grant.adjust",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.adjust_grant",
    input=AdjustIn,
    output=GrantOut,
    expose_api=True,
    ai={
        "description": "Adjust a voucher sold, with the reason: give sessions or a later expiry as a courtesy, or take "
        "sessions to correct its balance (never more than are left). It stays as a movement. The voucher's id comes "
        "from service.grant.list (by its owner's name or phone, or its package).",
        "risk": "high",
        "asks": {
            "en": ("give Inés two free sessions on her voucher", "extend Pilar's voucher by a month"),
            "es": ("regálale dos sesiones a Inés en su bono", "alarga un mes la caducidad del bono de Pilar"),
        },
    },
)
def adjust_grant(ctx: OperationContext, data: AdjustIn) -> dict:
    lock_grant(data.id)
    grant = find_grant(data.id)
    if grant.voided_at is not None:
        raise Conflict(str(GRANT_ALREADY_VOIDED), code="service.grant_already_voided")
    if data.uses_delta and grant.max_uses is None:
        raise Conflict(str(GRANT_UNLIMITED), code="service.grant_unlimited")
    if data.days_delta and grant.validity_days is None:
        raise Conflict(str(GRANT_NO_EXPIRY), code="service.grant_no_expiry")
    remaining = balance(grant).remaining
    if data.uses_delta < 0 and remaining is not None and -data.uses_delta > remaining:
        raise Conflict(str(GRANT_BELOW_USED), code="service.grant_adjust_below_used")
    GrantAdjustment.objects.create(
        grant=grant,
        uses_delta=data.uses_delta,
        days_delta=data.days_delta,
        reason=data.reason,
        actor=_actor(ctx),
    )
    record_event(
        ctx,
        events.GRANT_ADJUSTED,
        {
            "id": str(grant.id),
            "uses_delta": data.uses_delta,
            "days_delta": data.days_delta,
        },
    )
    return load_grant(ctx, grant.id)


@operation(
    "service.grant.redeem",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.redeem_package",
    input=RedeemIn,
    output=RedemptionOut,
    expose_api=True,
    ai={
        "description": "Spend one session of a voucher sold (outside the till), optionally on a service it covers, "
        "saying the professional who did it (its value counts in their production and commission; without one it "
        "counts for nobody), and linked to an appointment or a sale. Refused when voided, expired or without sessions "
        "left. The voucher's id comes from service.grant.list (by its owner's name or phone, or its package).",
        "risk": "normal",
        "asks": {
            "en": ("use one session of Inés's massage voucher", "mark a session of Pilar's voucher as spent"),
            "es": (
                "gasta una sesión del bono de masajes de Inés",
                "Paloma ha venido a su masaje, réstale una sesión del bono",
            ),
        },
    },
)
def redeem(ctx: OperationContext, data: RedeemIn) -> dict:
    service = (
        find_service(data.service_id, data.service)
        if (data.service_id or data.service)
        else None
    )
    member = resolve_member(data.member_id, data.member) if (data.member_id or data.member) else None
    lock_grant(data.id)
    grant = find_grant(data.id)
    state = balance(grant)
    refusal = redeem_refusal(grant, state, service)
    if refusal:
        code, message = REDEEM_REFUSALS[refusal]
        raise Conflict(str(message), code=code)
    session = Redemption.objects.create(
        grant=grant,
        service=service,
        member=member,
        appointment_id=data.appointment_id,
        sale_id=data.sale_id,
        note=data.note,
        actor=_actor(ctx),
        value=session_value(grant.id),
    )
    if member is not None:
        tell_sales(
            ctx,
            "sale.voucher_session.record",
            {"session_id": session.id, "staff_id": member.id, "value": _worth(session, service, member)},
        )
    record_event(
        ctx,
        events.GRANT_REDEEMED,
        {
            "id": str(grant.id),
            "redemption_id": str(session.id),
            "service_id": str(service.id) if service else None,
        },
    )
    return {
        "id": session.id,
        "grant_id": grant.id,
        "service_id": service.id if service else None,
        "service_name": service.name if service else None,
        "member_id": member.id if member else None,
        "member_name": member.full_name if member else None,
        "redeemed_at": session.redeemed_at,
        "remaining": None if state.remaining is None else state.remaining - 1,
    }


def _worth(session: Redemption, service: Service | None, member: Member) -> int:
    """What a session spent outside the till is worth to who did it (SALE-F28): its value (SERVICE-F24). An unlimited
    voucher has no sessions to divide its price by: as the till counts it, at the price of its line, the price the
    professional charges for the service (their own, else the service's); without the service said, nothing."""
    if session.value is not None:
        return session.value
    if service is None:
        return 0
    own = (
        Assignment.objects.filter(service=service, member=member, is_active=True)
        .values_list("custom_price", flat=True)
        .first()
    )
    return service.price if own is None else own
