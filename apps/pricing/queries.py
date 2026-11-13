"""Read operations of the pricing app (``READ ONLY``), the lookups services.py shares, and the one
resolution of the price of a line (WORKBOOK PRICING-F13).

Resolution: the candidate lists are the active ones in force on the business day of the sale, in the
business's currency (its country's, ``base.business.get``) and of the sale's tax basis (or following the business), that apply to the
customer (the general one and those of the customer's active groups), or only the one asked for by
name. In each, the highest quantity break the line reaches; the lowest price wins (Business Central's
«best price»); without any, the catalog's. Then one automatic rule, the best for the customer, comes
off that line (Square, Shopify, Toast): with equal discounts, the lower priority, then the lower code.
Money is whole cents, rounded once, half up.
"""

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from typing import Any
from uuid import UUID

import pydantic
from babel.numbers import format_decimal
from psycopg import sql
from django.db.models import CharField, Count, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce, Lower
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.context import OperationContext
from live.errors import AppInactive, Conflict, InvalidPayload, NotFound
from live.operations import UnknownOperation, get, operation

from apps.customer.models import CustomerGroup
from apps.customer.queries import find_customer, find_group
from apps.inventory.models import UNIT_SPECS, Product, ProductCategory
from apps.inventory.queries import find_category, find_product
from apps.pricing.models import DiscountRule, PriceItem, PriceList
from apps.pricing.schemas import (
    CatalogRecordOut,
    CatalogRefIn,
    Page,
    PriceItemDetailOut,
    PriceItemIdIn,
    PriceItemListIn,
    PriceItemOut,
    PriceListListIn,
    PriceListOut,
    PriceListRefIn,
    ResolveIn,
    ResolveOut,
    RuleListIn,
    RuleOut,
    RuleRefIn,
)
from base import operations as platform
from base.business import babel_locale, business_zone
from base.ordering import list_order

#: Candidates named when a text matches several.
MAX_CANDIDATES = 5

LIST_NOT_FOUND = _("This price list does not exist.")
LIST_AMBIGUOUS = _("“%(said)s” matches several price lists: %(names)s. Say which one.")
LIST_UNAVAILABLE = _("The price list %(code)s does not apply on %(day)s: it is deactivated or out of its dates.")
RULE_NOT_FOUND = _("This discount rule does not exist.")
RULE_AMBIGUOUS = _("“%(said)s” matches several discount rules: %(names)s. Say which one.")
ITEM_NOT_FOUND = _("That price no longer exists.")
SERVICES_UNAVAILABLE = _("Services is not active in this business.")
#: A price outside its list, from a quantity on: «Shampoo · VIP prices · from 10» (the list's «Desde»).
FROM_QUANTITY = pgettext_lazy("pricing", "from %(quantity)s")

SERVICE_GET = "service.service.get"


def business_today() -> dt.date:
    """The business's today, on its clock (hub#771): a price list ends at its midnight."""
    return timezone.localdate(timezone=business_zone())


def business_day(moment: dt.datetime | None) -> dt.date:
    """The business day of ``moment`` (its date on the business's clock); today without one."""
    return timezone.localdate(moment, business_zone()) if moment is not None else business_today()


