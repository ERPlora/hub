"""Read operations of the customer app (``READ ONLY``), and the lookups its commands share.

Every read sees the live cards only (not deleted, merged nor erased). A customer may be named by
its id or by its exact name, phone or email (``find_customer``); groups, tags and fields, by name.
"""

import csv
import io
from decimal import Decimal
from uuid import UUID

from django.db.models import Count, F, IntegerField, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import AI, INTERNAL, operation
from psycopg import sql

from apps.customer.models import (
    Activity,
    Consent,
    Customer,
    CustomerGroup,
    CustomerTag,
    CustomField,
    CustomFieldValue,
    HealthRecord,
    OrderLink,
    Purchase,
)
from apps.customer.phones import candidates
from apps.customer.schemas import (
    ActivityListIn,
    ActivityPage,
    ByPhoneIn,
    ConsentHistoryIn,
    ConsentPage,
    ConsentStateIn,
    ConsentStateOut,
    CustomerDetailOut,
    CustomerExportIn,
    CustomerFilters,
    CustomerListIn,
    CustomerPage,
    CustomerRefIn,
    CustomerStatsIn,
    CustomerStatsOut,
    DivergencePage,
    DivergencesIn,
    ExportOut,
    FieldListIn,
    FieldPage,
    FieldRefIn,
    FieldRow,
    GroupListIn,
    GroupPage,
    GroupRefIn,
    GroupRow,
    HealthDetailIn,
    HealthOut,
    OrderCustomerOut,
    OrderIn,
    OrderListIn,
    OrderNamedOut,
    OrderPage,
    PageIn,
    PhoneMatchOut,
    PurchaseListIn,
    PurchasePage,
    TagListIn,
    TagPage,
    TagRefIn,
    TagRow,
)
from apps.customer.search import normalize, search_term
from base import operations as platform
from base.business import currency_decimals
from base.ordering import list_order

CUSTOMER_UNAVAILABLE = _("This customer is no longer available.")
NO_CUSTOMER_MATCHES = _("No customer matches “%(reference)s”.")
SEVERAL_CUSTOMERS_MATCH = _(
    "Several customers match “%(reference)s”: give their id, phone or email."
)
GROUP_UNAVAILABLE = _("That group no longer exists.")
TAG_UNAVAILABLE = _("That tag no longer exists.")
FIELD_UNAVAILABLE = _("That field no longer exists.")
SALES_UNAVAILABLE = _("Sales is not active in this business.")
SEVERAL_MATCH = _("Several match “%(reference)s”: give the id.")

CUSTOMER_UNAVAILABLE_CODE = "customer.customer_unavailable"
CUSTOMER_AMBIGUOUS_CODE = "customer.customer_ambiguous"

#: The columns of the CSV export (CUSTOMER-F09): the import's, then the figures and the segments.
EXPORT_COLUMNS = (
    "name",
    "email",
    "phone",
    "tax_id",
    "company_name",
    "address",
    "city",
    "postal_code",
    "country",
    "lifecycle_stage",
    "notes",
    "source",
    "is_active",
    "total_purchases",
    "total_spent",
    "last_purchase_at",
    "created_at",
    "groups",
    "tags",
)
#: What a spreadsheet runs as a formula when a cell starts with it (OWASP «CSV injection»).
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def business_country(ctx: OperationContext) -> str:
    """The country a phone without prefix belongs to (CUSTOMER-F10, F11): ``ctx``'s business's, as erplora.com
    registered it, Spain without one (``base.operations.business_country``). Saving a card and every lookup by its
    phone, in this app and in the others (``find_customer``), read it here, so the two never part (hub#527)."""
    return platform.business_country(ctx.scope)


# ── Lookups shared with services.py ─────────────────────────────────────────────────────────────


