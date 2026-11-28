"""The writes on an option of a group (MODIFIER-F04)."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import operation
from live.outbox import record_event

from apps.inventory.queries.reads import held
from apps.modifier import events
from apps.modifier.models import MAX_OPTIONS, ModifierGroup, ModifierOption
from apps.modifier.queries.reads import find_group, find_option, load_option
from apps.modifier.schemas.fields import DeletedOut
from apps.modifier.schemas.options import OptionIn, OptionOut, OptionPatchIn, OptionRefIn
from apps.modifier.services.defaults import _make_room_for_a_default
from apps.modifier.services.writes import OPTION_NAME_TAKEN, OWN_LINE_NOT_POSITIVE, _actor, _option_payload, _save
from apps.tax.models import TaxCategory
from apps.tax.queries.naming import resolve_category_text

GROUP_FULL = _("A group holds at most %(max)s options.")
TAX_CATEGORY_UNKNOWN = _("This tax category does not exist in Taxes.")


@operation(
    "modifier.option.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="modifier.manage",
    input=OptionIn,
    output=OptionOut,
    ai={
        "description": "Add an option to a modifier group (named by its id or name) with its supplement in cents "
        "(negative is a discount, 0 is free); a tax category of its own only when it taxes differently from the "
        "dish; optionally chosen by default, and the allergens it adds to the dish.",
        "risk": "normal",
        "asks": {
            "en": (
                "add barbecue sauce to the Sauces group for 50 cents",
                "add Double cheese to Extras at one euro",
            ),
            "es": (
                "mete una opción gratis de salsa de yogur en Salsas",
                "que Salsas tenga una opción nueva, Alioli, que venga por defecto",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="modifier.manage",
    input=OptionPatchIn,
    output=OptionOut,
    ai={
        "description": "Change an option, named by its id or its name (and its group when two have one so named): "
        "its name, its supplement, its own tax category, whether it comes chosen by default or the allergens it adds "
        "to the dish; what is not sent is kept, and an empty tax category gives it back the dish's.",
        "risk": "normal",
        "check": "modifier.option.get",
        "asks": {
            "en": (
                "raise the extra cheese to one euro",
                "the house sauce should no longer come preselected",
            ),
            "es": (
                "sube a un euro el extra de queso",
                "que la opción Sin gluten deje de ser la predeterminada",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="modifier.manage",
    input=OptionRefIn,
    output=DeletedOut,
    ai={
        "description": "Delete an option, named by its id or its name (and its group when two have one so named); "
        "what was already ordered keeps its copy.",
        "risk": "high",
        "check": "modifier.option.get",
        "asks": {
            "en": (
                "remove barbecue sauce from the Sauces group",
                "delete the Gluten free option from Extras",
            ),
            "es": (
                "quita la salsa barbacoa del grupo Salsas",
                "borra la opción Sin gluten de Extras, las comandas ya enviadas se quedan como están",
            ),
        },
    },
)
def delete_option(ctx: OperationContext, data: OptionRefIn) -> dict:
    option = find_option(data.id, data.option, data.group_id, data.group, lock=True)
    payload, option_id = _option_payload(option), option.id
    option.delete()
    record_event(ctx, events.OPTION_DELETED, payload)
    return {"id": option_id}


def _check_option_name(group: ModifierGroup, name: str) -> None:
    if group.options.filter(name__iexact=name).exists():
        raise Conflict(
            str(OPTION_NAME_TAKEN),
            code="modifier.option_name_taken",
            fields={"name": str(OPTION_NAME_TAKEN)},
        )


def _tax_category(text: str) -> TaxCategory:
    """The active tax category named by its key, its name in any language or a learned alias (Taxes reads it),
    held for the option that names it (see ``held``)."""
    key, _matched = resolve_category_text(text)
    tax_category = (
        next(iter(held(TaxCategory.objects.filter(key=key, is_active=True)[:1])), None)
        if key
        else None
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