def half_up(value: Fraction) -> int:
    """To the cent, a half away from zero (money here is never negative)."""
    if value < 0:
        return -half_up(-value)
    return int((value * 2 + 1) // 2)


def in_force(on: dt.date) -> Q:
    return (Q(valid_from__isnull=True) | Q(valid_from__lte=on)) & (Q(valid_until__isnull=True) | Q(valid_until__gte=on))


def _page(rows: QuerySet, params, to_row) -> dict:
    page = list(rows[params.offset : params.offset + params.limit])
    return {"rows": [to_row(row) for row in page], "total": rows.count(), "limit": params.limit, "offset": params.offset}


def _named(rows: QuerySet, said: str, *, missing, missing_code: str, ambiguous, ambiguous_code: str):
    """The one row whose code or name is ``said`` (any case), else the one whose name holds it."""
    text = said.strip()
    for lookup in (Q(code__iexact=text), Q(name__iexact=text), Q(name__icontains=text) | Q(code__icontains=text)):
        candidates = list(rows.filter(lookup).order_by(Lower("code"), "id")[: MAX_CANDIDATES + 1])
        if len(candidates) == 1:
            return candidates[0]
        if candidates:
            names = ", ".join(f"{row.name} ({row.code})" for row in candidates[:MAX_CANDIDATES])
            raise Conflict(str(ambiguous) % {"said": text, "names": names}, code=ambiguous_code)
    raise NotFound(str(missing), code=missing_code)


def find_list(list_id: UUID | None, said: str | None, *, lock: bool = False, rows=None) -> PriceList:
    """A price list by its id, or by its code or name as a person says it (active or not). It comes from
    ``rows`` when given (e.g. with what its detail shows): one read, so a deletion committed meanwhile is
    either not seen yet or not found, never a row that vanished between two reads. Never with ``lock``:
    those rows are grouped (the count of prices) and Postgres refuses ``FOR UPDATE`` on a grouped query."""
    if lock and rows is not None:
        raise TypeError("find_list: rows= and lock=True are exclusive (FOR UPDATE is not allowed with GROUP BY)")
    lists = PriceList.objects.all()
    if list_id is None:
        list_id = _named(
            lists,
            said or "",
            missing=LIST_NOT_FOUND,
            missing_code="pricing.price_list_not_found",
            ambiguous=LIST_AMBIGUOUS,
            ambiguous_code="pricing.ambiguous_price_list",
        ).pk
    found = (lists if rows is None else rows).filter(pk=list_id)
    price_list = (found.select_for_update() if lock else found).first()
    if price_list is None:
        raise NotFound(str(LIST_NOT_FOUND), code="pricing.price_list_not_found")
    return price_list


def find_rule(rule_id: UUID | None, said: str | None, *, lock: bool = False) -> DiscountRule:
    """A discount rule by its id, or by its code or name as a person says it (active or not)."""
    rows = DiscountRule.objects.all()
    if rule_id is None:
        rule_id = _named(
            rows,
            said or "",
            missing=RULE_NOT_FOUND,
            missing_code="pricing.rule_not_found",
            ambiguous=RULE_AMBIGUOUS,
            ambiguous_code="pricing.ambiguous_rule",
        ).pk
    found = rows.filter(pk=rule_id)
    rule = (found.select_for_update() if lock else found).first()
    if rule is None:
        raise NotFound(str(RULE_NOT_FOUND), code="pricing.rule_not_found")
    return rule


def live_items() -> QuerySet:
    """The prices that count: of a service, or of a product Inventory has not deleted."""
    return PriceItem.objects.filter(Q(product__isnull=True) | Q(product__is_deleted=False))


# ── Services, by the name of their operations (Services is no requirement) ──────────────────────


def call_service(ctx: OperationContext, service_id: UUID | None, said: str | None):
    """Services' ``service.service.get`` for the caller (its permission applies): a ``ServiceOut``.

    Services off or absent → 409 ``pricing.services_unavailable``; its own refusals (a service that does
    not exist, a name that matches several) reach the caller as they are."""
    unavailable = Conflict(str(SERVICES_UNAVAILABLE), code="pricing.services_unavailable")
    try:
        op = get(SERVICE_GET)
    except UnknownOperation:
        raise unavailable from None
    data = {"id": str(service_id)} if service_id is not None else {"service": said}
    try:
        payload = op.input.model_validate(data)
    except pydantic.ValidationError as invalid:
        fields = {"service": error["msg"] for error in invalid.errors()}
        raise InvalidPayload(next(iter(fields.values())), code="invalid_field", fields=fields) from None
    try:
        return op(ctx, payload)
    except AppInactive:
        raise unavailable from None


# ── Rows ─────────────────────────────────────────────────────────────────────────────────────────


def _group_name() -> Subquery:
    return Subquery(CustomerGroup.objects.filter(pk=OuterRef("customer_group_id")).values("name")[:1])


def _lists() -> QuerySet:
    counted = Q(items__product__isnull=True) | Q(items__product__is_deleted=False)
    return PriceList.objects.annotate(
        customer_group_name=_group_name(), item_count=Count("items", filter=counted, distinct=True)
    )


def list_row(price_list: PriceList) -> dict:
    """A ``PriceListOut``; reads the group's name and the count of prices when the row lacks them."""
    if not hasattr(price_list, "item_count"):
        price_list = _lists().get(pk=price_list.pk)
    return {
        "id": price_list.id,
        "code": price_list.code,
        "name": price_list.name,
        "currency": price_list.currency,
        "tax_included": price_list.tax_included,
        "customer_group_id": price_list.customer_group_id,
        "customer_group_name": price_list.customer_group_name,
        "valid_from": price_list.valid_from,
        "valid_until": price_list.valid_until,
        "is_default": price_list.is_default,
        "is_active": price_list.is_active,
        "item_count": price_list.item_count,
        "updated_at": price_list.updated_at,
    }


def item_row(item: PriceItem) -> dict:
    """A ``PriceItemOut``: a product's name, SKU, unit and catalog price, read from Inventory now, and the currency of
    its list, the one its price is in."""
    product = item.product
    return {
        "id": item.id,
        "price_list_id": item.price_list_id,
        "price_list_code": item.price_list.code,
        "price_list_name": item.price_list.name,
        "kind": "product" if product else "service",
        "product_id": item.product_id,
        "service_id": item.service_id,
        "name": product.name if product else item.service_name,
        "sku": product.sku if product else None,
        "unit": product.unit if product else None,
        "base_price": product.price if product else None,
        "min_quantity": item.min_quantity,
        "price": item.price,
        "currency": item.price_list.currency,
        "updated_at": item.updated_at,
    }


def load_item(item_id: UUID) -> dict:
    return item_row(PriceItem.objects.select_related("price_list", "product").get(pk=item_id))


def item_label(row: dict, language: str) -> str:
    """How a price is named outside its list, in ``language``: its article and its list and, from a quantity on, that
    quantity, as the list's dialogs say it («Shampoo · VIP prices · from 10»)."""
    parts = [row["name"], row["price_list_name"]]
    if row["min_quantity"] != 1:
        quantity = format_decimal(row["min_quantity"], locale=babel_locale(language))
        with translation.override(language):
            parts.append(str(FROM_QUANTITY) % {"quantity": quantity})
    return " · ".join(parts)


def _rules() -> QuerySet:
    return DiscountRule.objects.select_related("category", "product").annotate(customer_group_name=_group_name())


def rule_row(rule: DiscountRule, currency: str) -> dict:
    """A ``RuleOut``, its amount per unit in ``currency`` (the business's: a rule belongs to no list); reads the names
    of what it applies to when the row lacks them."""
    if not hasattr(rule, "customer_group_name"):
        rule = _rules().get(pk=rule.pk)
    return {
        "id": rule.id,
        "code": rule.code,
        "name": rule.name,
        "rule_type": rule.rule_type,
        "percent": rule.percent,
        "amount": rule.amount,
        "currency": currency,
        "buy_quantity": rule.buy_quantity,
        "get_quantity": rule.get_quantity,
        "tiers": [{"min_quantity": Decimal(t["min_quantity"]), "percent": Decimal(t["percent"])} for t in rule.tiers],
        "applies_to": rule.applies_to,
        "category_id": rule.category_id,
        "category_name": rule.category.name if rule.category else None,
        "product_id": rule.product_id,
        "product_name": rule.product.name if rule.product else None,
        "service_id": rule.service_id,
        "service_name": rule.service_name or None,
        # Inventory deletes logically: the relayed reaction switches the rule off seconds later; until then, said.
        "target_deleted": bool(
            (rule.category and rule.category.is_deleted) or (rule.product and rule.product.is_deleted)
        ),
        "customer_group_id": rule.customer_group_id,
        "customer_group_name": rule.customer_group_name,
        "min_quantity": rule.min_quantity,
        "valid_from": rule.valid_from,
        "valid_until": rule.valid_until,
        "priority": rule.priority,
        "is_active": rule.is_active,
        "updated_at": rule.updated_at,
    }


def _status(rows: QuerySet, status: str) -> QuerySet:
    return rows if status == "all" else rows.filter(is_active=status == "active")


# ── Price lists ──────────────────────────────────────────────────────────────────────────────────


@operation(
    "pricing.price_list.list",
    kind="query",
    permission="pricing.view",
    input=PriceListListIn,
    output=Page[PriceListOut],
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "who do I give special conditions to?",
                "show me the special conditions for partners and distributors",
                "how many special conditions are still in force?",
            ),
            "es": (
                "¿para quién tengo condiciones especiales?",
                "enséñame las condiciones de socios y distribuidores",
                "¿cuántas condiciones especiales siguen en vigor?",
            ),
        },
        "description": "List the price lists (the active ones by default): code, name, currency, whether the "
        "prices carry the tax, customer group, dates, whether it is the general list and how many prices it has. "
        "Search by code or name; filter by currency, group, tax or status."
    },
)
def list_price_lists(ctx: OperationContext, params: PriceListListIn) -> dict:
    rows = _status(_lists(), params.status)
    if params.search:
        rows = rows.filter(Q(code__icontains=params.search) | Q(name__icontains=params.search))
    for column in ("code", "name", "currency"):
        value = getattr(params, column)
        if value:
            rows = rows.filter(**{f"{column}__icontains": value})
    if params.customer_group_id:
        rows = rows.filter(customer_group_id=params.customer_group_id)
    if params.tax_basis == "business":
        rows = rows.filter(tax_included__isnull=True)
    elif params.tax_basis:
        rows = rows.filter(tax_included=params.tax_basis == "included")
    rows = rows.order_by(*list_order(params.sort, Lower("code"), descending=params.dir == "desc", nulls_last=True))
    return _page(rows, params, list_row)


