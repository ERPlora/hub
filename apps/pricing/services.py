"""Write operations of the pricing app: one operation = one transaction, with its events in the outbox.

A refusal writes nothing and records no event; it carries the field it is about, so the form puts it
next to it. Codes are unique whatever their case (the database's index decides, also between two
people saving at once); at most one list is general: making one general takes the mark from the other
in a savepoint, and if another choice wins the race (the index says so), it is tried again, so the last
one stays (WORKBOOK «Para quien lo mantiene»).
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound, OperationError
from live.operations import operation
from live.outbox import record_event

from apps.customer.models import CustomerGroup
from apps.customer.queries import find_group
from apps.inventory.models import fits_unit, increment_of
from apps.inventory.queries import find_category, find_product
from apps.pricing import events
from apps.pricing.models import ACTOR_MAX_LENGTH, DiscountRule, PriceItem, PriceList
from apps.pricing.queries import (
    ITEM_NOT_FOUND,
    call_service,
    find_list,
    find_rule,
    item_row,
    list_row,
    live_items,
    load_item,
    rule_row,
    snapshot_values,
)
from apps.pricing.schemas import (
    BUSINESS_CURRENCY,
    DEFAULT_CURRENCY,
    DEFAULT_HAS_GROUP,
    RANGE_BACKWARDS,
    SCOPE_TARGETS,
    TYPE_VALUES,
    CatalogEventIn,
    CatalogOut,
    DeletedOut,
    PriceItemIn,
    PriceItemOut,
    PriceItemPatchIn,
    PriceItemRefIn,
    PriceListDefaultIn,
    PriceListIn,
    PriceListOut,
    PriceListPatchIn,
    PriceListRefIn,
    RuleIn,
    RuleOut,
    RulePatchIn,
    RuleRefIn,
    rule_problems,
)

DUPLICATE_LIST_CODE = _("A price list with that code already exists. Pick a different code.")
DUPLICATE_RULE_CODE = _("A discount rule with that code already exists. Pick a different code.")
LIST_INACTIVE = _("A deactivated price list cannot be the general one.")
DEFAULT_BUSY = _("Someone else is changing the general price list right now. Try again in a moment.")
LIST_IS_DEFAULT = _(
    "This is the general price list: make another one general or take its mark off before deactivating it."
)
LIST_ALREADY_INACTIVE = _("That price list is already deactivated.")
LIST_ALREADY_ACTIVE = _("That price list is already active.")
LIST_NOT_FOR_PRICES = _("That price list is not available: it does not exist in this business or it is deactivated.")
ITEM_EXISTS = _("That article already has a price in this list from that quantity.")
QUANTITY_OFF_STEP = _("This quantity does not fit the article's unit: use a multiple of %(step)s.")
RULE_ALREADY_INACTIVE = _("That discount rule is already deactivated.")
RULE_ALREADY_ACTIVE = _("That discount rule is already active.")
RULE_GROUP_DELETED = _(
    "This rule's customer group no longer exists: choose another group or take it off before activating it."
)

LIST_CODE_UNIQUE = "pricing_price_list_code_unique"
ONE_DEFAULT = "pricing_price_list_one_default"
RULE_CODE_UNIQUE = "pricing_rule_code_unique"
ITEM_UNIQUE = {"pricing_price_item_product_unique", "pricing_price_item_service_unique"}
#: Tries of a general list against another choice at the same time (the last one stays).
DEFAULT_TRIES = 3
THOUSANDTHS = Decimal("0.001")


def _actor(ctx: OperationContext) -> str:
    return str(ctx.actor)[:ACTOR_MAX_LENGTH]


def _constraint(error: IntegrityError) -> str | None:
    return getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)


def _quantity(value: Decimal) -> str:
    """A quantity in an event: always three decimals, so its consumers read it the same way."""
    return str(value.quantize(THOUSANDTHS))


def _field_error(error: OperationError, field: str):
    """Another app's refusal of a reference, said under the field it came from."""
    if isinstance(error, NotFound):
        return InvalidPayload(error.message, code="invalid_field", fields={field: error.message})
    return Conflict(error.message, code=error.code, fields={field: error.message})


