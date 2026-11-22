"""The platform's reactions to Customers on the vouchers sold: a card merged into another and a customer erased."""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation
from live.outbox import record_event

from apps.customer.models import Customer
from apps.service import events
from apps.service.models import Grant, GrantAdjustment, Redemption
from apps.service.queries.reads import SYSTEM
from apps.service.schemas import ForgetCustomerIn, ForgottenOut, ReassignedOut, ReassignIn

CUSTOMER_UNAVAILABLE = _("That customer's card does not exist in this business.")


@operation(
    "service.grant.reassign",
    kind="command",
    permission=SYSTEM,
    input=ReassignIn,
    output=ReassignedOut,
    ai={
        "description": "Platform reaction to customer.customer.merged: the absorbed card's vouchers move to the card "
        "that stays, with their sessions and adjustments.",
        "risk": "normal",
    },
)
def reassign_grants(ctx: OperationContext, data: ReassignIn) -> dict:
    if data.id == data.absorbed_id:
        return {"moved": 0}
    if not Customer.objects.select_for_update().filter(pk=data.id).exists():
        raise NotFound(str(CUSTOMER_UNAVAILABLE), code="service.customer_unavailable")
    moved = Grant.objects.filter(customer_id=data.absorbed_id).update(
        customer_id=data.id, updated_at=timezone.now()
    )
    if moved:
        record_event(
            ctx,
            events.GRANT_REASSIGNED,
            {"id": str(data.id), "absorbed_id": str(data.absorbed_id)},
        )
    return {"moved": moved}


@operation(
    "service.grant.forget_customer",
    kind="command",
    permission=SYSTEM,
    input=ForgetCustomerIn,
    output=ForgottenOut,
    ai={
        "description": "Platform reaction to customer.customer.erased (GDPR): the free texts of the card's vouchers "
        "(notes, void reasons, adjustment reasons, session notes) are emptied; ids, amounts and sessions stay.",
        "risk": "normal",
    },
)
def forget_customer(ctx: OperationContext, data: ForgetCustomerIn) -> dict:
    grants = Grant.objects.filter(customer_id=data.id)
    touched = set(grants.exclude(note="", void_reason="").values_list("id", flat=True))
    touched |= set(GrantAdjustment.objects.filter(grant__customer_id=data.id).exclude(reason="").values_list("grant_id", flat=True))
    touched |= set(
        Redemption.objects.filter(grant__customer_id=data.id)
        .exclude(note="", return_reason="")
        .values_list("grant_id", flat=True)
    )
    if touched:
        now = timezone.now()
        grants.filter(pk__in=touched).update(note="", void_reason="", updated_at=now)
        GrantAdjustment.objects.filter(grant_id__in=touched).update(reason="")
        Redemption.objects.filter(grant_id__in=touched).update(note="", return_reason="")
        record_event(ctx, events.GRANT_ERASED, {"id": str(data.id)})
    return {"erased": len(touched)}