@operation(
    "pricing.price_list.get",
    kind="query",
    permission="pricing.view",
    input=PriceListRefIn,
    output=PriceListOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "is the Hospitality one valid all year or does it end?",
                "give me the details of Hospitality, HOST-24",
                "until when is Hospitality valid?",
            ),
            "es": (
                "¿lo de Hostelería vale todo el año o caduca?",
                "dame el detalle de Hostelería, la HOST-24",
                "¿qué fechas tiene la de Hostelería?",
            ),
        },
        "description": "Get one price list by its id, its code or its name (e.g. «wholesale list»).",
    },
)
def get_price_list(ctx: OperationContext, data: PriceListRefIn) -> dict:
    return list_row(find_list(data.id, data.price_list, rows=_lists()))


# ── Prices ───────────────────────────────────────────────────────────────────────────────────────


@operation(
    "pricing.price_item.list",
    kind="query",
    permission="pricing.view",
    input=PriceItemListIn,
    output=Page[PriceItemOut],
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how much is the croissant in each one?",
                "what does the croissant go for everywhere?",
                "show me one by one what each thing costs in Hospitality",
            ),
            "es": (
                "¿cuánto cuesta el croissant en cada una?",
                "¿a cuánto va el croissant en todas?",
                "enséñame uno por uno lo que cuesta cada cosa en la de Hostelería",
            ),
        },
        "description": "List the prices of a price list (named by its code or name), or the prices of one product "
        "or service across every list: the article, its catalog price, the from quantity and the price in cents. "
        "Search by product name or SKU or by service name."
    },
)
def list_price_items(ctx: OperationContext, params: PriceItemListIn) -> dict:
    rows = live_items().select_related("price_list", "product")
    if params.price_list_id or params.price_list:
        rows = rows.filter(price_list=find_list(params.price_list_id, params.price_list))
    if params.product_id:
        rows = rows.filter(product_id=params.product_id)
    if params.service_id:
        rows = rows.filter(service_id=params.service_id)
    if params.kind:
        rows = rows.filter(product__isnull=params.kind == "service")
    if params.search:
        rows = rows.filter(
            Q(product__name__icontains=params.search)
            | Q(product__sku__icontains=params.search)
            | Q(service_name__icontains=params.search)
        )
    rows = rows.annotate(shown_name=Lower(Coalesce("product__name", "service_name", output_field=CharField())))
    column = {"name": "shown_name"}.get(params.sort, params.sort)
    rows = rows.order_by(*list_order(column, "min_quantity", descending=params.dir == "desc", nulls_last=True))
    return _page(rows, params, item_row)


