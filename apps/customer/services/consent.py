"""A channel's consent granted or withdrawn, as a new fact with its evidence (CUSTOMER-F14, F15)."""

from django.utils import timezone
from live.context import OperationContext
from live.operations import AI, operation
from live.outbox import record_event

from apps.customer import events
from apps.customer.models import Activity, Consent, Customer
from apps.customer.queries.reads import find_customer
from apps.customer.schemas.consent import ConsentGrantIn, ConsentRow, ConsentWithdrawIn
from apps.customer.services.writes import _actor, _occurred_at


def _contact_point(customer: Customer, channel: str) -> str:
    """The card's address for ``channel`` right now: its email, its phone or its postal address."""
    if channel == Consent.Channel.EMAIL:
        return customer.email
    if channel == Consent.Channel.POSTAL:
        town = f"{customer.postal_code} {customer.city}".strip()
        return ", ".join(
            part for part in (customer.address, town, customer.country) if part
        )
    return customer.phone


def _record_consent(ctx: OperationContext, data, state: str) -> Consent:
    customer = find_customer(ctx, data.customer_id, data.customer, lock=True)
    now = timezone.now()
    occurred_at = _occurred_at(data.occurred_at, now)
    granted = state == Consent.State.GRANTED
    fact = Consent.objects.create(
        customer=customer,
        purpose=data.purpose,
        channel=data.channel,
        state=state,
        # Always the card's own address: the proof names the real contact (WORKBOOK F14).
        contact_point=_contact_point(customer, data.channel),
        source=data.source,
        notice_text=data.notice_text if granted else "",
        notice_version=data.notice_version if granted else "",
        evidence=data.evidence,
        reason="" if granted else data.reason,
        recorded_by=_actor(ctx),
        occurred_at=occurred_at,
        created_at=now,
    )
    Activity.objects.create(
        customer=customer,
        kind=Activity.Kind.CONSENT_GRANTED
        if granted
        else Activity.Kind.CONSENT_WITHDRAWN,
        text=fact.notice_text if granted else fact.reason,
        related_id=str(fact.id),
        related_type="consent",
        data={
            "purpose": fact.purpose,
            "channel": fact.channel,
            "source": fact.source,
            "notice_version": fact.notice_version,
            "occurred_at": occurred_at.isoformat(),
        },
        actor=_actor(ctx),
    )
    event = events.CONSENT_GRANTED if granted else events.CONSENT_WITHDRAWN
    record_event(
        ctx,
        event,
        {"id": str(fact.id), "customer_id": str(customer.id), "channel": fact.channel},
    )
    return fact


@operation(
    "customer.consent.grant",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.manage",
    input=ConsentGrantIn,
    output=ConsentRow,
    ai=AI(
        "Records that a customer GAVE consent (opted in, said yes) for a purpose, marketing by default, on a channel "
        "(email, SMS, WhatsApp, phone or post), as a new fact with its evidence: the exact words shown and their "
        "version, where and when, the card's own address on that channel at that moment, and who wrote it down (from "
        "the session). Only after the customer said yes.",
        asks={
            "en": ("Ana says yes to WhatsApp offers", "Luis agreed to marketing emails"),
            "es": (
                "Ana quiere las ofertas por WhatsApp",
                "Luis acepta que le mandemos emails",
                "Marta nos da permiso para los SMS",
            ),
        },
    ),
)
def grant_consent(ctx: OperationContext, data: ConsentGrantIn) -> Consent:
    return _record_consent(ctx, data, Consent.State.GRANTED)


@operation(
    "customer.consent.withdraw",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.manage",
    input=ConsentWithdrawIn,
    output=ConsentRow,
    ai=AI(
        "Records that a customer WITHDREW consent (opted out, unsubscribed, asked to stop) for a purpose and channel "
        "(email, SMS, WhatsApp, phone or post), as a new fact in force at once, for the card's own address on that "
        "channel; the grant it revokes is kept. The reason is optional.",
        asks={
            "en": ("Luis wants to stop the emails", "unsubscribe Marta from WhatsApp messages"),
            "es": ("Luis ya no quiere más emails", "Carmen se da de baja de la publicidad"),
        },
    ),
)
def withdraw_consent(ctx: OperationContext, data: ConsentWithdrawIn) -> Consent:
    return _record_consent(ctx, data, Consent.State.WITHDRAWN)
