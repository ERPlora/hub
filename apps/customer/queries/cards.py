"""The cards: the list the Customers screen shows, one card whole (with its groups, tags, custom fields and consent in
force), the figures of every card and the cards a phone number is."""

from django.db.models import Count, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from live.context import OperationContext
from live.operations import AI, operation

from apps.customer.models import Consent, Customer, CustomField, CustomFieldValue
from apps.customer.phones import candidates
from apps.customer.queries.reads import _ordered, business_country, find_customer, page
from apps.customer.schemas.cards import (
    ByPhoneIn,
    CustomerDetailOut,
    CustomerFilters,
    CustomerListIn,
    CustomerPage,
    CustomerStatsIn,
    CustomerStatsOut,
    PhoneMatchOut,
)
from base.text_search import contains_text
from apps.customer.schemas.fields import CustomerRefIn
from apps.customer.search import search_term

from . import contact


def consent_states(customer: Customer) -> list[Consent]:
    """The last fact per purpose and channel of a card: its consent in force."""
    return list(
        Consent.objects.filter(customer=customer)
        .order_by("purpose", "channel", "-occurred_at", "-created_at", "-id")
        .distinct("purpose", "channel")
    )


def load_detail(customer: Customer) -> dict:
    """A ``CustomerDetailOut`` of ``customer``. Not an operation: services.py returns it after a write."""
    values = dict(
        CustomFieldValue.objects.filter(customer=customer).values_list(
            "field_id", "value"
        )
    )
    custom_fields = [
        {
            "field_id": field.id,
            "name": field.name,
            "field_type": field.field_type,
            "options": field.options,
            "is_required": field.is_required,
            "sort_order": field.sort_order,
            "value": values.get(field.id, ""),
        }
        for field in CustomField.objects.filter(is_active=True)
    ]
    consent = consent_states(customer)
    granted = [
        fact.occurred_at
        for fact in consent
        if fact.purpose == "marketing" and fact.state == Consent.State.GRANTED
    ]
    return {
        **{
            field: getattr(customer, field)
            for field in CustomerDetailOut.model_fields
            if hasattr(customer, field)
        },
        "group_ids": list(
            customer.groups.order_by("name", "id").values_list("id", flat=True)
        ),
        "tag_ids": list(
            customer.tags.order_by("name", "id").values_list("id", flat=True)
        ),
        "custom_fields": custom_fields,
        "consent": consent,
        "marketing_consent": bool(granted),
        "consent_date": max(granted) if granted else None,
    }


def _filtered_customers(ctx: OperationContext, params: CustomerFilters) -> QuerySet:
    cards = Customer.objects.live()
    term = search_term(params.search or "")
    if term:
        cards = contact.searched(ctx, cards, term)
    for field in ("name", "email", "tax_id", "company_name"):
        value = (getattr(params, field) or "").strip()
        if value:
            cards = cards.filter(contains_text(value, field))
    phone = search_term(params.phone or "")
    if phone:
        cards = cards.filter(phone__contains=phone)
    for field in ("lifecycle_stage", "source", "is_active"):
        value = getattr(params, field)
        if value is not None:
            cards = cards.filter(**{field: value})
    bounds = {
        "total_purchases__gte": params.purchases_min,
        "total_purchases__lte": params.purchases_max,
        "total_spent__gte": params.spent_min,
        "total_spent__lte": params.spent_max,
        "last_purchase_at__date__gte": params.last_purchase_from,
        "last_purchase_at__date__lte": params.last_purchase_to,
    }
    return cards.filter(
        **{lookup: value for lookup, value in bounds.items() if value is not None}
    )


def _customers(ctx: OperationContext, params: CustomerFilters) -> QuerySet:
    return _ordered(_filtered_customers(ctx, params), params.sort, params.descending)


@operation(
    "customer.customer.list",
    kind="query",
    permission="customer.view",
    input=CustomerListIn,
    output=CustomerPage,
    ai=AI(
        "Lists the business's customers, 50 per page, with a search over name, email, phone, tax id and company and "
        "filters by stage, source, activity, purchases and spend.",
        asks={
            "en": ("show me my customers", "who are my best clients?", "find the customers from Acme"),
            "es": (
                "¿qué clientes tengo?",
                "búscame los clientes de la empresa Acme",
                "pásame las clientas que más gastan",
            ),
        },
    ),
)
def list_customers(ctx: OperationContext, params: CustomerListIn) -> dict:
    return page(_customers(ctx, params), params)


@operation(
    "customer.customer.detail",
    kind="query",
    permission="customer.view",
    input=CustomerRefIn,
    output=CustomerDetailOut,
    ai=AI(
        "Retrieves a customer's whole card by its id or by its name, phone or email: contact and tax details, "
        "groups, tags, custom fields and consent per channel.",
        asks={
            "en": ("what do we know about Marta?", "pull up Luis's details", "bring up Carmen's card"),
            "es": ("¿qué sabemos de Marta?", "dame los datos de la clienta Carmen", "¿quién es Luis Gómez?"),
        },
    ),
)
def customer_detail(ctx: OperationContext, data: CustomerRefIn) -> dict:
    return load_detail(find_customer(ctx, data.id, data.customer))


@operation(
    "customer.customer.stats",
    kind="query",
    permission="customer.view",
    input=CustomerStatsIn,
    output=CustomerStatsOut,
    ai=AI(
        "Returns the customer figures: how many customers, how many active, how many VIP, and the revenue.",
        asks={
            "en": ("what are our customer stats?", "give me our customer figures"),
            "es": (
                "¿cuántos clientes VIP hay?",
                "¿cuánto nos han dejado los clientes en total?",
                "dame las cifras de clientes",
            ),
        },
    ),
)
def customer_stats(ctx: OperationContext, data: CustomerStatsIn) -> dict:
    return Customer.objects.live().aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(is_active=True)),
        vip=Count("id", filter=Q(lifecycle_stage=Customer.Stage.VIP)),
        total_revenue=Coalesce(Sum("total_spent"), Value(0)),
    )


@operation(
    "customer.customer.by_phone",
    kind="query",
    permission="customer.view",
    input=ByPhoneIn,
    output=PhoneMatchOut,
    ai=AI(
        "Finds the customers whose phone is the same number as `phone`, however it was typed (spaces, dashes, + or "
        "00, the business's country for a number without prefix, the bare digits WhatsApp sends); another country's "
        "code is another person, and an unreadable number matches nobody.",
        asks={
            "en": (
                "whose number is 600 111 222?",
                "who's calling from +34 612 345 678?",
                "look up this phone number",
            ),
            "es": (
                "¿de quién es el 600 111 222?",
                "me llama el 612345678, ¿es clienta?",
                "busca quién tiene este móvil",
            ),
        },
    ),
)
def customers_by_phone(ctx: OperationContext, data: ByPhoneIn) -> dict:
    numbers = candidates(data.phone, business_country(ctx))
    if not numbers:
        return {"rows": []}
    return {
        "rows": list(
            Customer.objects.live().filter(phone__in=numbers).order_by("name", "id")
        )
    }