@operation(
    "pricing.price_item.get",
    kind="query",
    permission="pricing.view",
    input=PriceItemIdIn,
    output=PriceItemDetailOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "from how many does the beer's amount in the partners' one apply?",
                "give me the details of the croissant in the partners' one",
                "what exactly does a beer go for with the partners?",
            ),
            "es": (
                "¿a partir de cuántas vale lo de la caña de los socios?",
                "dame el detalle de lo del croissant en la de socios",
                "¿a cuánto va exactamente la caña para los socios?",
            ),
        },
        "description": "Get one price of a price list by its id (see pricing.price_item.list): the article, its list "
        "and the list's currency, the from quantity and the price in cents of that currency."
    },
)
def get_price_item(ctx: OperationContext, data: PriceItemIdIn) -> dict:
    item = live_items().select_related("price_list", "product").filter(pk=data.id).first()
    if item is None:
        raise NotFound(str(ITEM_NOT_FOUND), code="pricing.price_item_not_found")
    row = item_row(item)
    return {**row, "label": item_label(row, ctx.language)}


# ── Rules ────────────────────────────────────────────────────────────────────────────────────────


@operation(
    "pricing.rule.list",
    kind="query",
    permission="pricing.view",
    input=RuleListIn,
    output=Page[RuleOut],
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "show me the promotions running now",
                "which promotions apply by themselves?",
                "what gets cheaper by itself and for whom?",
            ),
            "es": (
                "enséñame las promociones que hay ahora",
                "¿qué promociones se aplican solas?",
                "¿qué se rebaja solo y para quién?",
            ),
        },
        "description": "List the automatic discount rules (the active ones by default): type and value (a percent, "
        "an amount per unit, buy X get Y, tiers by quantity), what each applies to, its customer group, minimum "
        "quantity, dates and priority. Search by code or name."
    },
)
def list_rules(ctx: OperationContext, params: RuleListIn) -> dict:
    rows = _status(_rules(), params.status)
    if params.search:
        rows = rows.filter(Q(code__icontains=params.search) | Q(name__icontains=params.search))
    for column in ("code", "name"):
        value = getattr(params, column)
        if value:
            rows = rows.filter(**{f"{column}__icontains": value})
    for column in ("rule_type", "applies_to", "customer_group_id"):
        value = getattr(params, column)
        if value:
            rows = rows.filter(**{column: value})
    rows = rows.order_by(*list_order(params.sort, Lower("code"), descending=params.dir == "desc", nulls_last=True))
    currency = platform.business_currency(ctx.scope)
    return _page(rows, params, lambda rule: rule_row(rule, currency))


