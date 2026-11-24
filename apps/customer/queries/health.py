"""A card's health data (CUSTOMER-F32): its allergies and sensitivity test, and its permission to keep them."""

from live.context import OperationContext
from live.operations import INTERNAL, operation

from apps.customer.models import Consent, Customer, HealthRecord
from apps.customer.queries.reads import find_customer
from apps.customer.schemas.health import HealthDetailIn, HealthOut

#: The consent purpose of the permission to keep a card's health data.
HEALTH_PURPOSE = "health"


def health_consent(customer: Customer) -> Consent | None:
    """The card's last decision on keeping its health data, or ``None`` if it was never asked."""
    return (
        Consent.objects.filter(customer=customer, purpose=HEALTH_PURPOSE)
        .order_by("-occurred_at", "-created_at", "-id")
        .first()
    )


def load_health(customer: Customer) -> dict:
    """A ``HealthOut`` of ``customer``. Not an operation: services.py returns it after a write."""
    fact = health_consent(customer)
    record = HealthRecord.objects.filter(customer=customer).first()
    return {
        "customer_id": customer.id,
        "consent": fact.state if fact else "none",
        "consent_at": fact.occurred_at if fact else None,
        "consent_by": fact.recorded_by if fact else "",
        "notice_text": fact.notice_text if fact else "",
        "allergies": record.allergies if record else "",
        "sensitivity_test_on": record.sensitivity_test_on if record else None,
        "sensitivity_test_result": record.sensitivity_test_result if record else "",
        "updated_at": record.updated_at if record else None,
        "updated_by": record.updated_by if record else "",
    }


# No ``ai`` and no ``expose_api``: health data never reaches the assistant nor an API key (GDPR art. 9).
# Not an assistant tool: health data (GDPR art. 9), for the screen only and never sent to a model.
@operation(
    "customer.health.detail",
    kind="query",
    permission="customer.view",
    input=HealthDetailIn,
    output=HealthOut,
    ai=INTERNAL,
)
def health_detail(ctx: OperationContext, data: HealthDetailIn) -> dict:
    return load_health(find_customer(ctx, data.customer_id, data.customer))
