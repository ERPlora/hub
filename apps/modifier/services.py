"""Write operations of the modifier app: one operation = one transaction, with its events in the outbox.

Every check runs before anything is written, so a refusal leaves no trace. A name another row took in
the meantime (two people saving at once) is caught as the database's unique constraint, in a
savepoint, and refused with the same 409 as the check. Changing a row only changes what was sent and
says so only when something changed. A group's row is locked before its options' defaults are
counted, so two saves of the same group wait for each other.
"""

from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.inventory.queries import find_category, find_product
from apps.modifier import events
from apps.modifier.models import (
    ACTOR_MAX_LENGTH,
    MAX_OPTIONS,
    ModifierGroup,
    ModifierLink,
    ModifierOption,
)
from apps.modifier.queries import (
    find_group,
    find_option,
    load_group,
    load_link,
    load_option,
)
from apps.modifier.schemas import (
    MAX_BELOW_MIN,
    DeletedOut,
    DropIn,
    DropOut,
    GroupIn,
    GroupOut,
    GroupPatchIn,
    GroupRefIn,
    LinkIn,
    LinkOut,
    LinkRefIn,
    OptionIn,
    OptionOut,
    OptionPatchIn,
    OptionRefIn,
)
from apps.tax.models import TaxCategory
from apps.tax.queries import resolve_category_text

GROUP_NAME_TAKEN = _("There is already a group with that name.")
OPTION_NAME_TAKEN = _("This group already has an option with that name.")
TOO_MANY_DEFAULTS = _("This group has more options chosen by default than its maximum.")
GROUP_FULL = _("A group holds at most %(max)s options.")
TAX_CATEGORY_UNKNOWN = _("This tax category does not exist in Taxes.")
OWN_LINE_NOT_POSITIVE = _(
    "An option with its own tax category is billed on a line of its own: its supplement must be more than zero."
)
LINK_EXISTS = _("This group already applies there.")
LINK_NOT_FOUND = _("This group does not apply there.")

#: Run only by the platform (events.py): no role holds it, so no person and no API key reaches it.
SYSTEM = "modifier.system"

_CONSTRAINTS = {
    "modifier_group_name_unique": (
        "name",
        GROUP_NAME_TAKEN,
        "modifier.group_name_taken",
    ),
    "modifier_option_name_unique_in_group": (
        "name",
        OPTION_NAME_TAKEN,
        "modifier.option_name_taken",
    ),
    "modifier_link_product_unique": ("__all__", LINK_EXISTS, "modifier.link_exists"),
    "modifier_link_category_unique": ("__all__", LINK_EXISTS, "modifier.link_exists"),
}
#: The database's own rules that are a 422 of a field, not a 409.
_CHECKS = {
    "modifier_option_own_line_positive": ("price_delta", OWN_LINE_NOT_POSITIVE),
}


# Groups (MODIFIER-F02, F03)


@operation(
    "modifier.group.create",
    kind="command",
    permission="modifier.manage",
    input=GroupIn,
    output=GroupOut,
    ai={
        "description": "Create a modifier group (e.g. «Sauces», «Doneness») with how many options must be chosen "
        "(a minimum of 1 or more makes it required; a maximum of 0 is no ceiling) and whether one can repeat.",
        "risk": "normal",
    },
)
def create_group(ctx: OperationContext, data: GroupIn) -> dict:
    _check_group_name(data.name)
    group = ModifierGroup(
        **data.model_dump(), created_by=_actor(ctx), updated_by=_actor(ctx)
    )
    _save(group)
    record_event(ctx, events.GROUP_CREATED, _group_payload(group))
    return load_group(group.id)