@operation(
    "pricing.rule.get",
    kind="query",
    permission="pricing.view",
    input=RuleRefIn,
    output=RuleOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how big is the happy hour discount and how long does it last?",
                "what does the happy hour consist of?",
                "give me the details of the happy hour, PROMO-HH",
            ),
            "es": (
                "¿de cuánto es el descuento de la happy hour y cuánto dura?",
                "¿en qué consiste la happy hour?",
                "dame el detalle de la happy hour, la PROMO-HH",
            ),
        },
        "description": "Get one discount rule, active or not, by its id, its code or its name (e.g. «summer rule»).",
    },
)
def get_rule(ctx: OperationContext, data: RuleRefIn) -> dict:
    return rule_row(find_rule(data.id, data.rule), platform.business_currency(ctx.scope))


# ── What a price or a rule points at in another app ──────────────────────────────────────────────


@operation(
    "pricing.catalog.get",
    kind="query",
    permission="pricing.view",
    input=CatalogRefIn,
    output=CatalogRecordOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what group is behind the partners' one?",
                "what is the real name of the group behind that identifier?",
                "name the identifier this one points at",
            ),
            "es": (
                "¿qué grupo hay detrás de la de socios?",
                "¿cómo se llama de verdad el grupo de ese identificador?",
                "¿a qué apunta ese identificador y cómo se llama?",
            ),
        },
        "description": "Name by its id the service, the category or the customer group a price list, a price or a "
        "rule points at, as Services, Inventory or Customers name it (a service needs its permission in Services)."
    },
)
def get_catalog_record(ctx: OperationContext, data: CatalogRefIn) -> dict:
    if data.service_id is not None:
        record = call_service(ctx, data.service_id, None)
    elif data.category_id is not None:
        record = find_category(data.category_id, None)
    else:
        record = find_group(data.customer_group_id, None)
    return {"id": record.id, "name": record.name}