def _group_id(group_id: UUID | None, said: str | None) -> UUID | None:
    """The id of the customer group named by its id or its name (Customers' lookup); none = no group."""
    if group_id is None and said is None:
        return None
    try:
        return find_group(group_id, said).id
    except (NotFound, Conflict) as error:
        raise _field_error(error, "customer_group_id" if group_id is not None else "customer_group") from None


# ── Price lists ──────────────────────────────────────────────────────────────────────────────────


def _take_default_mark(price_list: PriceList) -> PriceList | None:
    """Takes the general mark from the list that has it (locked); that list, if any."""
    previous = PriceList.objects.select_for_update().filter(is_default=True).exclude(pk=price_list.pk).first()
    if previous is not None:
        previous.is_default = False
        previous.save(update_fields=["is_default", "updated_at"])
    return previous


def _save_list(price_list: PriceList, *, make_default: bool) -> PriceList | None:
    """Saves ``price_list`` (making it the general one if asked); the list that lost the mark, if any."""
    for attempt in range(DEFAULT_TRIES):
        try:
            with transaction.atomic():
                previous = None
                if make_default:
                    previous = _take_default_mark(price_list)
                    price_list.is_default = True
                price_list.save()
            return previous
        except IntegrityError as error:
            constraint = _constraint(error)
            if constraint == LIST_CODE_UNIQUE:
                raise Conflict(
                    str(DUPLICATE_LIST_CODE), code="pricing.duplicate_code", fields={"code": str(DUPLICATE_LIST_CODE)}
                ) from None
            if constraint != ONE_DEFAULT:
                raise
            if attempt == DEFAULT_TRIES - 1:
                # Other choices kept winning the race: said with its code, never as the database's error.
                raise Conflict(str(DEFAULT_BUSY), code="pricing.default_busy") from None
    return None  # unreachable: the last try returns or raises


def _default_changed(ctx: OperationContext, price_list: PriceList, previous: PriceList | None) -> None:
    record_event(
        ctx,
        events.PRICE_LIST_DEFAULT_CHANGED,
        {
            "id": str(price_list.id),
            "is_default": price_list.is_default,
            "previous_id": str(previous.id) if previous else None,
        },
    )


@operation(
    "pricing.price_list.create",
    kind="command",
    permission="pricing.manage",
    input=PriceListIn,
    output=PriceListOut,
    expose_api=True,
    ai={
        "description": "Create a price list: its code (unique, e.g. WHOLESALE) and name, and if wanted its currency, "
        "whether its prices carry the tax, the customer group whose members get it (by name, e.g. VIP), its first "
        "and last day, and whether it is the general list for everybody. It starts with no prices: add them with "
        "pricing.price_item.add.",
        "risk": "normal",
    },
)
def create_price_list(ctx: OperationContext, data: PriceListIn) -> dict:
    actor = _actor(ctx)
    price_list = PriceList(
        code=data.code,
        name=data.name,
        currency=data.currency,
        tax_included=data.tax_included,
        customer_group_id=_group_id(data.customer_group_id, data.customer_group),
        valid_from=data.valid_from,
        valid_until=data.valid_until,
        created_by=actor,
        updated_by=actor,
    )
    previous = _save_list(price_list, make_default=data.is_default)
    record_event(
        ctx,
        events.PRICE_LIST_CREATED,
        {"id": str(price_list.id), "code": price_list.code, "is_default": price_list.is_default},
    )
    if price_list.is_default:
        _default_changed(ctx, price_list, previous)
    return list_row(price_list)


