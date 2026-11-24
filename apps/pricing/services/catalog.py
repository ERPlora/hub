"""Reactions to other apps' events, run as the platform and idempotent: a product deleted or restored, a category
or a customer group deleted, a service renamed."""

from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.inventory.models import Product
from apps.pricing import events
from apps.pricing.models import DiscountRule, PriceItem, PriceList
from apps.pricing.queries.other_apps import call_service
from apps.pricing.schemas import CatalogEventIn, CatalogOut
from apps.pricing.services.writes import _actor, _group_held


def _switch_off(ctx: OperationContext, rules) -> int:
    count = 0
    for rule in rules.filter(is_active=True).select_for_update():
        rule.is_active = False
        rule.updated_by = _actor(ctx)
        rule.save(update_fields=["is_active", "updated_by", "updated_at"])
        record_event(ctx, events.RULE_DEACTIVATED, {"id": str(rule.id)})
        count += 1
    return count


@operation(
    "pricing.catalog.forget_product",
    kind="command",
    permission="pricing.system",
    input=CatalogEventIn,
    output=CatalogOut,
    ai={
        "description": "Platform reaction to inventory.product.deleted: remove the product's prices from every list "
        "and switch off its rules.",
        "risk": "normal",
    },
)
def forget_product(ctx: OperationContext, data: CatalogEventIn) -> dict:
    items = list(PriceItem.objects.select_for_update().filter(product_id=data.id))
    for item in items:
        record_event(ctx, events.PRICE_ITEM_REMOVED, {"id": str(item.id), "price_list_id": str(item.price_list_id)})
        item.delete()
    rules = _switch_off(ctx, DiscountRule.objects.filter(product_id=data.id))
    return {"lists": 0, "items": len(items), "rules": rules}


@operation(
    "pricing.catalog.recall_product",
    kind="command",
    permission="pricing.system",
    input=CatalogEventIn,
    output=CatalogOut,
    ai={
        "description": "Platform reaction to inventory.product.restored: switch back on the product's rules that its "
        "deletion switched off.",
        "risk": "normal",
    },
)
def recall_product(ctx: OperationContext, data: CatalogEventIn) -> dict:
    if not Product.objects.filter(pk=data.id, is_deleted=False).exists():
        # Deleted again before this reached the app: its deletion's own reaction comes next.
        return {"lists": 0, "items": 0, "rules": 0}
    # The platform runs every reaction as the same actor, forget_product's included: a rule the business switched off
    # or touched since carries its own, and is left as the business left it.
    switched_off = DiscountRule.objects.select_for_update().filter(
        product_id=data.id, is_active=False, updated_by=_actor(ctx)
    )
    count = 0
    for rule in switched_off:
        if not _group_held(rule):
            continue
        rule.is_active = True
        rule.save(update_fields=["is_active", "updated_at"])
        record_event(ctx, events.RULE_ACTIVATED, {"id": str(rule.id)})
        count += 1
    return {"lists": 0, "items": 0, "rules": count}


@operation(
    "pricing.catalog.forget_category",
    kind="command",
    permission="pricing.system",
    input=CatalogEventIn,
    output=CatalogOut,
    ai={
        "description": "Platform reaction to inventory.category.deleted: switch off the category's rules.",
        "risk": "normal",
    },
)
def forget_category(ctx: OperationContext, data: CatalogEventIn) -> dict:
    return {"lists": 0, "items": 0, "rules": _switch_off(ctx, DiscountRule.objects.filter(category_id=data.id))}


@operation(
    "pricing.catalog.forget_group",
    kind="command",
    permission="pricing.system",
    input=CatalogEventIn,
    output=CatalogOut,
    ai={
        "description": "Platform reaction to customer.group.deleted: the group's lists stay without group and its "
        "rules are switched off (never does a group's discount spread to everybody).",
        "risk": "normal",
    },
)
def forget_group(ctx: OperationContext, data: CatalogEventIn) -> dict:
    lists = list(PriceList.objects.select_for_update().filter(customer_group_id=data.id))
    for price_list in lists:
        price_list.customer_group_id = None
        price_list.updated_by = _actor(ctx)
        price_list.save(update_fields=["customer_group_id", "updated_by", "updated_at"])
        record_event(ctx, events.PRICE_LIST_UPDATED, {"id": str(price_list.id)})
    rules = _switch_off(ctx, DiscountRule.objects.filter(customer_group_id=data.id))
    return {"lists": len(lists), "items": 0, "rules": rules}


@operation(
    "pricing.catalog.refresh_service",
    kind="command",
    permission="pricing.system",
    input=CatalogEventIn,
    output=CatalogOut,
    ai={
        "description": "Platform reaction to service.service.updated: copy the service's new name into its prices "
        "and rules.",
        "risk": "normal",
    },
)
def refresh_service(ctx: OperationContext, data: CatalogEventIn) -> dict:
    try:
        service = call_service(ctx, data.id, None)
    except (NotFound, Conflict):
        return {"lists": 0, "items": 0, "rules": 0}
    items = PriceItem.objects.filter(service_id=service.id).exclude(service_name=service.name).update(
        service_name=service.name
    )
    if items:
        record_event(ctx, events.PRICE_ITEM_UPDATED, {"service_id": str(service.id)})
    rules = list(DiscountRule.objects.select_for_update().filter(service_id=service.id).exclude(service_name=service.name))
    for rule in rules:
        rule.service_name = service.name
        rule.save(update_fields=["service_name", "updated_at"])
        record_event(ctx, events.RULE_UPDATED, {"id": str(rule.id)})
    return {"lists": 0, "items": items, "rules": len(rules)}