# ── The price of a line ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Article:
    """What is being sold: a product of Inventory or a service of Services, with its catalog price."""

    kind: str
    name: str
    base_price: int
    product: Product | None = None
    service_id: UUID | None = None
    category_ids: frozenset = field(default_factory=frozenset)

    def measure(self, quantity: Decimal) -> Fraction:
        """``quantity`` in the unit the price is for (250 g of a coffee priced per kg: 0.25); a service and
        an article priced in its own unit: the quantity itself. What a rule's quantities count."""
        if self.product is None:
            return Fraction(quantity)
        unit = UNIT_SPECS[self.product.unit].factor
        priced_in = UNIT_SPECS[self.product.pricing_unit].factor
        return Fraction(quantity) * unit / priced_in

    def ratio(self, quantity: Decimal) -> Fraction:
        """How many «price quantities» ``quantity`` is (a service: the quantity itself), as Sales counts it."""
        if self.product is None:
            return Fraction(quantity)
        return self.measure(quantity) / Fraction(self.product.price_quantity)


def article_of(ctx: OperationContext, data) -> Article:
    """The product (``product_id``/``product``) or the service (``service_id``/``service``) of ``data``."""
    if data.product_id is not None or data.product is not None:
        product = find_product(data.product_id, data.product)
        categories = ProductCategory.objects.filter(product=product, category__is_deleted=False)
        return Article(
            kind="product",
            name=product.name,
            base_price=product.price,
            product=product,
            category_ids=frozenset(categories.values_list("category_id", flat=True)),
        )
    service = call_service(ctx, data.service_id, data.service)
    return Article(kind="service", name=service.name, base_price=service.price, service_id=service.id)


def _of_article(article: Article) -> Q:
    if article.product is not None:
        return Q(product=article.product)
    return Q(service_id=article.service_id)


def _customer_groups(ctx: OperationContext, data: ResolveIn) -> list[UUID]:
    if data.customer_id is None and data.customer is None:
        return []
    customer = find_customer(ctx, data.customer_id, data.customer)
    return list(customer.groups.filter(is_active=True).values_list("id", flat=True))


def best_list_price(article: Article, quantity: Decimal, lists: list[PriceList]) -> tuple[PriceItem | None, PriceList | None]:
    """In each list, the highest break ``quantity`` reaches; across them, the lowest price (then the code)."""
    by_list = {price_list.pk: price_list for price_list in lists}
    reached: dict[UUID, PriceItem] = {}
    items = PriceItem.objects.filter(_of_article(article), price_list__in=lists, min_quantity__lte=quantity)
    for item in items.order_by("price_list_id", "-min_quantity", "id"):
        reached.setdefault(item.price_list_id, item)
    if not reached:
        return None, None
    item = min(reached.values(), key=lambda row: (row.price, by_list[row.price_list_id].code.lower(), row.price_list_id.int))
    return item, by_list[item.price_list_id]


def candidate_lists(data: ResolveIn, on: dt.date, groups: list[UUID], currency: str) -> list[PriceList]:
    if data.price_list_id is not None or data.price_list is not None:
        asked = find_list(data.price_list_id, data.price_list)
        if not asked.is_active or not PriceList.objects.filter(in_force(on), pk=asked.pk).exists():
            raise Conflict(
                str(LIST_UNAVAILABLE) % {"code": asked.code, "day": on.isoformat()},
                code="pricing.price_list_unavailable",
            )
        return [asked]
    # Only the business's currency and the sale's tax basis compete: different ones are never compared.
    rows = PriceList.objects.filter(
        in_force(on),
        Q(tax_included__isnull=True) | Q(tax_included=data.tax_included),
        is_active=True,
        currency=currency,
    )
    return list(rows.filter(Q(is_default=True) | Q(customer_group_id__in=groups)))


