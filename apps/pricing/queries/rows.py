"""How a price list, a price, a removed price and a discount rule read (``PriceListOut``, ``PriceItemOut``,
``PriceRemovedOut``, ``RuleOut``), and the stored fields of a rule its checks read.
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from babel.numbers import format_decimal
from django.db.models import Count, OuterRef, Q, QuerySet, Subquery
from django.utils import translation
from django.utils.translation import pgettext_lazy
from live.context import OperationContext
from live.errors import OperationError

from apps.customer.models import CustomerGroup
from apps.pricing.models import DiscountRule, PriceItem, PriceList
from apps.pricing.queries import resolution
from apps.pricing.schemas.resolution import ResolveIn
from base import operations as platform
from base.business import babel_locale

#: A price outside its list, from a quantity on: «Shampoo · VIP prices · from 10» (the list's «Desde»).
FROM_QUANTITY = pgettext_lazy("pricing", "from %(quantity)s")


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


def removed_row(ctx: OperationContext, item: PriceItem, item_id: UUID) -> dict:
    """A ``PriceRemovedOut``: ``item``, just taken off its list, and what its article costs there now from the same
    quantity, as the price of a line reads it: on a customer group's list, the best of the general list and that
    group's lists; on any other, that list alone (it is only used by its name); without a price in them, the catalog's.
    A service's catalog price is Services': when it cannot be read, what it costs now is not known."""
    price_list = item.price_list
    row = {
        "id": item_id,
        "name": item.product.name if item.product else item.service_name,
        "price_now": None,
        "price_now_list": None,
        "currency": price_list.currency,
    }
    asked = ResolveIn(product_id=item.product_id, service_id=item.service_id, tax_included=price_list.tax_included is not False)
    try:
        article = resolution.article_of(ctx, asked)
    except OperationError:
        return row
    lists = [price_list]
    if price_list.customer_group_id is not None:
        currency = platform.business_currency(ctx.scope)
        lists = resolution.candidate_lists(asked, resolution.business_today(), [price_list.customer_group_id], currency)
    found, source = resolution.best_list_price(article, item.min_quantity, lists)
    if found is None:
        return {**row, "price_now": article.base_price, "currency": platform.business_currency(ctx.scope)}
    return {**row, "price_now": found.price, "price_now_list": source.name, "currency": source.currency}


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


def snapshot_values(rule: DiscountRule) -> dict[str, Any]:
    """The fields of a stored rule that ``schemas.rules.rule_problems`` reads (targets as ids)."""
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