@operation(
    "pricing.price_list.update",
    kind="command",
    permission="pricing.manage",
    input=PriceListPatchIn,
    output=PriceListOut,
    expose_api=True,
    ai={
        "description": "Change a price list, named by its id, code or name: only the fields sent (code, name, "
        "currency, tax, customer group, first and last day). null takes the group, the tax or a day off. The "
        "general list cannot get a group.",
        "risk": "normal",
    },
)
def update_price_list(ctx: OperationContext, data: PriceListPatchIn) -> dict:
    price_list = find_list(data.id, data.price_list, lock=True)
    sent = data.model_fields_set
    changes: dict[str, Any] = {
        name: getattr(data, name)
        for name in ("code", "name", "currency", "tax_included", "valid_from", "valid_until")
        if name in sent and getattr(data, name) != getattr(price_list, name)
    }
    if sent & {"customer_group_id", "customer_group"}:
        group_id = _group_id(data.customer_group_id, data.customer_group)
        if group_id != price_list.customer_group_id:
            changes["customer_group_id"] = group_id
        if group_id is not None and price_list.is_default:
            field = "customer_group" if "customer_group" in sent else "customer_group_id"
            raise InvalidPayload(str(DEFAULT_HAS_GROUP), code="invalid_field", fields={field: str(DEFAULT_HAS_GROUP)})
    if price_list.is_default and changes.get("currency", BUSINESS_CURRENCY) != BUSINESS_CURRENCY:
        message = str(DEFAULT_CURRENCY) % {"currency": BUSINESS_CURRENCY}
        raise InvalidPayload(message, code="invalid_field", fields={"currency": message})
    start = changes.get("valid_from", price_list.valid_from)
    until = changes.get("valid_until", price_list.valid_until)
    if start is not None and until is not None and until < start:
        field = "valid_until" if "valid_until" in sent else "valid_from"
        raise InvalidPayload(str(RANGE_BACKWARDS), code="invalid_field", fields={field: str(RANGE_BACKWARDS)})
    if changes:
        for name, value in changes.items():
            setattr(price_list, name, value)
        price_list.updated_by = _actor(ctx)
        _save_list(price_list, make_default=False)
        record_event(ctx, events.PRICE_LIST_UPDATED, {"id": str(price_list.id)})
    return list_row(price_list)


@operation(
    "pricing.price_list.set_default",
    kind="command",
    permission="pricing.manage",
    input=PriceListDefaultIn,
    output=PriceListOut,
    ai={
        "description": "Make a price list (by its id, code or name) the general one, for every customer: the list "
        "that was general stops being so. With is_default false, take the mark off it (no general list). Only an "
        "active list without customer group can be general.",
        "risk": "high",
    },
)
def set_default_price_list(ctx: OperationContext, data: PriceListDefaultIn) -> dict:
    price_list = find_list(data.id, data.price_list, lock=True)
    if price_list.is_default == data.is_default:
        return list_row(price_list)
    previous = None
    if data.is_default:
        if not price_list.is_active:
            raise Conflict(str(LIST_INACTIVE), code="pricing.price_list_inactive")
        if price_list.customer_group_id is not None:
            raise Conflict(str(DEFAULT_HAS_GROUP), code="pricing.default_has_group")
        if price_list.currency != BUSINESS_CURRENCY:
            raise Conflict(str(DEFAULT_CURRENCY) % {"currency": BUSINESS_CURRENCY}, code="pricing.default_currency")
        price_list.updated_by = _actor(ctx)
        previous = _save_list(price_list, make_default=True)
    else:
        price_list.is_default = False
        price_list.updated_by = _actor(ctx)
        price_list.save(update_fields=["is_default", "updated_by", "updated_at"])
    _default_changed(ctx, price_list, previous)
    return list_row(price_list)