@operation(
    "modifier.group.update",
    kind="command",
    permission="modifier.manage",
    input=GroupPatchIn,
    output=GroupOut,
    ai={
        "description": "Change a modifier group, named by its id or its name; what is not sent is kept.",
        "risk": "normal",
    },
)
def update_group(ctx: OperationContext, data: GroupPatchIn) -> dict:
    group = find_group(data.id, data.group, lock=True)
    sent = data.model_dump(
        exclude_unset=True, exclude_none=True, exclude={"id", "group"}
    )
    changes = {
        field: value for field, value in sent.items() if getattr(group, field) != value
    }
    if not changes:
        return load_group(group.id)
    minimum = changes.get("min_choices", group.min_choices)
    maximum = changes.get("max_choices", group.max_choices)
    if maximum and maximum < minimum:
        field = "max_choices" if "max_choices" in changes else "min_choices"
        raise InvalidPayload(
            str(MAX_BELOW_MIN), code="invalid_field", fields={field: str(MAX_BELOW_MIN)}
        )
    if "name" in changes and changes["name"].casefold() != group.name.casefold():
        _check_group_name(changes["name"])
    if (
        "max_choices" in changes
        and maximum
        and group.options.filter(is_default=True).count() > maximum
    ):
        raise _too_many_defaults("max_choices")
    for field, value in changes.items():
        setattr(group, field, value)
    group.updated_by = _actor(ctx)
    _save(group, update_fields=[*changes, "updated_by", "updated_at"])
    record_event(ctx, events.GROUP_UPDATED, _group_payload(group))
    return load_group(group.id)


@operation(
    "modifier.group.delete",
    kind="command",
    permission="modifier.manage",
    input=GroupRefIn,
    output=DeletedOut,
    ai={
        "description": "Delete a modifier group, named by its id or its name, with all its options and the "
        "products and categories it applied to; what was already ordered keeps its copy.",
        "risk": "high",
    },
)
def delete_group(ctx: OperationContext, data: GroupRefIn) -> dict:
    group = find_group(data.id, data.group, lock=True)
    payload, group_id = _group_payload(group), group.id
    group.delete()
    record_event(ctx, events.GROUP_DELETED, payload)
    return {"id": group_id}


# Options (MODIFIER-F04)


@operation(
    "modifier.option.create",
    kind="command",
    permission="modifier.manage",
    input=OptionIn,
    output=OptionOut,
    ai={
        "description": "Add an option to a modifier group (named by its id or name) with its supplement in cents "
        "(negative is a discount, 0 is free); a tax category of its own only when it taxes differently from the "
        "dish; optionally chosen by default.",
        "risk": "normal",
    },
)
def create_option(ctx: OperationContext, data: OptionIn) -> dict:
    group = find_group(data.group_id, data.group, lock=True)
    if group.options.count() >= MAX_OPTIONS:
        message = str(GROUP_FULL) % {"max": MAX_OPTIONS}
        raise Conflict(message, code="modifier.group_full", fields={"name": message})
    _check_option_name(group, data.name)
    tax_category = (
        _tax_category(data.tax_category_key) if data.tax_category_key else None
    )
    _check_own_line(tax_category, data.price_delta)
    if data.is_default:
        _make_room_for_a_default(ctx, group, exclude=None)
    option = ModifierOption(
        group=group,
        **data.model_dump(exclude={"group_id", "group", "tax_category_key"}),
        tax_category=tax_category,
        created_by=_actor(ctx),
        updated_by=_actor(ctx),
    )
    _save(option)
    record_event(ctx, events.OPTION_CREATED, _option_payload(option))
    return load_option(option.id)


@operation(
    "modifier.option.update",
    kind="command",
    permission="modifier.manage",
    input=OptionPatchIn,
    output=OptionOut,
    ai={
        "description": "Change an option, named by its id or its name (and its group when two have one so named); "
        "what is not sent is kept; an empty tax category gives it back the dish's.",
        "risk": "normal",
    },
)
def update_option(ctx: OperationContext, data: OptionPatchIn) -> dict:
    found = find_option(data.id, data.option, data.group_id, data.group)
    group = find_group(found.group_id, None, lock=True)
    option = find_option(found.id, None, lock=True)
    sent = data.model_dump(
        exclude_unset=True,
        exclude_none=True,
        exclude={"id", "option", "group_id", "group"},
    )
    if "tax_category_key" in sent:
        key = sent.pop("tax_category_key")
        sent["tax_category"] = _tax_category(key) if key else None
    changes = {
        field: value for field, value in sent.items() if getattr(option, field) != value
    }
    if not changes:
        return load_option(option.id)
    if "name" in changes and changes["name"].casefold() != option.name.casefold():
        _check_option_name(group, changes["name"])
    _check_own_line(
        changes.get("tax_category", option.tax_category),
        changes.get("price_delta", option.price_delta),
    )
    if changes.get("is_default"):
        _make_room_for_a_default(ctx, group, exclude=option)
    for field, value in changes.items():
        setattr(option, field, value)
    option.updated_by = _actor(ctx)
    _save(option, update_fields=[*changes, "updated_by", "updated_at"])
    record_event(ctx, events.OPTION_UPDATED, _option_payload(option))
    return load_option(option.id)


