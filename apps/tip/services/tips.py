"""Recording, adjusting and voiding a tip (TIP-F03 to TIP-F06): one operation = one transaction, with its event in the
outbox and its line in the open drawer (``drawer.move``)."""

from django.db import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import atomic, operation
from live.outbox import record_event

from apps.sale.models import PaymentMethod, Sale
from apps.sale.queries.business import actor
from apps.sale.queries.payment_methods import find_method
from apps.staff.models import Member
from apps.staff.queries.reads import live_members
from apps.tip import events
from apps.tip.models import Tip
from apps.tip.queries import find_tip, tip_row
from apps.tip.schemas import TipAddIn, TipOut, TipPatchIn, TipVoidIn
from apps.tip.services import drawer

SALE_NOT_FOUND = _("That sale does not exist.")
SALE_VOIDED = _("That sale is voided: it takes no tip.")
MEMBER_NOT_FOUND = _("That person is not on the team: choose someone from Staff.")
ATTEMPT_KEY_REUSED = _("That attempt already recorded another tip.")
ATTEMPT_IN_PROGRESS = _("That tip is being recorded right now: try again in a moment.")
TIP_VOIDED = _("That tip is voided: it no longer changes.")


def _sale(data: TipAddIn) -> Sale | None:
    if data.pool:
        return None
    sale = (Sale.objects.filter(pk=data.sale_id) if data.sale_id else Sale.objects.filter(number=data.sale)).first()
    if sale is None:
        raise Conflict(str(SALE_NOT_FOUND), code="tip.sale_not_found")
    if sale.status != Sale.Status.COMPLETED:
        raise Conflict(str(SALE_VOIDED), code="tip.sale_voided")
    return sale


def _member(named, sale: Sale | None) -> Member | None:
    """Whoever is named, else whoever served the sale; nobody (unassigned) when that one has no live record."""
    wanted = named or (sale.staff_id if sale else None)
    member = live_members().filter(pk=wanted).first() if wanted else None
    if member is None and named:
        raise Conflict(str(MEMBER_NOT_FOUND), code="tip.member_not_found")
    return member


def _the_same(done: Tip, data: TipAddIn) -> Tip:
    """A retry of the attempt that recorded ``done`` gets it back; another tip under its key is refused."""
    same_sale = done.pool if data.pool else (done.sale_id == data.sale_id or done.sale.number == data.sale)
    if done.amount != data.amount or not same_sale:
        raise Conflict(str(ATTEMPT_KEY_REUSED), code="tip.attempt_key_reused")
    return done


def _attempted(key: str | None) -> Tip | None:
    """The tip the charge's attempt ``key`` already recorded, if any."""
    return Tip.objects.filter(attempt_key=key).first() if key else None


def _still_active(tip: Tip) -> None:
    if tip.status == Tip.Status.VOIDED:
        raise Conflict(str(TIP_VOIDED), code="tip.tip_voided")


@operation(
    "tip.tip.add",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="tip.add_tip",
    input=TipAddIn,
    output=TipOut,
    expose_api=True,
    ai={
        "asks": {
            "en": ("record a 2 € card tip on sale 20261114-0007", "put 5 € from the tip jar in the pool"),
            "es": ("apunta una propina de 2 € con tarjeta en la venta 20261114-0007", "echa 5 € del bote a las propinas"),
        },
        "description": "Record a tip in cents: of a sale (by its id or number) with its payment method, for whoever "
        "served it unless another member of the team is named, or, with pool, cash to the pool of no sale nor person. "
        "A tip enters the open drawer as its own line (in cash it raises the expected cash); in cash with the drawer on "
        "and closed it is refused. A voided or wholly refunded sale takes no tip.",
        "risk": "normal",
    },
)
def add_tip(ctx: OperationContext, data: TipAddIn) -> dict:
    done = _attempted(data.attempt_key)
    if done is not None:
        return tip_row(_the_same(done, data))
    sale = _sale(data)
    method = find_method(None, PaymentMethod.Type.CASH) if data.pool else find_method(data.method_id, data.method)
    tip = Tip(
        sale=sale,
        member=_member(data.member_id, sale),
        method=method,
        method_name=method.name,
        method_type=method.type,
        amount=data.amount,
        attempt_key=data.attempt_key,
        created_by=actor(ctx),
    )
    tip.session_id = drawer.move(ctx, tip, "in", tip.amount, strict=True)
    try:
        with atomic():
            tip.save()
    except IntegrityError:
        raise Conflict(str(ATTEMPT_IN_PROGRESS), code="tip.attempt_in_progress") from None
    record_event(
        ctx,
        events.TIP_ADDED,
        {
            "tip_id": str(tip.id),
            "sale_id": str(sale.id) if sale else None,
            "sale_number": sale.number if sale else "",
            "member_id": str(tip.member_id) if tip.member_id else None,
            "method_type": tip.method_type,
            "amount": tip.amount,
        },
    )
    return tip_row(tip)