def _switch_list(ctx: OperationContext, data: PriceListRefIn, active: bool) -> dict:
    price_list = find_list(data.id, data.price_list, lock=True)
    if price_list.is_active == active:
        message, code = (
            (LIST_ALREADY_ACTIVE, "pricing.price_list_already_active")
            if active
            else (LIST_ALREADY_INACTIVE, "pricing.price_list_already_inactive")
        )
        raise Conflict(str(message), code=code)
    if not active and price_list.is_default:
        raise Conflict(str(LIST_IS_DEFAULT), code="pricing.price_list_is_default")
    price_list.is_active = active
    price_list.updated_by = _actor(ctx)
    price_list.save(update_fields=["is_active", "updated_by", "updated_at"])
    record_event(ctx, events.PRICE_LIST_ACTIVATED if active else events.PRICE_LIST_DEACTIVATED, {"id": str(price_list.id)})
    return list_row(price_list)


@operation(
    "pricing.price_list.deactivate",
    kind="command",
    permission="pricing.manage",
    input=PriceListRefIn,
    output=PriceListOut,
    ai={
        "description": "Deactivate a price list (by its id, code or name) so it no longer prices new sales; its "
        "prices are kept and pricing.price_list.activate brings it back. Not the general list.",
        "risk": "high",
    },
)
def deactivate_price_list(ctx: OperationContext, data: PriceListRefIn) -> dict:
    return _switch_list(ctx, data, active=False)


@operation(
    "pricing.price_list.activate",
    kind="command",
    permission="pricing.manage",
    input=PriceListRefIn,
    output=PriceListOut,
    ai={
        "description": "Bring a deactivated price list (by its id, code or name) back, so it prices new sales again.",
        "risk": "high",
    },
)
def activate_price_list(ctx: OperationContext, data: PriceListRefIn) -> dict:
    return _switch_list(ctx, data, active=True)


# ── Prices ───────────────────────────────────────────────────────────────────────────────────────


def _check_step(quantity: Decimal, unit: str) -> None:
    """A from quantity in the article's unit and on its step (a service: whole units)."""
    if not fits_unit(quantity, unit):
        message = str(QUANTITY_OFF_STEP) % {"step": f"{increment_of(unit).normalize():f}"}
        raise InvalidPayload(message, code="invalid_field", fields={"min_quantity": message})


def _save_item(item: PriceItem) -> None:
    try:
        with transaction.atomic():
            item.save()
    except IntegrityError as error:
        if _constraint(error) in ITEM_UNIQUE:
            raise Conflict(
                str(ITEM_EXISTS), code="pricing.price_item_exists", fields={"min_quantity": str(ITEM_EXISTS)}
            ) from None
        raise


@operation(
    "pricing.price_item.add",
    kind="command",
    permission="pricing.manage",
    input=PriceItemIn,
    output=PriceItemOut,
    expose_api=True,
    ai={
        "description": "Put the price of a product (by its SKU or name) or a service (by its name) in a price list "
        "(by its code or name), in cents, from a minimum quantity on (1 by default). Repeat the product with "
        "another minimum quantity for volume prices.",
        "risk": "normal",
    },
)
def add_price_item(ctx: OperationContext, data: PriceItemIn) -> dict:
    price_list = find_list(data.price_list_id, data.price_list, lock=True)
    if not price_list.is_active:
        raise Conflict(str(LIST_NOT_FOR_PRICES), code="pricing.price_list_unavailable")
    actor = _actor(ctx)
    item = PriceItem(
        price_list=price_list, price=data.price, min_quantity=data.min_quantity, created_by=actor, updated_by=actor
    )
    if data.product_id is not None or data.product is not None:
        item.product = find_product(data.product_id, data.product)
        _check_step(data.min_quantity, item.product.unit)
    else:
        service = call_service(ctx, data.service_id, data.service)
        _check_step(data.min_quantity, "ud")
        item.service_id, item.service_name = service.id, service.name
    _save_item(item)
    record_event(
        ctx,
        events.PRICE_ITEM_ADDED,
        {
            "id": str(item.id),
            "price_list_id": str(price_list.id),
            "product_id": str(item.product_id) if item.product_id else None,
            "service_id": str(item.service_id) if item.service_id else None,
            "min_quantity": _quantity(item.min_quantity),
            "price": item.price,
        },
    )
    return item_row(item)


