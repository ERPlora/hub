"""A customer's personal data erased (CUSTOMER-F16)."""

from django.utils import timezone
from live.context import OperationContext
from live.operations import AI, operation
from live.outbox import record_event

from apps.customer import events
from apps.customer.models import Activity, Customer, HealthRecord
from apps.customer.queries.reads import find_customer
from apps.customer.schemas.erasing import EraseIn, ErasedOut
from apps.customer.services.merging import MERGE_FILLED
from apps.customer.services.writes import _actor

#: The name an erased card keeps (CUSTOMER-F16): data, not a text of the interface.
ERASED_NAME = "Deleted customer"
#: What an erasure clears and what it keeps, written on its audit entry.
ERASE_SCOPE = [
    "customer",
    "activity",
    "field_values",
    "health",
    "memberships",
    "consent_addresses",
]
ERASE_RETAINED = ["purchases", "orders"]


@operation(
    "customer.customer.erase",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.erase",
    input=EraseIn,
    output=ErasedOut,
    ai=AI(
        "GDPR erasure of a customer's personal data: the card keeps its id and figures, its contact, tax and address "
        "data, notes, activity, custom values and memberships are erased, and one audit entry (who, when, why) "
        "stays. Purchases and orders are kept. Irreversible; repeating it changes nothing.",
        risk="high",
        asks={
            "en": ("Pedro wants all his data wiped", "GDPR request: erase Lucía's personal data"),
            "es": ("aplica el derecho al olvido a Lucía", "borra los datos personales de Sara por la RGPD"),
        },
    ),
)
def erase_customer(ctx: OperationContext, data: EraseIn) -> dict:
    customer = find_customer(ctx, data.id, data.customer, lock=True, live=False)
    # The same person's duplicates merged into this card keep their own data (CUSTOMER-F13):
    # erasing the person erases them too, however deep the chain, all locked in this transaction.
    cards, pending = [customer], [customer.id]
    while pending:
        absorbed = list(
            Customer.objects.select_for_update()
            .filter(merged_into_id__in=pending)
            .exclude(pk__in=[card.id for card in cards])
            .order_by("pk")
        )
        cards += absorbed
        pending = [card.id for card in absorbed]
    for card in cards:
        _erase_card(ctx, card, data.reason)
    return {"id": customer.id}


def _erase_card(ctx: OperationContext, customer: Customer, reason: str) -> None:
    """Erases one locked card once (repeating it writes nothing) and announces it every time."""
    if customer.erased_at is None:
        now = timezone.now()
        for field in (*MERGE_FILLED, "notes"):
            setattr(customer, field, "")
        customer.name = ERASED_NAME
        customer.birthday = customer.anniversary = None
        customer.preferred_channel = Customer.PreferredChannel.NONE
        customer.is_active = False
        customer.deleted_at = customer.deleted_at or now
        customer.erased_at = now
        customer.save()
        customer.activity.all().delete()
        customer.field_values.all().delete()
        HealthRecord.objects.filter(customer=customer).delete()
        customer.groups.clear()
        customer.tags.clear()
        customer.consents.update(contact_point="", evidence="", reason="")
        Activity.objects.create(
            customer=customer,
            kind=Activity.Kind.ERASED,
            text=reason,
            related_id=str(customer.id),
            related_type="customer",
            data={"scope": ERASE_SCOPE, "retained": ERASE_RETAINED},
            actor=_actor(ctx),
        )
    record_event(ctx, events.CUSTOMER_ERASED, {"id": str(customer.id)})
