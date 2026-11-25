"""Purchases: the system's (CUSTOMER-F20, F21, F22), recorded, voided and refunded as Sales reacts to a sale."""

from uuid import UUID

from django.db.models import Max
from django.utils import timezone
from live.context import OperationContext
from live.operations import INTERNAL, operation
from live.outbox import record_event

from apps.customer import events
from apps.customer.models import Activity, Customer, Purchase
from apps.customer.schemas.purchases import (
    PurchaseRecordIn,
    PurchaseRecordOut,
    PurchaseRefundIn,
    PurchaseRefundOut,
    PurchaseVoidIn,
    PurchaseVoidOut,
)
from apps.customer.services.writes import _actor

#: Where a purchase moves a card's stage, and where a void takes it back.
STAGE_AFTER_PURCHASE = {
    Customer.Stage.LEAD: Customer.Stage.FIRST_PURCHASE,
    Customer.Stage.PROSPECT: Customer.Stage.FIRST_PURCHASE,
    Customer.Stage.FIRST_PURCHASE: Customer.Stage.ACTIVE,
    Customer.Stage.AT_RISK: Customer.Stage.ACTIVE,
    Customer.Stage.DORMANT: Customer.Stage.ACTIVE,
}


def _stage_after_void(stage: str, purchases_left: int) -> str:
    if purchases_left <= 0 and stage in (
        Customer.Stage.FIRST_PURCHASE,
        Customer.Stage.ACTIVE,
    ):
        return Customer.Stage.LEAD
    if purchases_left == 1 and stage == Customer.Stage.ACTIVE:
        return Customer.Stage.FIRST_PURCHASE
    return stage


# The sale app's reaction to a paid sale, never a person's tool: records the sale in its customer's history once
# (the same sale twice counts once), adding it to the purchases, the spend and the last purchase and moving the
# stage forward.
@operation(
    "customer.purchase.record",
    kind="command",
    # Declared by no app: only the system context (``*``) holds it, as the product's internal commands.
    permission="customer.record_purchase",
    input=PurchaseRecordIn,
    output=PurchaseRecordOut,
    ai=INTERNAL,
)
def record_purchase(ctx: OperationContext, data: PurchaseRecordIn) -> dict:
    nothing = {"sale_id": data.sale_id, "recorded": False}
    if data.customer_id is None:
        return nothing
    customer = (
        Customer.objects.live().select_for_update().filter(pk=data.customer_id).first()
    )
    if customer is None or (
        data.sale_id is not None
        and Purchase.objects.filter(sale_id=data.sale_id).exists()
    ):
        return nothing
    at = data.purchased_at or timezone.now()
    purchase = Purchase.objects.create(
        customer=customer,
        sale_id=data.sale_id,
        amount=data.total,
        currency=data.currency,
        recorded_at=at,
    )
    customer.total_purchases += 1
    customer.total_spent += data.total
    customer.last_purchase_at = max(
        moment for moment in (customer.last_purchase_at, at) if moment
    )
    customer.lifecycle_stage = STAGE_AFTER_PURCHASE.get(
        customer.lifecycle_stage, customer.lifecycle_stage
    )
    customer.save(
        update_fields=[
            "total_purchases",
            "total_spent",
            "last_purchase_at",
            "lifecycle_stage",
            "updated_at",
        ]
    )
    Activity.objects.create(
        customer=customer,
        kind=Activity.Kind.PURCHASE_RECORDED,
        related_id=str(data.sale_id or purchase.id),
        related_type="sale",
        data={"amount": data.total, "currency": data.currency},
        actor=_actor(ctx),
    )
    sale = str(data.sale_id) if data.sale_id else None
    record_event(
        ctx,
        events.PURCHASE_RECORDED,
        {"customer_id": str(customer.id), "sale_id": sale},
    )
    return {"sale_id": data.sale_id, "recorded": True}


