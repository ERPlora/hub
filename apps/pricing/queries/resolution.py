"""The price of a line (WORKBOOK PRICING-F13).

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
from uuid import UUID

from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation

from apps.customer.queries import find_customer
from apps.inventory import queries as inventory_queries
from apps.inventory.models import UNIT_SPECS, Product, ProductCategory
from apps.pricing.models import DiscountRule, PriceItem, PriceList
from apps.pricing.queries.other_apps import call_service
from apps.pricing.queries.reads import find_list
from apps.pricing.schemas import ResolveIn, ResolveOut
from base import operations as platform
from base.business import business_zone

LIST_UNAVAILABLE = _("The price list %(code)s does not apply on %(day)s: it is deactivated or out of its dates.")


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
        product = inventory_queries.reads.find_product(data.product_id, data.product)
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
