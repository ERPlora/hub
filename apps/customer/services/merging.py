"""Two cards of the same person merged into one (CUSTOMER-F13)."""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload, NotFound
from live.operations import AI, operation
from live.outbox import record_event

from apps.customer import events
from apps.customer.models import (
    Activity,
    Consent,
    Customer,
    CustomerGroup,
    CustomerTag,
    CustomFieldValue,
    HealthRecord,
    OrderLink,
    Purchase,
)
from apps.customer.queries import (
    CUSTOMER_UNAVAILABLE,
    CUSTOMER_UNAVAILABLE_CODE,
    find_customer,
    health_consent,
    load_detail,
)
from apps.customer.schemas.cards import CustomerDetailOut
from apps.customer.schemas.merging import MergeIn
from apps.customer.services.writes import _actor, lock_rows

SAME_CUSTOMER = _("Pick another card: a card cannot be merged into itself.")
#: The text fields of a card a merge fills from the duplicate when the survivor's is empty.
MERGE_FILLED = (
    "email",
    "phone",
    "tax_id",
    "company_name",
    "address",
    "city",
    "postal_code",
    "country",
    "avatar",
    "birthday",
    "anniversary",
)


@operation(
    "customer.customer.merge",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.merge",
    input=MergeIn,
    output=CustomerDetailOut,
    ai=AI(
        "Use this tool once both cards are known; do not stop at reading or explaining the merge. `customer` is the "
        "card that stays and `absorbed` is the duplicate merged into it: for «merge A into B», B is `customer` and A "
        "is `absorbed`. Pass an exact name, phone or email in either field or, once customer.customer.by_phone or "
        "customer.customer.list found the cards, their ids in `id` and `absorbed_id`; never ask the person for an "
        "internal id. The survivor keeps its data and fills only its empty fields, notes are appended and figures "
        "summed; activity, custom values, groups, tags, purchases, orders and consent move to it, and the duplicate is "
        "retired. Cannot be undone.",
        risk="high",
        asks={
            "en": (
                "merge the two Marta cards",
                "Ana's in there twice, combine them",
                "merge the card for 611 222 444 into the one for 611 222 333",
            ),
            "es": (
                "Ana López está repetida, júntala con la otra",
                "tengo a Marta duplicada, únelas",
                "junta la ficha del 611 222 444 dentro de la del 611 222 333",
            ),
        },
    ),
)
def merge_customers(ctx: OperationContext, data: MergeIn) -> dict:
    survivor_id = find_customer(ctx, data.id, data.customer).id
    absorbed_id = find_customer(ctx, data.absorbed_id, data.absorbed).id
    if survivor_id == absorbed_id:
        raise InvalidPayload(
            SAME_CUSTOMER,
            code="customer.same_customer",
            fields={"absorbed_id": SAME_CUSTOMER},
        )
    # Both rows locked in one order, so two merges of the same pair never wait for each other.
    cards = (
        Customer.objects.live()
        .select_for_update()
        .filter(pk__in=[survivor_id, absorbed_id])
    )
    locked = {customer.id: customer for customer in cards.order_by("pk")}
    if len(locked) < 2:  # one of them went between the lookup and the lock
        raise NotFound(CUSTOMER_UNAVAILABLE, code=CUSTOMER_UNAVAILABLE_CODE)
    survivor, absorbed = locked[survivor_id], locked[absorbed_id]
    for field in MERGE_FILLED:
        if not getattr(survivor, field):
            setattr(survivor, field, getattr(absorbed, field))
    if survivor.preferred_channel == Customer.PreferredChannel.NONE:
        survivor.preferred_channel = absorbed.preferred_channel
    survivor.notes = "\n".join(
        note for note in (survivor.notes, absorbed.notes) if note
    )
    survivor.total_purchases += absorbed.total_purchases
    survivor.total_spent += absorbed.total_spent
    survivor.last_purchase_at = max(
        (
            moment
            for moment in (survivor.last_purchase_at, absorbed.last_purchase_at)
            if moment
        ),
        default=None,
    )
    survivor.save()

    Activity.objects.filter(customer=absorbed).update(customer=survivor)
    Purchase.objects.filter(customer=absorbed).update(customer=survivor)
    Consent.objects.filter(customer=absorbed).update(customer=survivor)
    OrderLink.objects.filter(customer=absorbed).update(customer=survivor)
    survivor_fields = CustomFieldValue.objects.filter(customer=survivor).values_list(
        "field_id", flat=True
    )
    CustomFieldValue.objects.filter(customer=absorbed).exclude(
        field_id__in=list(survivor_fields)
    ).update(customer=survivor)
    # The duplicate's groups and tags are held before the survivor points at them (as setting them does).
    survivor.groups.add(*lock_rows(CustomerGroup, absorbed.groups.values("id")))
    survivor.tags.add(*lock_rows(CustomerTag, absorbed.tags.values("id")))
    absorbed.groups.clear()
    absorbed.tags.clear()
    _merge_health(survivor, absorbed)

    # The cards merged into the duplicate before now point at the survivor: the chain stays flat.
    Customer.objects.filter(merged_into=absorbed).update(merged_into=survivor)
    absorbed.deleted_at = timezone.now()
    absorbed.is_active = False
    absorbed.merged_into = survivor
    absorbed.total_purchases = absorbed.total_spent = 0
    absorbed.last_purchase_at = None
    absorbed.save()
    Activity.objects.create(
        customer=survivor,
        kind=Activity.Kind.MERGED,
        related_id=str(absorbed.id),
        related_type="customer",
        data={"absorbed_id": str(absorbed.id)},
        actor=_actor(ctx),
    )
    record_event(
        ctx,
        events.CUSTOMER_MERGED,
        {"id": str(survivor.id), "absorbed_id": str(absorbed.id)},
    )
    return load_detail(survivor)


def _merge_health(survivor: Customer, absorbed: Customer) -> None:
    """The survivor keeps its health data and fills its gaps with the duplicate's (CUSTOMER-F13, F32).

    Their consent facts already moved: if the last health decision of the person is not a grant, no
    health data stays.
    """
    duplicate = HealthRecord.objects.filter(customer=absorbed).first()
    own = HealthRecord.objects.filter(customer=survivor).first()
    if duplicate and own:
        own.allergies = own.allergies or duplicate.allergies
        if not own.sensitivity_test_on:
            own.sensitivity_test_on = duplicate.sensitivity_test_on
            own.sensitivity_test_result = duplicate.sensitivity_test_result
        own.save()
        duplicate.delete()
    elif duplicate:
        duplicate.customer = survivor
        duplicate.save(update_fields=["customer"])
    fact = health_consent(survivor)
    if fact is None or fact.state != Consent.State.GRANTED:
        HealthRecord.objects.filter(customer=survivor).delete()