def _matching_ids(ctx: OperationContext, reference: str) -> list[UUID]:
    """The live cards whose email, phone or name is exactly ``reference`` (at most two: one is enough)."""
    text = reference.strip()
    cards = Customer.objects.live()
    if "@" in text:
        return list(cards.filter(email__iexact=text).values_list("id", flat=True)[:2])
    numbers = candidates(text, business_country(ctx))
    if numbers:
        return list(
            cards.filter(phone__in=numbers)
            .order_by("name", "id")
            .values_list("id", flat=True)[:2]
        )
    wanted = normalize(text)
    found = cards.filter(search_text__startswith=wanted).values_list("id", "name")
    return [card_id for card_id, name in found if normalize(name) == wanted][:2]


def find_customer(
    ctx: OperationContext,
    customer_id: UUID | None,
    reference: str | None,
    *,
    lock: bool = False,
    live: bool = True,
) -> Customer:
    """The card ``customer_id`` names or, without it, the one live card ``reference`` names, a phone read in ``ctx``'s
    business's country as the card's was saved (``business_country``).

    ``lock`` locks its row until the end of the command's transaction; ``live=False`` also finds a
    deleted, merged or erased card, by its id only. ``NotFound`` (``customer.customer_unavailable``)
    when there is none and ``Conflict`` (``customer.customer_ambiguous``) when the reference fits
    several cards.
    """
    if customer_id is None:
        ids = _matching_ids(ctx, reference or "")
        if not ids:
            raise NotFound(
                NO_CUSTOMER_MATCHES % {"reference": reference},
                code=CUSTOMER_UNAVAILABLE_CODE,
            )
        if len(ids) > 1:
            raise Conflict(
                SEVERAL_CUSTOMERS_MATCH % {"reference": reference},
                code=CUSTOMER_AMBIGUOUS_CODE,
            )
        customer_id = ids[0]
    cards = Customer.objects.live() if live else Customer.objects.all()
    if lock:
        cards = cards.select_for_update()
    customer = cards.filter(pk=customer_id).first()
    if customer is None:
        raise NotFound(CUSTOMER_UNAVAILABLE, code=CUSTOMER_UNAVAILABLE_CODE)
    return customer


def _by_id(rows: QuerySet, item_id: UUID, *, missing, code: str):
    """The row of ``rows`` with ``item_id``; ``NotFound`` (``code``) when there is none."""
    found = rows.filter(pk=item_id).first()
    if found is None:
        raise NotFound(missing, code=code)
    return found


def _find_named(
    model, item_id: UUID | None, name: str | None, *, missing, code: str, lock: bool
):
    rows = model.objects.select_for_update() if lock else model.objects.all()
    if item_id is not None:
        return _by_id(rows, item_id, missing=missing, code=code)
    matches = list(rows.filter(name__iexact=(name or "").strip()))
    active = [row for row in matches if row.is_active]
    chosen = active or matches
    if not chosen:
        raise NotFound(missing, code=code)
    if len(chosen) > 1:
        raise Conflict(
            SEVERAL_MATCH % {"reference": name},
            code=code.replace("_unavailable", "_ambiguous"),
        )
    return chosen[0]


def find_group(
    group_id: UUID | None, name: str | None, *, lock: bool = False
) -> CustomerGroup:
    return _find_named(
        CustomerGroup,
        group_id,
        name,
        missing=GROUP_UNAVAILABLE,
        code="customer.group_unavailable",
        lock=lock,
    )


def find_tag(
    tag_id: UUID | None, name: str | None, *, lock: bool = False
) -> CustomerTag:
    return _find_named(
        CustomerTag,
        tag_id,
        name,
        missing=TAG_UNAVAILABLE,
        code="customer.tag_unavailable",
        lock=lock,
    )


def find_field(
    field_id: UUID | None, name: str | None, *, lock: bool = False
) -> CustomField:
    return _find_named(
        CustomField,
        field_id,
        name,
        missing=FIELD_UNAVAILABLE,
        code="customer.field_unavailable",
        lock=lock,
    )


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