def _locked_item(item_id: UUID) -> PriceItem:
    item = live_items().select_for_update(of=("self",)).select_related("price_list", "product").filter(pk=item_id).first()
    if item is None:
        raise NotFound(str(ITEM_NOT_FOUND), code="pricing.price_item_not_found")
    return item


def _named_item(ctx: OperationContext, data: PriceItemRefIn) -> PriceItem:
    """A price by its id, or by its list, its article and its from quantity."""
    if data.id is not None:
        return _locked_item(data.id)
    price_list = find_list(data.price_list_id, data.price_list)
    rows = live_items().filter(price_list=price_list, min_quantity=data.min_quantity)
    if data.product_id is not None or data.product is not None:
        rows = rows.filter(product=find_product(data.product_id, data.product))
    elif data.service_id is not None:
        rows = rows.filter(service_id=data.service_id)
    else:
        # The copy of its name: a price of a service is removed even with Services off.
        rows = rows.filter(service_name__iexact=data.service)
    found = rows.order_by("id").first()
    if found is None:
        raise NotFound(str(ITEM_NOT_FOUND), code="pricing.price_item_not_found")
    return _locked_item(found.pk)


@operation(
    "pricing.price_item.update",
    kind="command",
    permission="pricing.manage",
    input=PriceItemPatchIn,
    output=PriceItemOut,
    expose_api=True,
    ai={
        "description": "Change a price of a price list, by its id (see pricing.price_item.list): its price in cents "
        "or its from quantity.",
        "risk": "normal",
    },
)
def update_price_item(ctx: OperationContext, data: PriceItemPatchIn) -> dict:
    item = _locked_item(data.id)
    if not item.price_list.is_active:
        # As adding one: the prices of a deactivated list stay as they were (they can still be removed).
        raise Conflict(str(LIST_NOT_FOR_PRICES), code="pricing.price_list_unavailable")
    sent = data.model_fields_set
    changes = {
        name: getattr(data, name) for name in ("price", "min_quantity") if name in sent and getattr(data, name) != getattr(item, name)
    }
    if "min_quantity" in changes:
        _check_step(changes["min_quantity"], item.product.unit if item.product else "ud")
    if changes:
        for name, value in changes.items():
            setattr(item, name, value)
        item.updated_by = _actor(ctx)
        _save_item(item)
        record_event(ctx, events.PRICE_ITEM_UPDATED, {"id": str(item.id)})
    return load_item(item.id)


@operation(
    "pricing.price_item.remove",
    kind="command",
    permission="pricing.manage",
    input=PriceItemRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Remove a price from a price list: by its id, or by the list (code or name), the product "
        "(SKU or name) or the service (name) and its from quantity (1 if not said). The article is then charged at "
        "another list's price or the catalog's.",
        "risk": "high",
    },
)
def remove_price_item(ctx: OperationContext, data: PriceItemRefIn) -> dict:
    item = _named_item(ctx, data)
    item_id, list_id = item.id, item.price_list_id
    item.delete()
    record_event(ctx, events.PRICE_ITEM_REMOVED, {"id": str(item_id), "price_list_id": str(list_id)})
    return {"id": item_id}


# ── Rules ────────────────────────────────────────────────────────────────────────────────────────


def _refuse(problems: dict[str, str]) -> None:
    if problems:
        raise InvalidPayload(next(iter(problems.values())), code="invalid_field", fields=problems)


def _tiers(tiers) -> list[dict]:
    return [{"min_quantity": str(tier["min_quantity"]), "percent": str(tier["percent"])} for tier in tiers or []]


