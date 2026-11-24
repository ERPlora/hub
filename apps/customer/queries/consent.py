"""A card's consent: the one in force per purpose and channel, and every fact of it, newest first."""

from django.db.models import Q
from live.context import OperationContext
from live.operations import AI, operation

from apps.customer.models import Consent
from apps.customer.queries.cards import consent_states
from apps.customer.queries.reads import find_customer, page
from apps.customer.schemas.consent import ConsentHistoryIn, ConsentPage, ConsentStateIn, ConsentStateOut

from . import contact


@operation(
    "customer.consent.state",
    kind="query",
    permission="customer.view",
    input=ConsentStateIn,
    output=ConsentStateOut,
    expose_api=True,
    ai=AI(
        "Whether a customer agreed to be sent marketing (offers, news) by email, SMS, WhatsApp, phone or post: the "
        "consent in force, one row per purpose and channel, granted or withdrawn. The last fact wins, so a "
        "withdrawal is in force on the next read. Read it before writing to anybody.",
        asks={
            "en": ("can I send Luis marketing emails?", "has Marta agreed to WhatsApp messages?"),
            "es": (
                "¿puedo mandarle un email a Marta?",
                "¿qué permisos nos ha dado Carmen?",
                "¿Luis acepta publicidad por WhatsApp?",
            ),
        },
    ),
)
def consent_state(ctx: OperationContext, data: ConsentStateIn) -> dict:
    customer = find_customer(ctx, data.customer_id, data.customer)
    return {"customer_id": customer.id, "rows": consent_states(customer)}


@operation(
    "customer.consent.history",
    kind="query",
    permission="customer.view",
    input=ConsentHistoryIn,
    output=ConsentPage,
    ai=AI(
        "Every consent fact of a customer, newest first: what was decided, for which purpose and channel, at which "
        "address, from where, after which words, and who wrote it down.",
        asks={
            "en": ("when did Carmen opt in?", "show Luis's consent history"),
            "es": ("¿cuándo dijo Carmen que sí a los emails?", "historial de permisos de Luis"),
        },
    ),
)
def consent_history(ctx: OperationContext, params: ConsentHistoryIn) -> dict:
    customer = find_customer(ctx, params.customer_id, params.customer)
    facts = Consent.objects.filter(customer=customer)
    if params.search:
        text = params.search
        facts = facts.filter(
            Q(purpose__icontains=text)
            | Q(channel__icontains=text)
            | (Q(contact_point__icontains=text) if contact.sees_contact(ctx) else Q())
            | Q(notice_text__icontains=text)
            | Q(reason__icontains=text)
        )
    return page(facts.order_by("-occurred_at", "-created_at", "-id"), params)