def page(rows: QuerySet, params: PageIn) -> dict:
    """One page of ``rows`` (already ordered with the id as the tie-break) and how many there are."""
    return {
        "rows": list(rows[params.offset : params.offset + params.limit]),
        "total": rows.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


def _ordered(rows: QuerySet, column: str, descending: bool) -> QuerySet:
    """``rows`` by ``column``, empties last, the id in the list's direction as the tie-break."""
    return rows.order_by(*list_order(column, descending=descending, nulls_last=True))


def _filtered_customers(params: CustomerFilters) -> QuerySet:
    cards = Customer.objects.live()
    term = search_term(params.search or "")
    if term:
        cards = cards.filter(search_text__contains=term)
    for field in ("name", "email", "tax_id", "company_name"):
        value = (getattr(params, field) or "").strip()
        if value:
            cards = cards.filter(**{f"{field}__icontains": value})
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


def _customers(params: CustomerFilters) -> QuerySet:
    return _ordered(_filtered_customers(params), params.sort, params.descending)


def _customer_count(relation: str) -> Count:
    return Count(
        relation, filter=Q(**{f"{relation}__deleted_at__isnull": True}), distinct=True
    )


# ── Customers ───────────────────────────────────────────────────────────────────────────────────


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
    return page(_customers(params), params)


@operation(
    "customer.customer.detail",
    kind="query",
    permission="customer.view",
    input=CustomerRefIn,
    output=CustomerDetailOut,
    ai=AI(
        "Retrieves a customer's whole card by its id or by its exact name, phone or email: contact and tax details, "
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


def _cell(value) -> str:
    """One CSV cell as text, with an apostrophe in front of what a spreadsheet would run."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = value.isoformat() if hasattr(value, "isoformat") else str(value)
    return f"'{text}" if text.startswith(FORMULA_STARTS) else text


@operation(
    "customer.customer.export",
    kind="query",
    permission="customer.export",
    input=CustomerExportIn,
    output=ExportOut,
    ai=AI(
        "Exports every customer that matches the search and filters as a CSV file, with contact details, stage, "
        "figures, groups and tags. It hands out personal data.",
        risk="high",
        asks={
            "en": ("download a CSV of every customer", "give me a file with all my customers"),
            "es": ("descárgame los clientes en un CSV", "exporta las clientas a un fichero"),
        },
    ),
)
def export_customers(ctx: OperationContext, params: CustomerExportIn) -> dict:
    cards = _customers(params).prefetch_related("groups", "tags")
    # «Spent» with the decimals of the business's currency (its country's: 0 in JPY), never two fixed.
    decimals = currency_decimals(platform.business_currency(ctx.scope))
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(EXPORT_COLUMNS)
    count = 0
    for customer in cards:
        values = {
            **{column: getattr(customer, column, None) for column in EXPORT_COLUMNS},
            "total_spent": f"{Decimal(customer.total_spent).scaleb(-decimals):.{decimals}f}",
            "groups": "; ".join(sorted(group.name for group in customer.groups.all())),
            "tags": "; ".join(sorted(tag.name for tag in customer.tags.all())),
        }
        writer.writerow([_cell(values[column]) for column in EXPORT_COLUMNS])
        count += 1
    return {
        "filename": "customers.csv",
        "content_type": "text/csv",
        "rows": count,
        "csv": buffer.getvalue(),
    }


# ── Groups, tags and custom fields ──────────────────────────────────────────────────────────────


def _groups() -> QuerySet:
    """The groups as their list shows them, with how many live cards are in each."""
    return CustomerGroup.objects.annotate(customer_count=_customer_count("customers"))


def _tags() -> QuerySet:
    """The tags as their list shows them, with how many live cards have each."""
    return CustomerTag.objects.annotate(customer_count=_customer_count("customers"))


@operation(
    "customer.group.list",
    kind="query",
    permission="customer.view",
    input=GroupListIn,
    output=GroupPage,
    ai=AI(
        "Lists the customer groups with how many customers are in each, active and inactive.",
        asks={
            "en": ("what customer groups are there?", "how many people are in the VIP group?"),
            "es": ("¿qué grupos tenemos?", "¿cuánta gente hay en el grupo VIP?"),
        },
    ),
)
def list_groups(ctx: OperationContext, params: GroupListIn) -> dict:
    groups = _groups()
    if params.search:
        groups = groups.filter(
            Q(name__icontains=params.search) | Q(description__icontains=params.search)
        )
    filters = {
        "is_active": params.is_active,
        "color": params.color,
        "customer_count__gte": params.customers_min,
        "customer_count__lte": params.customers_max,
    }
    groups = groups.filter(
        **{lookup: value for lookup, value in filters.items() if value is not None}
    )
    return page(_ordered(groups, params.sort, params.descending), params)


@operation(
    "customer.tag.list",
    kind="query",
    permission="customer.view",
    input=TagListIn,
    output=TagPage,
    ai=AI(
        "Lists the customer tags with how many customers have each, active and inactive.",
        asks={
            "en": ("which tags do we have?", "how many clients are tagged vegan?"),
            "es": ("¿qué etiquetas usamos?", "¿cuántos clientes llevan la etiqueta habitual?"),
        },
    ),
)
def list_tags(ctx: OperationContext, params: TagListIn) -> dict:
    tags = _tags()
    if params.search:
        tags = tags.filter(name__icontains=params.search)
    filters = {"is_active": params.is_active, "color": params.color}
    tags = tags.filter(
        **{lookup: value for lookup, value in filters.items() if value is not None}
    )
    return page(_ordered(tags, params.sort, params.descending), params)


@operation(
    "customer.field.list",
    kind="query",
    permission="customer.view",
    input=FieldListIn,
    output=FieldPage,
    ai=AI(
        "Lists the custom fields defined for the customers' cards, with their type, options and whether they are "
        "required.",
        asks={
            "en": ("what custom fields do we have?", "which extra fields are on the customer card?"),
            "es": ("¿qué campos extra tiene la ficha?", "¿qué datos pedimos a los clientes además del nombre?"),
        },
    ),
)
def list_fields(ctx: OperationContext, params: FieldListIn) -> dict:
    fields = CustomField.objects.all()
    if params.search:
        fields = fields.filter(name__icontains=params.search)
    filters = {
        "field_type": params.field_type,
        "is_required": params.is_required,
        "is_active": params.is_active,
    }
    fields = fields.filter(
        **{lookup: value for lookup, value in filters.items() if value is not None}
    )
    return page(_ordered(fields, params.sort, params.descending), params)


# Not assistant tools: what names a group, a tag or a custom field on the card of a write (``schemas.A_GROUP``,
# ``A_TAG``, ``A_FIELD``), also one no longer active, which a change brings back; the model finds them in their lists.
# Said by its name (``schemas.A_GROUP_SAID``…), the one its write finds by it (``find_group``…, hub#1280).
@operation(
    "customer.group.detail",
    kind="query",
    permission="customer.view",
    input=GroupRefIn,
    output=GroupRow,
    ai=INTERNAL,
)
def group_detail(ctx: OperationContext, data: GroupRefIn) -> CustomerGroup:
    group_id = data.id if data.id is not None else find_group(None, data.group).id
    return _by_id(_groups(), group_id, missing=GROUP_UNAVAILABLE, code="customer.group_unavailable")


@operation(
    "customer.tag.detail",
    kind="query",
    permission="customer.view",
    input=TagRefIn,
    output=TagRow,
    ai=INTERNAL,
)
def tag_detail(ctx: OperationContext, data: TagRefIn) -> CustomerTag:
    tag_id = data.id if data.id is not None else find_tag(None, data.tag).id
    return _by_id(_tags(), tag_id, missing=TAG_UNAVAILABLE, code="customer.tag_unavailable")


@operation(
    "customer.field.detail",
    kind="query",
    permission="customer.view",
    input=FieldRefIn,
    output=FieldRow,
    ai=INTERNAL,
)
def field_detail(ctx: OperationContext, data: FieldRefIn) -> CustomField:
    return find_field(data.id, data.field)


# ── A card's timeline, purchases, consent and orders ────────────────────────────────────────────


@operation(
    "customer.activity.list",
    kind="query",
    permission="customer.view",
    input=ActivityListIn,
    output=ActivityPage,
    ai=AI(
        "Lists a customer's activity history, newest first: notes, purchases, voids, consent decisions, merges and "
        "other apps' entries.",
        asks={
            "en": (
                "what's been going on with Pedro?",
                "show Lucía's history",
                "has anything happened with Javier lately?",
            ),
            "es": ("¿qué ha pasado con Pedro últimamente?", "enséñame el historial de Lucía"),
        },
    ),
)
def list_activity(ctx: OperationContext, params: ActivityListIn) -> dict:
    customer = find_customer(ctx, params.customer_id, params.customer)
    entries = Activity.objects.filter(customer=customer)
    if params.search:
        entries = entries.filter(
            Q(text__icontains=params.search) | Q(title__icontains=params.search)
        )
    return page(entries.order_by("-created_at", "-id"), params)


@operation(
    "customer.purchase.list",
    kind="query",
    permission="customer.view",
    input=PurchaseListIn,
    output=PurchasePage,
    ai=AI(
        "Paginated purchase history of a customer: each sale with its amount in cents, currency and status (paid or "
        "voided); voided ones are kept.",
        asks={
            "en": ("what has Sara bought?", "how much has Pedro spent with us?", "show Ana's purchases"),
            "es": ("¿qué ha comprado Sara?", "¿cuánto se ha gastado Pedro con nosotros?", "las compras de Ana"),
        },
    ),
)
def list_purchases(ctx: OperationContext, params: PurchaseListIn) -> dict:
    customer = find_customer(ctx, params.customer_id, params.customer)
    purchases = Purchase.objects.filter(customer=customer)
    if params.search:
        purchases = purchases.filter(sale_id__icontains=params.search.strip())
    filters = {
        "status": params.status,
        "recorded_at__date__gte": params.recorded_from,
        "recorded_at__date__lte": params.recorded_to,
    }
    purchases = purchases.filter(
        **{lookup: value for lookup, value in filters.items() if value is not None}
    )
    return page(_ordered(purchases, params.sort, params.descending), params)


@operation(
    "customer.purchase.divergences",
    kind="query",
    permission="customer.view",
    input=DivergencesIn,
    output=DivergencePage,
    ai=AI(
        "Reconciliation audit: the customers whose purchase count or spend disagree with their purchase history. "
        "Empty means healthy.",
        asks={
            "en": ("check the customer spend figures for mismatches", "are the customers' spend totals right?"),
            "es": ("revisa si cuadra el gasto de cada cliente", "¿está bien calculado el gasto de los clientes?"),
        },
    ),
)
def purchase_divergences(ctx: OperationContext, params: DivergencesIn) -> dict:
    confirmed = Q(purchases__status=Purchase.Status.CONFIRMED)
    # The spend is what was paid minus what came back (refund lines carry a negative amount).
    spent = confirmed | Q(purchases__status=Purchase.Status.REFUNDED)
    cards = Customer.objects.live().annotate(
        ledger_purchases=Count("purchases", filter=confirmed),
        ledger_spent=Coalesce(
            Sum("purchases__amount", filter=spent),
            Value(0),
            output_field=IntegerField(),
        ),
    )
    cards = cards.exclude(
        total_purchases=F("ledger_purchases"), total_spent=F("ledger_spent")
    )
    term = normalize(params.search or "")
    if term:
        cards = cards.filter(search_text__contains=term)
    return page(cards.order_by("name", "id"), params)


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
            | Q(contact_point__icontains=text)
            | Q(notice_text__icontains=text)
            | Q(reason__icontains=text)
        )
    return page(facts.order_by("-occurred_at", "-created_at", "-id"), params)


@operation(
    "customer.order.customer",
    kind="query",
    permission="customer.view",
    input=OrderIn,
    output=OrderCustomerOut,
    ai=AI(
        "Returns the customer linked to an open order, if any, so the till can put her back on a restored check.",
        asks={
            "en": ("who's on this order?", "whose tab is this?"),
            "es": ("¿de quién es este pedido?", "¿qué cliente tiene la cuenta abierta?"),
        },
    ),
)
def order_customer(ctx: OperationContext, data: OrderIn) -> dict:
    link = OrderLink.objects.filter(
        order_id=data.order_id, customer__deleted_at__isnull=True
    ).first()
    return {
        "order_id": data.order_id,
        "customer_id": link.customer_id if link else None,
    }


@operation(
    "customer.order.list",
    kind="query",
    permission="customer.view",
    input=OrderListIn,
    output=OrderPage,
    expose_api=True,
    ai=AI(
        "Lists the order ids linked to a customer, newest first. The amounts live in the sale app.",
        asks={
            "en": ("what orders does Pedro have?", "list Ana's orders"),
            "es": ("¿qué pedidos tiene el cliente Pedro?", "los pedidos de la clienta Ana"),
        },
    ),
)
def list_orders(ctx: OperationContext, params: OrderListIn) -> dict:
    customer = find_customer(ctx, params.customer_id, params.customer)
    links = OrderLink.objects.filter(customer=customer)
    if params.search:
        links = links.filter(order_id__icontains=params.search.strip())
    return page(links.order_by("-linked_at", "-id"), params)


#: Sales's read that names one of its records by its id (an open check by ``order_id``).
SALES_NAMES = "sale.record.get"


# Not an assistant tool: what names the open order on the card of ``customer.order.link`` (``schemas.A_ORDER``). The
# order is Sales's, which Customers does not require: its name comes from Sales's own read, through the platform's one
# door (BASE-F84), with that read's permission. Sales off or absent → 409 ``customer.sales_unavailable``.
@operation(
    "customer.order.get",
    kind="query",
    permission="customer.view",
    input=OrderIn,
    output=OrderNamedOut,
    ai=INTERNAL,
)
def get_order(ctx: OperationContext, data: OrderIn) -> dict:
    unavailable = Conflict(str(SALES_UNAVAILABLE), code="customer.sales_unavailable")
    named = platform.call(ctx, SALES_NAMES, {"order_id": str(data.order_id)}, unavailable=unavailable)
    return {"order_id": data.order_id, "name": named.name}



# ── Health data (CUSTOMER-F32) ──────────────────────────────────────────────────────────────────

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


def keeps_fiscal_documents() -> bool:
    """Whether this database holds the card sales of its customers (``fiscal_documents_kept`` on this app's config), of any status: a draft counts
    too, for what it asks is whether a database can go, and that cannot be undone."""
    return Purchase.objects.exists()


def has_live_twin(name: str, phone: str, email: str) -> bool:
    """A live card with the same name, phone and email, the case of the name and the email aside: the same card made
    again (an import of a row already imported, services#152; a card brought back from a copy already, hub#1257).

    Only the three together: two people may share a phone or an email (CUSTOMER-F12).
    """
    return _live_twins(name, phone, email).exists()


def _live_twins(name: str, phone: str, email: str) -> QuerySet[Customer]:
    """The live cards ``has_live_twin`` finds, the oldest first."""
    return Customer.objects.live().filter(name__iexact=name, phone=phone, email__iexact=email).order_by("created_at", "id")


def card_in_business(card: dict) -> UUID | None:
    """hub#1284: the business's live card that is ``card`` of a separate copy (its ``id``, ``name``, ``phone`` and
    ``email`` there), what another app's recovery matches a record of the copy that points at it by, by the rule
    ``cards_not_in_business`` tells a card is not lacking by: the same card while live, the one it was merged into since
    (it lives on in that one, CUSTOMER-F13), or one made again (``has_live_twin``: by hand, or brought back already).
    ``None`` when the business has none: deleted and not made again, gone, or erased (never another card, CUSTOMER-F16).
    """
    seen: set[UUID] = set()
    current = card["id"]
    while current is not None and current not in seen:
        seen.add(current)
        row = Customer.objects.filter(pk=current).values("deleted_at", "merged_into", "erased_at").first()
        if row is None:
            break
        if row["erased_at"] is not None:
            return None
        if row["deleted_at"] is None:
            return current
        current = row["merged_into"]
    return _live_twins(card["name"], card["phone"], card["email"]).values_list("pk", flat=True).first()


#: What a card of a separate copy gives its create (``CustomerIn``), as the copy's columns hold it since
#: ``0001_initial`` (``cards_in_copy``).
CARD_FIELDS = (
    "name",
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
    "source",
    "lifecycle_stage",
    "preferred_channel",
    "notes",
)


def cards_in_copy(conn) -> list[dict]:
    """hub#1257: each live card of a separate copy of the business (not deleted, merged nor erased: those three set
    ``deleted_at``), with its ``id`` there and what ``customer.customer.create`` takes, by id; nothing where the app's
    table is not there. ``conn`` is the copy's direct, read-only connection (``recoverable_from_copy`` on this app's
    config: the copy is no business and has no alias), so it is read by its own SQL over the model's names, never the
    ORM."""
    table = Customer._meta.db_table
    if conn.execute("SELECT to_regclass(%s)", [table]).fetchone()[0] is None:
        return []
    read = ("id", *CARD_FIELDS)
    column = {field: sql.Identifier(Customer._meta.get_field(field).column) for field in (*read, "deleted_at")}
    query = sql.SQL("SELECT {} FROM {} WHERE {} IS NULL ORDER BY {}").format(
        sql.SQL(", ").join(column[field] for field in read), sql.Identifier(table), column["deleted_at"], column["id"]
    )
    return [dict(zip(read, row, strict=True)) for row in conn.execute(query)]


def cards_not_in_business(cards: list[dict]) -> list[dict]:
    """hub#1257: the cards of a separate copy (``cards_in_copy``) the business no longer has, in their order, for
    ``customer.customer.create``. Not lacking: any card it still holds, live, deleted (it comes back the same,
    ``cards_deleted_in_business``), merged into another (it lives on in that one, CUSTOMER-F13) or erased (never
    brought back, CUSTOMER-F16), and one made again (``has_live_twin``: by hand, or brought back already)."""
    held = set(Customer.objects.filter(pk__in=[card["id"] for card in cards]).values_list("pk", flat=True))
    return [
        card
        for card in cards
        if card["id"] not in held and not has_live_twin(card["name"], card["phone"], card["email"])
    ]


def cards_deleted_in_business(cards: list[dict]) -> list[dict]:
    """hub#1306: the cards of a separate copy (``cards_in_copy``) the business still holds deleted (CUSTOMER-F07), in
    their order, for ``customer.customer.restore``: the same card back with all that hangs from it. Never one merged
    into another or erased, and never one made again since (``has_live_twin``)."""
    deleted = set(
        Customer.objects.filter(
            pk__in=[card["id"] for card in cards],
            deleted_at__isnull=False,
            merged_into__isnull=True,
            erased_at__isnull=True,
        ).values_list("pk", flat=True)
    )
    return [
        card
        for card in cards
        if card["id"] in deleted and not has_live_twin(card["name"], card["phone"], card["email"])
    ]