def _set_value(rule: DiscountRule, values: dict[str, Any]) -> None:
    """The value(s) of the rule's type; those of the other types, empty."""
    for names in TYPE_VALUES.values():
        for name in names:
            mine = name in TYPE_VALUES[rule.rule_type]
            if name == "tiers":
                rule.tiers = _tiers(values.get("tiers")) if mine else []
            else:
                setattr(rule, name, values.get(name) if mine else None)


def _set_target(ctx: OperationContext, rule: DiscountRule, values: dict[str, Any]) -> None:
    """The category, product or service of the rule's scope (by id or text); the others, empty."""
    rule.category, rule.product, rule.service_id, rule.service_name = None, None, None, ""
    if rule.applies_to not in SCOPE_TARGETS:
        return
    field, id_key, text_key = SCOPE_TARGETS[rule.applies_to]
    target_id, said = values.get(id_key), values.get(text_key)
    try:
        if rule.applies_to == DiscountRule.Scope.CATEGORY:
            rule.category = find_category(target_id, said)
        elif rule.applies_to == DiscountRule.Scope.PRODUCT:
            rule.product = find_product(target_id, said)
        else:
            service = call_service(ctx, target_id, said)
            rule.service_id, rule.service_name = service.id, service.name
    except (NotFound, Conflict) as error:
        if error.code == "pricing.services_unavailable":
            raise
        raise _field_error(error, id_key if target_id is not None else field) from None


def _save_rule(rule: DiscountRule) -> None:
    try:
        with transaction.atomic():
            rule.save()
    except IntegrityError as error:
        if _constraint(error) == RULE_CODE_UNIQUE:
            raise Conflict(
                str(DUPLICATE_RULE_CODE), code="pricing.duplicate_code", fields={"code": str(DUPLICATE_RULE_CODE)}
            ) from None
        raise


@operation(
    "pricing.rule.create",
    kind="command",
    permission="pricing.manage",
    input=RuleIn,
    output=RuleOut,
    ai={
        "description": "Create an automatic discount rule for a line: its code and name, its type with its value "
        "(percent: a percent; fixed: cents off each unit; buy_x_get_y: buy and free units; tiered: percents by "
        "quantity), what it applies to (all, products, services, a category, a product or a service, by name), and "
        "if wanted a customer group, a minimum quantity, first and last day and a priority. A line gets only the "
        "rule that takes the most off.",
        "risk": "normal",
    },
)
def create_rule(ctx: OperationContext, data: RuleIn) -> dict:
    values = data.model_dump()
    _refuse(rule_problems(values))
    actor = _actor(ctx)
    rule = DiscountRule(
        code=data.code,
        name=data.name,
        rule_type=data.rule_type,
        applies_to=data.applies_to,
        min_quantity=data.min_quantity,
        valid_from=data.valid_from,
        valid_until=data.valid_until,
        priority=data.priority,
        created_by=actor,
        updated_by=actor,
    )
    _set_value(rule, values)
    _set_target(ctx, rule, values)
    rule.customer_group_id = _group_id(data.customer_group_id, data.customer_group)
    _save_rule(rule)
    record_event(ctx, events.RULE_CREATED, {"id": str(rule.id), "code": rule.code})
    return rule_row(rule)


_TARGET_KEYS = {key for _field, id_key, text_key in SCOPE_TARGETS.values() for key in (id_key, text_key)}
_PLAIN = ("code", "name", "min_quantity", "valid_from", "valid_until", "priority")
_COMPARED = (
    *_PLAIN,
    "rule_type",
    "applies_to",
    "percent",
    "amount",
    "buy_quantity",
    "get_quantity",
    "tiers",
    "category_id",
    "product_id",
    "service_id",
    "customer_group_id",
)