# The sale app's reaction to a voided sale, never a person's tool: marks its purchase as voided (kept in the
# history), takes it off the purchases and the spend, recomputes the last purchase and steps the stage back. Once.
@operation(
    "customer.purchase.void",
    kind="command",
    permission="customer.record_purchase",
    input=PurchaseVoidIn,
    output=PurchaseVoidOut,
    ai=INTERNAL,
)
def void_purchase(ctx: OperationContext, data: PurchaseVoidIn) -> dict:
    nothing = {"sale_id": data.sale_id, "voided": False}
    locked = _locked_purchase(data.sale_id)
    if locked is None:
        return nothing
    customer, purchase = locked
    purchase.status = Purchase.Status.VOIDED
    purchase.voided_at = timezone.now()
    purchase.void_reason = data.reason
    purchase.save(update_fields=["status", "voided_at", "void_reason"])
    customer.total_purchases = max(customer.total_purchases - 1, 0)
    customer.total_spent -= purchase.amount
    customer.last_purchase_at = customer.purchases.filter(
        status=Purchase.Status.CONFIRMED
    ).aggregate(last=Max("recorded_at"))["last"]
    customer.lifecycle_stage = _stage_after_void(
        customer.lifecycle_stage, customer.total_purchases
    )
    customer.save(
        update_fields=[
            "total_purchases",
            "total_spent",
            "last_purchase_at",
            "lifecycle_stage",
            "updated_at",
        ]
    )
    if customer.erased_at is None:  # an erased card's timeline keeps only its erasure
        Activity.objects.create(
            customer=customer,
            kind=Activity.Kind.PURCHASE_VOIDED,
            text=data.reason,
            related_id=str(data.sale_id),
            related_type="sale",
            data={"amount": purchase.amount, "currency": purchase.currency},
            actor=_actor(ctx),
        )
    record_event(
        ctx,
        events.PURCHASE_VOIDED,
        {"customer_id": str(customer.id), "sale_id": str(data.sale_id)},
    )
    return {"sale_id": data.sale_id, "voided": True}


#: How many times a void follows a purchase that a merge moved to another card meanwhile.
VOID_ATTEMPTS = 3


# The sale app's reaction to a refund of a paid sale (all or part), never a person's tool: records the refund as a
# line of its own in its customer's history and takes what came back off the spend; the purchases, the last
# purchase and the stage stay. Once per refund.
@operation(
    "customer.purchase.refund",
    kind="command",
    permission="customer.record_purchase",
    input=PurchaseRefundIn,
    output=PurchaseRefundOut,
    ai=INTERNAL,
)
def refund_purchase(ctx: OperationContext, data: PurchaseRefundIn) -> dict:
    nothing = {"sale_id": data.sale_id, "refund_id": data.refund_id, "refunded": False}
    # The card first, then its purchase (the order a merge locks them in); then the refund, checked
    # under that lock so a repeated delivery never counts twice.
    locked = _locked_purchase(data.sale_id)
    if locked is None or Purchase.objects.filter(refund_id=data.refund_id).exists():
        return nothing
    customer, purchase = locked
    Purchase.objects.create(
        customer=customer,
        sale_id=data.sale_id,
        refund_id=data.refund_id,
        amount=-data.total,
        currency=purchase.currency,
        status=Purchase.Status.REFUNDED,
        recorded_at=data.refunded_at or timezone.now(),
        void_reason=data.reason,
    )
    customer.total_spent -= data.total
    customer.save(update_fields=["total_spent", "updated_at"])
    if customer.erased_at is None:  # an erased card's timeline keeps only its erasure
        Activity.objects.create(
            customer=customer,
            kind=Activity.Kind.PURCHASE_REFUNDED,
            text=data.reason,
            related_id=str(data.refund_id),
            related_type="refund",
            data={"amount": data.total, "currency": purchase.currency},
            actor=_actor(ctx),
        )
    record_event(
        ctx,
        events.PURCHASE_REFUNDED,
        {
            "customer_id": str(customer.id),
            "sale_id": str(data.sale_id),
            "refund_id": str(data.refund_id),
        },
    )
    return {"sale_id": data.sale_id, "refund_id": data.refund_id, "refunded": True}


def _locked_purchase(sale_id: UUID) -> tuple[Customer, Purchase] | None:
    """The card and the paid purchase of ``sale_id``, both locked, the card first; ``None`` if none.

    A merge locks the cards and then moves their purchases: locking the purchase first and the card
    after would make the two wait for each other. So the purchase is read without a lock, its card
    is locked, and the purchase is read again, locked, checking it is still that card's and paid. A
    card the Hub admin deleted in between took its purchases with it: the purchase is looked for
    again, as one a merge moved.
    """
    for _attempt in range(VOID_ATTEMPTS):
        found = (
            Purchase.objects.filter(sale_id=sale_id, status=Purchase.Status.CONFIRMED)
            .values_list("customer_id", flat=True)
            .first()
        )
        if found is None:
            return None
        customer = Customer.objects.select_for_update().filter(pk=found).first()
        if customer is None:
            continue
        purchase = (
            Purchase.objects.select_for_update()
            .filter(
                sale_id=sale_id, customer=customer, status=Purchase.Status.CONFIRMED
            )
            .first()
        )
        if purchase is not None:
            return customer, purchase
    return None