@operation(
    "modifier.option.delete",
    kind="command",
    permission="modifier.manage",
    input=OptionRefIn,
    output=DeletedOut,
    ai={
        "description": "Delete an option, named by its id or its name (and its group when two have one so named); "
        "what was already ordered keeps its copy.",
        "risk": "high",
    },
)
def delete_option(ctx: OperationContext, data: OptionRefIn) -> dict:
    option = find_option(data.id, data.option, data.group_id, data.group, lock=True)
    payload, option_id = _option_payload(option), option.id
    option.delete()
    record_event(ctx, events.OPTION_DELETED, payload)
    return {"id": option_id}


# Links (MODIFIER-F05, F09)


@operation(
    "modifier.link.attach",
    kind="command",
    permission="modifier.manage",
    input=LinkIn,
    output=LinkOut,
    ai={
        "description": "Apply a modifier group (named by its id or name) to a product (by its id, SKU or name) or to "
        "a category (by its id or name), so that the till asks for it when that is sold.",
        "risk": "normal",
    },
)
def attach_link(ctx: OperationContext, data: LinkIn) -> dict:
    # The group's row is locked: a deletion at the same time waits, or is waited for and then said.
    group = find_group(data.group_id, data.group, lock=True)
    product, category = _target(data)
    if ModifierLink.objects.filter(
        group=group, product=product, category=category
    ).exists():
        raise Conflict(
            str(LINK_EXISTS),
            code="modifier.link_exists",
            fields={"__all__": str(LINK_EXISTS)},
        )
    link = ModifierLink(
        group=group, product=product, category=category, created_by=_actor(ctx)
    )
    _save(link)
    record_event(ctx, events.LINK_ATTACHED, _link_payload(link))
    return load_link(link.id)


@operation(
    "modifier.link.detach",
    kind="command",
    permission="modifier.manage",
    input=LinkRefIn,
    output=DeletedOut,
    ai={
        "description": "Stop applying a modifier group to a product or a category: by the link's id, or by the group "
        "and the product (id, SKU or name) or category (id or name). It can be applied again later.",
        "risk": "normal",
    },
)
def detach_link(ctx: OperationContext, data: LinkRefIn) -> dict:
    if data.id is not None:
        link = ModifierLink.objects.select_for_update().filter(pk=data.id).first()
    else:
        product, category = _target(data)
        group = find_group(data.group_id, data.group)
        link = (
            ModifierLink.objects.select_for_update()
            .filter(group=group, product=product, category=category)
            .first()
        )
    if link is None:
        raise NotFound(str(LINK_NOT_FOUND))
    payload, link_id = _link_payload(link), link.id
    link.delete()
    record_event(ctx, events.LINK_DETACHED, payload)
    return {"id": link_id}


@operation(
    "modifier.link.drop_product",
    kind="command",
    permission=SYSTEM,
    input=DropIn,
    output=DropOut,
    ai={
        "description": "Platform reaction to a product deleted in Inventory: drop the groups hung from it.",
        "risk": "normal",
    },
)
def drop_product_links(ctx: OperationContext, data: DropIn) -> dict:
    return {"dropped": _drop(ctx, ModifierLink.objects.filter(product_id=data.id))}


@operation(
    "modifier.link.drop_category",
    kind="command",
    permission=SYSTEM,
    input=DropIn,
    output=DropOut,
    ai={
        "description": "Platform reaction to a category deleted in Inventory: drop the groups hung from it.",
        "risk": "normal",
    },
)
def drop_category_links(ctx: OperationContext, data: DropIn) -> dict:
    return {"dropped": _drop(ctx, ModifierLink.objects.filter(category_id=data.id))}


# Helpers