@operation(
    "pricing.rule.update",
    kind="command",
    permission="pricing.manage",
    input=RulePatchIn,
    output=RuleOut,
    ai={
        "description": "Change a discount rule, named by its id, code or name: only the fields sent. Changing its "
        "type asks for the new type's value; changing what it applies to asks for the new target. null takes the "
        "group, the minimum quantity or a day off.",
        "risk": "normal",
    },
)
def update_rule(ctx: OperationContext, data: RulePatchIn) -> dict:
    rule = find_rule(data.id, data.rule, lock=True)
    sent = data.model_fields_set - {"id", "rule"}
    before = {name: getattr(rule, name) for name in _COMPARED}
    merged = snapshot_values(rule)
    if "rule_type" in sent and data.rule_type != rule.rule_type:
        for name in (name for names in TYPE_VALUES.values() for name in names):
            if name not in sent:
                merged[name] = [] if name == "tiers" else None
    if ("applies_to" in sent and data.applies_to != rule.applies_to) or sent & _TARGET_KEYS:
        for key in _TARGET_KEYS:
            merged[key] = None
    dumped = data.model_dump(include=sent)
    merged.update(dumped)
    _refuse(rule_problems(merged))
    for name in _PLAIN:
        if name in sent:
            setattr(rule, name, dumped[name])
    rule.rule_type, rule.applies_to = merged["rule_type"], merged["applies_to"]
    _set_value(rule, merged)
    if sent & ({"applies_to"} | _TARGET_KEYS):
        _set_target(ctx, rule, merged)
    if sent & {"customer_group_id", "customer_group"}:
        rule.customer_group_id = _group_id(data.customer_group_id, data.customer_group)
    if {name: getattr(rule, name) for name in _COMPARED} != before:
        rule.updated_by = _actor(ctx)
        _save_rule(rule)
        record_event(ctx, events.RULE_UPDATED, {"id": str(rule.id)})
    return rule_row(rule)


def _switch_rule(ctx: OperationContext, data: RuleRefIn, active: bool) -> dict:
    rule = find_rule(data.id, data.rule, lock=True)
    if rule.is_active == active:
        message, code = (
            (RULE_ALREADY_ACTIVE, "pricing.rule_already_active")
            if active
            else (RULE_ALREADY_INACTIVE, "pricing.rule_already_inactive")
        )
        raise Conflict(str(message), code=code)
    group = rule.customer_group_id
    if active and group is not None and not CustomerGroup.objects.filter(pk=group).exists():
        # Its group was deleted in Customers: it would apply to nobody, or, without the group, to everybody.
        raise Conflict(str(RULE_GROUP_DELETED), code="pricing.rule_group_deleted")
    rule.is_active = active
    rule.updated_by = _actor(ctx)
    rule.save(update_fields=["is_active", "updated_by", "updated_at"])
    record_event(ctx, events.RULE_ACTIVATED if active else events.RULE_DEACTIVATED, {"id": str(rule.id)})
    return rule_row(rule)


@operation(
    "pricing.rule.deactivate",
    kind="command",
    permission="pricing.manage",
    input=RuleRefIn,
    output=RuleOut,
    ai={
        "description": "Deactivate a discount rule (by its id, code or name) so it no longer takes anything off new "
        "sales; pricing.rule.activate brings it back. Sales already made do not change.",
        "risk": "high",
    },
)
def deactivate_rule(ctx: OperationContext, data: RuleRefIn) -> dict:
    return _switch_rule(ctx, data, active=False)


@operation(
    "pricing.rule.activate",
    kind="command",
    permission="pricing.manage",
    input=RuleRefIn,
    output=RuleOut,
    ai={
        "description": "Bring a deactivated discount rule (by its id, code or name) back, so it applies to new sales.",
        "risk": "normal",
    },
)
def activate_rule(ctx: OperationContext, data: RuleRefIn) -> dict:
    return _switch_rule(ctx, data, active=True)


# ── Reactions to other apps (run as the platform; idempotent) ────────────────────────────────────


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