def _figures(tip: Tip) -> dict:
    return {"amount": tip.amount, "member_id": str(tip.member_id) if tip.member_id else None}


@operation(
    "tip.tip.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="tip.manage",
    input=TipPatchIn,
    output=TipOut,
    expose_api=True,
    ai={
        "asks": {
            "en": ("the tip of sale 20261114-0007 was 3 €, not 2 €", "give the tip of sale 20261114-0009 to Ana"),
            "es": ("la propina de la venta 20261114-0007 era de 3 €, no de 2 €", "la propina de la 20261114-0009 es de Ana"),
        },
        "description": "Adjust a tip, by its id or its sale's number, with the reason: its amount in cents or who it "
        "belongs to. The difference enters or leaves the open drawer in its payment method; a closed session is never "
        "touched. A voided tip does not change.",
        "risk": "normal",
    },
)
def update_tip(ctx: OperationContext, data: TipPatchIn) -> dict:
    tip = find_tip(data, lock=True)
    _still_active(tip)
    member = _member(data.member_id, None) if data.member_id else tip.member
    amount = tip.amount if data.amount is None else data.amount
    if amount == tip.amount and member == tip.member:
        return tip_row(tip)
    before = _figures(tip)
    if amount != tip.amount and tip.session_id is not None:
        difference = amount - tip.amount
        drawer.move(ctx, tip, "in" if difference > 0 else "out", abs(difference))
    tip.amount, tip.member = amount, member
    tip.adjusted_at, tip.adjusted_by, tip.adjust_reason = timezone.now(), actor(ctx), data.reason
    tip.save(update_fields=["amount", "member", "adjusted_at", "adjusted_by", "adjust_reason"])
    record_event(
        ctx,
        events.TIP_ADJUSTED,
        {
            "tip_id": str(tip.id),
            "sale_id": str(tip.sale_id) if tip.sale_id else None,
            "before": before,
            "after": _figures(tip),
            "reason": data.reason,
        },
    )
    return tip_row(tip)


def void_one(ctx: OperationContext, tip: Tip, by: str, reason: str) -> None:
    """Voids ``tip``: what it put in a drawer goes out of the open one, and ``tip.tip.voided`` says who and why."""
    if tip.session_id is not None:
        drawer.move(ctx, tip, "out", tip.amount)
    tip.status, tip.voided_at = Tip.Status.VOIDED, timezone.now()
    tip.voided_by, tip.void_reason = by[:150], reason[:255]
    tip.save(update_fields=["status", "voided_at", "voided_by", "void_reason"])
    record_event(
        ctx,
        events.TIP_VOIDED,
        {
            "tip_id": str(tip.id),
            "sale_id": str(tip.sale_id) if tip.sale_id else None,
            "amount": tip.amount,
            "method_type": tip.method_type,
            "reason": tip.void_reason,
        },
    )


@operation(
    "tip.tip.void",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="tip.manage",
    input=TipVoidIn,
    output=TipOut,
    expose_api=True,
    ai={
        "asks": {
            "en": ("void the tip of sale 20261114-0007, it went on the wrong sale",),
            "es": ("anula la propina de la venta 20261114-0007, era de otra mesa",),
        },
        "description": "Void a tip, by its id or its sale's number, with the reason. What it put in a drawer goes out of "
        "the open one in its payment method; a closed session is never touched. It cannot be undone.",
        "risk": "high",
    },
)
def void_tip(ctx: OperationContext, data: TipVoidIn) -> dict:
    tip = find_tip(data, lock=True)
    _still_active(tip)
    void_one(ctx, tip, actor(ctx), data.reason)
    return tip_row(tip)
