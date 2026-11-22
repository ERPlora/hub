"""A card's health data and the permission to keep it (CUSTOMER-F32)."""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import INTERNAL, operation
from live.outbox import record_event

from apps.customer import events
from apps.customer.models import Activity, Consent, Customer, HealthRecord
from apps.customer.queries import find_customer, HEALTH_PURPOSE, health_consent, load_health
from apps.customer.schemas import HealthGrantIn, HealthIn, HealthOut, HealthWithdrawIn
from apps.customer.services.writes import DATE_IN_FUTURE, _actor, _changes, _occurred_at
from base.business import business_zone

HEALTH_CONSENT_REQUIRED = _("Record their permission first to keep health data.")
HEALTH_TEST_DATE_MISSING = _("Enter the date of the test.")


# Special category data (GDPR art. 9): kept only while the card's last health decision is a grant,
# erased when it is withdrawn. No ``ai`` and no ``expose_api``: never for the assistant nor an API key.


def _health_fact(
    ctx: OperationContext, data, customer: Customer, state: str
) -> Consent:
    now = timezone.now()
    occurred_at = _occurred_at(getattr(data, "occurred_at", None), now)
    granted = state == Consent.State.GRANTED
    fact = Consent.objects.create(
        customer=customer,
        purpose=HEALTH_PURPOSE,
        channel="",
        state=state,
        source=data.source,
        notice_text=data.notice_text if granted else "",
        notice_version=data.notice_version if granted else "",
        evidence=data.evidence if granted else "",
        reason="" if granted else data.reason,
        recorded_by=_actor(ctx),
        occurred_at=occurred_at,
        created_at=now,
    )
    Activity.objects.create(
        customer=customer,
        kind=Activity.Kind.HEALTH_CONSENT_GRANTED
        if granted
        else Activity.Kind.HEALTH_CONSENT_WITHDRAWN,
        text=fact.notice_text if granted else fact.reason,
        related_id=str(fact.id),
        related_type="consent",
        data={
            "purpose": HEALTH_PURPOSE,
            "source": fact.source,
            "notice_version": fact.notice_version,
            "occurred_at": occurred_at.isoformat(),
        },
        actor=_actor(ctx),
    )
    record_event(
        ctx,
        events.HEALTH_CONSENT_GRANTED if granted else events.HEALTH_CONSENT_WITHDRAWN,
        {"id": str(fact.id), "customer_id": str(customer.id)},
    )
    return fact


# Not an assistant tool: health data (GDPR art. 9), for the screen only and never sent to a model.
@operation(
    "customer.health.grant",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.manage",
    input=HealthGrantIn,
    output=HealthOut,
    ai=INTERNAL,
)
def grant_health(ctx: OperationContext, data: HealthGrantIn) -> dict:
    customer = find_customer(ctx, data.customer_id, data.customer, lock=True)
    _health_fact(ctx, data, customer, Consent.State.GRANTED)
    return load_health(customer)


# Not an assistant tool: health data (GDPR art. 9), for the screen only and never sent to a model.
@operation(
    "customer.health.withdraw",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.manage",
    input=HealthWithdrawIn,
    output=HealthOut,
    ai=INTERNAL,
)
def withdraw_health(ctx: OperationContext, data: HealthWithdrawIn) -> dict:
    customer = find_customer(ctx, data.customer_id, data.customer, lock=True)
    _health_fact(ctx, data, customer, Consent.State.WITHDRAWN)
    # Withdrawing the only ground to keep them erases them in the same step (GDPR arts. 7.3, 17.1.b).
    HealthRecord.objects.filter(customer=customer).delete()
    return load_health(customer)


# Not an assistant tool: health data (GDPR art. 9), for the screen only and never sent to a model.
@operation(
    "customer.health.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.manage",
    input=HealthIn,
    output=HealthOut,
    ai=INTERNAL,
)
def update_health(ctx: OperationContext, data: HealthIn) -> dict:
    customer = find_customer(ctx, data.customer_id, data.customer, lock=True)
    fact = health_consent(customer)
    if fact is None or fact.state != Consent.State.GRANTED:
        raise Conflict(HEALTH_CONSENT_REQUIRED, code="customer.health_consent_required")
    if data.sensitivity_test_on and data.sensitivity_test_on > timezone.localdate(timezone=business_zone()):
        raise InvalidPayload(
            DATE_IN_FUTURE,
            code="customer.date_in_future",
            fields={"sensitivity_test_on": DATE_IN_FUTURE},
        )
    if data.sensitivity_test_result and not data.sensitivity_test_on:
        raise InvalidPayload(
            HEALTH_TEST_DATE_MISSING,
            code="customer.health_test_date_missing",
            fields={"sensitivity_test_on": HEALTH_TEST_DATE_MISSING},
        )
    values = {
        "allergies": data.allergies,
        "sensitivity_test_on": data.sensitivity_test_on,
        "sensitivity_test_result": data.sensitivity_test_result,
    }
    record = HealthRecord.objects.filter(customer=customer).first()
    if record is None:
        record = HealthRecord(customer=customer)
    elif not _changes(record, values):
        return load_health(customer)
    for field, value in values.items():
        setattr(record, field, value)
    record.updated_at = timezone.now()
    record.updated_by = _actor(ctx)
    record.save()
    # The timeline says it changed and who did it, never what: the data lives in its block only.
    Activity.objects.create(
        customer=customer,
        kind=Activity.Kind.HEALTH_UPDATED,
        related_id=str(record.id),
        related_type="health",
        actor=_actor(ctx),
    )
    record_event(
        ctx,
        events.HEALTH_UPDATED,
        {"id": str(record.id), "customer_id": str(customer.id)},
    )
    return load_health(customer)