def _actor(ctx: OperationContext) -> str:
    return str(ctx.actor)[:ACTOR_MAX_LENGTH]


def _save(row, **options) -> None:
    """Save in a savepoint, so that a name or a link another save took at the same time, or a rule the
    database holds, says so on its field."""
    try:
        with transaction.atomic():
            row.save(**options)
    except IntegrityError as exc:
        for constraint, (field, message, code) in _CONSTRAINTS.items():
            if constraint in str(exc):
                raise Conflict(
                    str(message), code=code, fields={field: str(message)}
                ) from exc
        for constraint, (field, message) in _CHECKS.items():
            if constraint in str(exc):
                raise InvalidPayload(str(message), code="invalid_field", fields={field: str(message)}) from exc
        raise


def _check_group_name(name: str) -> None:
    if ModifierGroup.objects.filter(name__iexact=name).exists():
        raise Conflict(
            str(GROUP_NAME_TAKEN),
            code="modifier.group_name_taken",
            fields={"name": str(GROUP_NAME_TAKEN)},
        )


def _check_option_name(group: ModifierGroup, name: str) -> None:
    if group.options.filter(name__iexact=name).exists():
        raise Conflict(
            str(OPTION_NAME_TAKEN),
            code="modifier.option_name_taken",
            fields={"name": str(OPTION_NAME_TAKEN)},
        )


def _tax_category(text: str) -> TaxCategory:
    """The active tax category named by its key, its name in any language or a learned alias (Taxes reads it)."""
    key, _matched = resolve_category_text(text)
    tax_category = (
        TaxCategory.objects.filter(key=key, is_active=True).first() if key else None
    )
    if tax_category is None:
        message = str(TAX_CATEGORY_UNKNOWN)
        raise InvalidPayload(
            message, code="invalid_field", fields={"tax_category_key": message}
        )
    return tax_category


def _check_own_line(tax_category: TaxCategory | None, price_delta: int) -> None:
    if tax_category is not None and price_delta <= 0:
        message = str(OWN_LINE_NOT_POSITIVE)
        raise InvalidPayload(
            message, code="invalid_field", fields={"price_delta": message}
        )


def _too_many_defaults(field: str) -> Conflict:
    return Conflict(
        str(TOO_MANY_DEFAULTS),
        code="modifier.too_many_defaults",
        fields={field: str(TOO_MANY_DEFAULTS)},
    )


def _make_room_for_a_default(
    ctx: OperationContext, group: ModifierGroup, exclude: ModifierOption | None
) -> None:
    """A new default in a group of one replaces the old one (said as its change); otherwise the defaults
    never pass the maximum. The group's row is locked by the caller."""
    others = group.options.filter(is_default=True)
    if exclude is not None:
        others = others.exclude(pk=exclude.pk)
    if group.max_choices == 1:
        for previous in others:
            previous.is_default, previous.updated_by = False, _actor(ctx)
            previous.save(update_fields=["is_default", "updated_by", "updated_at"])
            record_event(ctx, events.OPTION_UPDATED, _option_payload(previous))
    elif group.max_choices and others.count() + 1 > group.max_choices:
        raise _too_many_defaults("is_default")


def _target(data):
    """The live product or category a link names: exactly one of them, the other ``None``."""
    if data.product_id is not None or data.product is not None:
        return find_product(data.product_id, data.product), None
    return None, find_category(data.category_id, data.category)


def _drop(ctx: OperationContext, links) -> int:
    dropped = 0
    for link in links.select_for_update().order_by("id"):
        payload = _link_payload(link)
        link.delete()
        record_event(ctx, events.LINK_DETACHED, payload)
        dropped += 1
    return dropped


def _group_payload(group: ModifierGroup) -> dict:
    return {"id": str(group.id), "name": group.name}


def _option_payload(option: ModifierOption) -> dict:
    return {
        "id": str(option.id),
        "group_id": str(option.group_id),
        "name": option.name,
        "price_delta": option.price_delta,
    }


def _link_payload(link: ModifierLink) -> dict:
    return {
        "id": str(link.id),
        "group_id": str(link.group_id),
        "product_id": str(link.product_id) if link.product_id else None,
        "category_id": str(link.category_id) if link.category_id else None,
    }