def rule_discount(rule: DiscountRule, line_amount: int, measure: Fraction) -> int:
    """What ``rule`` takes off a line of ``line_amount`` cents, between 0 and the line.

    Its quantities (amount per unit, buy and free, tiers, minimum) count ``measure``: the line's quantity
    in the unit its price is for (as Odoo, Business Central and Dynamics 365
    Commerce count it), so «0,50 € per unit» is per kg of a coffee sold in grams; free units are rounded down.
    """
    if rule.min_quantity is not None and measure < Fraction(rule.min_quantity):
        return 0
    if rule.rule_type == DiscountRule.Type.PERCENT:
        exact = line_amount * Fraction(rule.percent) / 100
    elif rule.rule_type == DiscountRule.Type.FIXED:
        exact = Fraction(rule.amount) * measure
    elif rule.rule_type == DiscountRule.Type.BUY_X_GET_Y:
        free = (measure // (rule.buy_quantity + rule.get_quantity)) * rule.get_quantity
        exact = line_amount * free / measure
    else:
        reached = [tier for tier in rule.tiers if Fraction(Decimal(tier["min_quantity"])) <= measure]
        exact = line_amount * Fraction(Decimal(reached[-1]["percent"])) / 100 if reached else Fraction(0)
    return max(0, min(half_up(exact), line_amount))


def candidate_rules(article: Article, on: dt.date, groups: list[UUID]) -> QuerySet:
    if article.product is not None:
        scope = (
            Q(applies_to=DiscountRule.Scope.ALL)
            | Q(applies_to=DiscountRule.Scope.PRODUCTS)
            | Q(applies_to=DiscountRule.Scope.PRODUCT, product=article.product)
            | Q(applies_to=DiscountRule.Scope.CATEGORY, category_id__in=article.category_ids)
        )
    else:
        scope = (
            Q(applies_to=DiscountRule.Scope.ALL)
            | Q(applies_to=DiscountRule.Scope.SERVICES)
            | Q(applies_to=DiscountRule.Scope.SERVICE, service_id=article.service_id)
        )
    return DiscountRule.objects.filter(
        scope,
        in_force(on),
        Q(customer_group_id__isnull=True) | Q(customer_group_id__in=groups),
        is_active=True,
    )


def best_rule(rules, line_amount: int, measure: Fraction) -> tuple[DiscountRule | None, int]:
    """The rule that takes the most off the line; with equal discounts, the lower priority, then the code."""
    ranked = sorted(
        ((rule_discount(rule, line_amount, measure), rule) for rule in rules),
        key=lambda pair: (-pair[0], pair[1].priority, pair[1].code.lower(), pair[1].id.int),
    )
    if not ranked or ranked[0][0] == 0:
        return None, 0
    discount, rule = ranked[0]
    return rule, discount


def resolve_line(ctx: OperationContext, data: ResolveIn) -> dict:
    """The price of a line (a ``ResolveOut``): the list's or the catalog's, and the best rule's discount."""
    on = business_day(data.when)
    article = article_of(ctx, data)
    groups = _customer_groups(ctx, data)
    currency = platform.business_currency(ctx.scope)
    lists = candidate_lists(data, on, groups, currency)
    item, price_list = best_list_price(article, data.quantity, lists)
    unit_price = item.price if item else article.base_price
    line_amount = half_up(unit_price * article.ratio(data.quantity))
    rule, discount = best_rule(candidate_rules(article, on, groups), line_amount, article.measure(data.quantity))
    return {
        "kind": article.kind,
        "product_id": article.product.id if article.product else None,
        "service_id": article.service_id,
        "name": article.name,
        "quantity": data.quantity,
        "date": on,
        "base_price": article.base_price,
        "unit_price": unit_price,
        "price_list_id": price_list.id if price_list else None,
        "price_list_code": price_list.code if price_list else None,
        "price_list_name": price_list.name if price_list else None,
        "tax_included": price_list.tax_included if price_list else None,
        # Only a list asked for by name may be in another currency (candidate_lists).
        "currency": price_list.currency if price_list else currency,
        "line_amount": line_amount,
        "discount": discount,
        "rule_id": rule.id if rule else None,
        "rule_code": rule.code if rule else None,
        "rule_name": rule.name if rule else None,
        "rule_type": rule.rule_type if rule else None,
        "total": line_amount - discount,
    }


@operation(
    "pricing.price.resolve",
    kind="query",
    permission="pricing.view",
    input=ResolveIn,
    output=ResolveOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "work out what three croissants cost Nuria",
                "how much do three croissants come to for Nuria?",
                "calculate a beer for the hotels' group, with its discount",
            ),
            "es": (
                "calcula lo que cuestan tres croissants para Nuria",
                "¿cuánto paga Nuria por tres croissants con su descuento?",
                "calcula cuánto cuesta una caña para el grupo de hoteles",
            ),
        },
        "description": "The price of a line: give the product (by its name or SKU) or the service (by its name), "
        "and if you know them the customer (name, phone or email), the quantity and the moment. It answers the "
        "catalog price, the price that applies and the price list it comes from (the general list or the "
        "customer's group's; the lowest wins), the automatic discount of the best rule and the total, in cents. "
        "It changes nothing."
    },
)
def resolve_price(ctx: OperationContext, data: ResolveIn) -> dict:
    return resolve_line(ctx, data)


