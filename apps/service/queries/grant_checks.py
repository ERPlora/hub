"""Whether a voucher sold can be voided, adjusted or spent, and why not."""

from live.context import OperationContext
from live.operations import operation

from apps.service.models import Grant, PackageItem, Service
from apps.service.queries.catalog import find_service
from apps.service.queries.grants import Balance, balance, find_grant
from apps.service.schemas import AdjustCheckOut, ByIdIn, RedeemCheckIn, RedeemCheckOut, VoidCheckOut


@operation(
    "service.grant.void_check",
    kind="query",
    permission="service.void_grant",
    input=ByIdIn,
    output=VoidCheckOut,
    expose_api=True,
    ai={
        "description": "Whether a voucher sold can be voided now and, if not, why (already_voided, in_use). The "
        "voucher's id comes from service.grant.list (by its owner's name or phone, or its package).",
        "asks": {
            "en": ("can Inés's voucher still be voided?", "is it too late to void Pilar's voucher?"),
            "es": (
                "¿se puede anular todavía el bono de Inés?",
                "¿el bono de Pilar ya tiene sesiones gastadas o aún se puede anular?",
            ),
        },
    },
)
def void_check(ctx: OperationContext, data: ByIdIn) -> dict:
    grant = find_grant(data.id)
    reason = void_refusal(grant)
    return {
        "id": grant.id,
        "voidable": reason == "",
        "reason": reason,
        "used": grant.used,
    }


def void_refusal(grant: Grant) -> str:
    """Why a voucher sold cannot be voided (``""`` when it can): only an untouched one is."""
    if grant.voided_at is not None:
        return "already_voided"
    if grant.used > 0:
        return "in_use"
    return ""


@operation(
    "service.grant.adjust_check",
    kind="query",
    permission="service.adjust_grant",
    input=ByIdIn,
    output=AdjustCheckOut,
    expose_api=True,
    ai={
        "description": "What can be adjusted on a voucher sold: sessions (if it has a limit) and its expiry (if it has "
        "one). The voucher's id comes from service.grant.list (by its owner's name or phone, or its package).",
        "asks": {
            "en": ("what can I change on Inés's voucher?", "can Pilar's voucher get a later expiry?"),
            "es": (
                "¿el bono de Inés admite más sesiones o más días de caducidad?",
                "¿se le puede alargar la caducidad al bono de Pilar?",
            ),
        },
    },
)
def adjust_check(ctx: OperationContext, data: ByIdIn) -> dict:
    grant = find_grant(data.id)
    state = balance(grant)
    return {
        "id": grant.id,
        "can_add_uses": grant.max_uses is not None,
        "can_extend": grant.validity_days is not None,
        "uses_left": state.remaining,
        "expires_at": state.expires_at,
        "reason": "already_voided" if grant.voided_at is not None else "",
    }


@operation(
    "service.grant.redeem_check",
    kind="query",
    permission="service.redeem_package",
    input=RedeemCheckIn,
    output=RedeemCheckOut,
    expose_api=True,
    ai={
        "description": "Whether a session of a voucher sold can be spent now (optionally on a service) and, if not, "
        "why: voided, expired, no_uses_left or does_not_cover_service. The voucher's id comes from service.grant.list "
        "(by its owner's name or phone, or its package).",
        "asks": {
            "en": ("can Inés's voucher pay for a manicure?", "why can't Pilar's voucher be used?"),
            "es": ("¿le sirve a Inés su bono para una manicura?", "¿por qué no se puede gastar el bono de Pilar?"),
        },
    },
)
def redeem_check(ctx: OperationContext, data: RedeemCheckIn) -> dict:
    grant = find_grant(data.id)
    service = (
        find_service(data.service_id, data.service)
        if (data.service_id or data.service)
        else None
    )
    state = balance(grant)
    reason = redeem_refusal(grant, state, service)
    return {"id": grant.id, "redeemable": reason == "", "reason": reason, "remaining": state.remaining}


def redeem_refusal(grant: Grant, state: Balance, service: Service | None) -> str:
    """Why a session cannot be spent (``""`` when it can), in the order the WORKBOOK says them."""
    if grant.voided_at is not None:
        return "voided"
    if state.is_expired:
        return "expired"
    if state.remaining is not None and state.remaining <= 0:
        return "no_uses_left"
    if (
        service is not None
        and not PackageItem.objects.filter(
            package_id=grant.package_id, service=service
        ).exists()
    ):
        return "does_not_cover_service"
    return ""