def snapshot_values(rule: DiscountRule) -> dict[str, Any]:
    """The fields of a stored rule that ``schemas.rule_problems`` reads (targets as ids)."""
    return {
        "rule_type": rule.rule_type,
        "percent": rule.percent,
        "amount": rule.amount,
        "buy_quantity": rule.buy_quantity,
        "get_quantity": rule.get_quantity,
        "tiers": rule.tiers,
        "applies_to": rule.applies_to,
        "category_id": rule.category_id,
        "product_id": rule.product_id,
        "service_id": rule.service_id,
        "valid_from": rule.valid_from,
        "valid_until": rule.valid_until,
    }


# ── A separate copy of the business (BASE-F114): what Price Lists gives back from it ─────────────────────────────────

#: What a price of a separate copy is read with: its id there and what ``pricing.price_item.add`` takes, each a column
#: since ``0001_initial``.
PRICE_FIELDS = ("id", "price_list_id", "product_id", "service_id", "price", "min_quantity")


def prices_in_copy(conn) -> list[dict]:
    """Each price of a separate copy of the business that counts there (of a service, or of a product Inventory had not
    deleted: ``live_items``), with what ``PRICE_FIELDS`` names; nothing where the app's table is not there. ``conn`` is
    the copy's direct, read-only connection: it is read by its own SQL over the models' names, never the ORM."""
    item, product = PriceItem._meta, Product._meta
    if conn.execute("SELECT to_regclass(%s)", [item.db_table]).fetchone()[0] is None:
        return []

    def column(meta, field: str) -> sql.Identifier:
        return sql.Identifier(meta.get_field(field).column)

    read = sql.SQL(
        "SELECT {columns} FROM {items} i LEFT JOIN {products} p ON p.{product_pk} = i.{product_id}"
        " WHERE i.{product_id} IS NULL OR NOT p.{deleted} ORDER BY i.{item_pk}"
    ).format(
        columns=sql.SQL(", ").join(
            sql.SQL("i.{}").format(column(item, field))
            for field in ("id", "price_list", "product", "service_id", "price", "min_quantity")
        ),
        items=sql.Identifier(item.db_table),
        products=sql.Identifier(product.db_table),
        product_pk=column(product, "id"),
        product_id=column(item, "product"),
        deleted=column(product, "is_deleted"),
        item_pk=column(item, "id"),
    )
    return [dict(zip(PRICE_FIELDS, row, strict=True)) for row in conn.execute(read)]


def prices_not_in_business(prices: list[dict]) -> list[dict]:
    """The prices of a separate copy (``prices_in_copy``) the business no longer has, in their order, each as
    ``pricing.price_item.add`` takes it with its ``id`` there: its list, its one article (a product or a service), its
    price and its from quantity. Not lacking: one the business still holds, nor one whose place (its list, its article
    and its from quantity) the business has taken again, at whatever price: that one stays as the business has it."""
    held = set(PriceItem.objects.filter(pk__in=[one["id"] for one in prices]).values_list("pk", flat=True))
    taken = set(
        PriceItem.objects.filter(price_list_id__in={one["price_list_id"] for one in prices}).values_list(
            "price_list_id", "product_id", "service_id", "min_quantity"
        )
    )
    return [
        {
            "id": one["id"],
            "price_list_id": one["price_list_id"],
            **({"product_id": one["product_id"]} if one["product_id"] else {"service_id": one["service_id"]}),
            "price": one["price"],
            "min_quantity": one["min_quantity"],
        }
        for one in prices
        if one["id"] not in held
        and (one["price_list_id"], one["product_id"], one["service_id"], one["min_quantity"]) not in taken
    ]
