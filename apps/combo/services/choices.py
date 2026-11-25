"""A course's choices (COMBO-F06, F12): offer a product, or several at once, last in its course, change one in its
place, remove it and put them in a new order; and the reaction to a product deleted in Inventory (COMBO-F13)."""

from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.combo import events
from apps.combo.models import ChoiceGroup, ChoiceOption
from apps.combo.queries.new_choices import field_refusal, product_said
from apps.combo.queries.offers import sold_by_unit, takeaway_targets
from apps.combo.queries.reads import find_group, find_option
from apps.combo.queries.rows import option_row
from apps.combo.schemas.choices import (
    DroppedOut, DropProductIn, OptionBulkIn, OptionIn, OptionOut, OptionPatchIn, OptionReorderIn,
)
from apps.combo.schemas.courses import GroupOut
from apps.combo.schemas.fields import MAX_OPTIONS, DeletedOut
from apps.combo.schemas.references import OptionRefIn
from apps.combo.services.writes import SYSTEM, _group_out, _next_order, _reordered, _saved
from apps.inventory import queries as inventory
from apps.inventory.models import Product, Unit
from apps.inventory.queries.reads import held

OPTION_EXISTS = _(
    "This course already offers that product. To let it be picked twice, switch on «the same choice may be "
    "picked more than once»."
)
OPTIONS_EXIST = _("This course already offers %(names)s.")
TOO_MANY_OPTIONS = _("A course holds %(max)s choices at most.")
PRODUCT_INACTIVE = _(
    "“%(product)s” is deactivated in Inventory: activate it before putting it in a menu."
)
PRODUCT_NOT_BY_UNIT = _(
    "Only a product sold and priced by the unit can be a menu choice; “%(product)s” is sold by %(unit)s."
)


def _option_event(
    ctx: OperationContext, name: str, option: ChoiceOption, **extra
) -> None:
    payload = {
        "id": str(option.id),
        "group_id": str(option.group_id),
        "combo_id": str(option.group.combo_id),
        "product_id": str(option.product_id),
    }
    record_event(ctx, name, {**payload, **extra})


def _sellable_product(product_id: UUID | None, said: str | None, field: str) -> Product:
    """A product that may become a choice: live, active and sold by units, held for the write that offers
    it (see ``held``)."""
    found = product_said(product_id, said, field)
    live = Product.objects.filter(pk=found.pk, is_deleted=False)
    product = next(iter(held(live[:1])), None)
    if product is None:
        # Deleted between the two reads: Inventory's own refusal, as for one deleted before.
        raise field_refusal(NotFound(str(inventory.reads.PRODUCT_NOT_FOUND)), field)
    if not product.is_active:
        message = str(PRODUCT_INACTIVE) % {"product": product.name}
        raise Conflict(message, code="combo.product_inactive", fields={field: message})
    if not sold_by_unit(product):
        per = f"{product.price_quantity.normalize():f} {product.pricing_unit}"
        unit = product.unit if product.unit != Unit.UNIT else per
        message = str(PRODUCT_NOT_BY_UNIT) % {"product": product.name, "unit": unit}
        raise Conflict(message, code="combo.product_not_by_unit", fields={field: message})
    return product


def _locked_group(data) -> ChoiceGroup:
    """The course a choice belongs to, locked until the end of the command."""
    return find_group(data.group_id, data.combo_id, data.combo, data.group, lock=True)


def _lock_group(group_id: UUID) -> None:
    """Locks the course's row until the end of the command: writes of a course's choices queue on it."""
    list(ChoiceGroup.objects.select_for_update().filter(pk=group_id).values_list("pk", flat=True))


def _option_out(option_id: UUID) -> dict:
    option = ChoiceOption.objects.select_related("product__tax_category", "group__combo").get(pk=option_id)
    return option_row(option, takeaway_targets())


def _product_free(
    group: ChoiceGroup, product: Product, field: str, exclude: UUID | None = None
) -> None:
    if group.options.filter(product=product).exclude(pk=exclude).exists():
        raise Conflict(
            str(OPTION_EXISTS),
            code="combo.option_exists",
            fields={field: str(OPTION_EXISTS)},
        )


@operation(
    "combo.option.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="combo.manage",
    input=OptionIn,
    output=OptionOut,
    expose_api=True,
    ai={
        "description": "Offer a product as a choice of a course («put the lentils in Starters of the menu of the "
        "day», «hake in Mains with 2 euros supplement»): it goes last. The supplement adds to the closed price.",
        "risk": "normal",
        "check": "combo.option.check",
        "asks": {
            "en": (
                "add the salad as a starter in the vegan menu",
                "offer the steak as a main with 3 extra",
            ),
            "es": (
                "incorpora la ensalada a los entrantes del menú vegano",
                "que se pueda elegir entrecot de segundo con 3 de suplemento",
            ),
        },
    },
)
def create_option(ctx: OperationContext, data: OptionIn) -> dict:
    group = _locked_group(data)
    field = "product_id" if data.product_id else "product"
    product = _sellable_product(data.product_id, data.product, field)
    if group.options.count() >= MAX_OPTIONS:
        raise Conflict(
            str(TOO_MANY_OPTIONS) % {"max": MAX_OPTIONS}, code="combo.too_many_options"
        )
    _product_free(group, product, field)
    option = ChoiceOption(
        group=group,
        product=product,
        price_delta=data.price_delta,
        is_available=data.is_available,
        sort_order=_next_order(group.options),
    )
    _saved(option.save, lambda: _product_free(group, product, field))
    _option_event(ctx, events.OPTION_CREATED, option)
    return _option_out(option.id)


@operation(
    "combo.option.bulk_create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="combo.manage",
    input=OptionBulkIn,
    output=GroupOut,
    expose_api=True,
    ai={
        "description": "Offer several products at once in a course, without supplement, in the order given; all "
        "or nothing.",
        "risk": "normal",
        "check": "combo.option.bulk_check",
        "asks": {
            "en": (
                "add soup, salad and gazpacho as starters all at once",
                "put several desserts in the kids' menu in one go",
            ),
            "es": (
                "añade de golpe sopa, ensalada y gazpacho de entrante, en este orden y todos sin suplemento",
                "mete varios postres a la vez en el menú infantil",
            ),
        },
    },
)
def bulk_create_options(ctx: OperationContext, data: OptionBulkIn) -> dict:
    group = _locked_group(data)
    products = [
        _sellable_product(product_id, None, "product_ids")
        for product_id in data.product_ids
    ]
    present = [p for p in products if group.options.filter(product=p).exists()]
    if present:
        message = str(OPTIONS_EXIST) % {"names": ", ".join(p.name for p in present)}
        raise Conflict(
            message, code="combo.option_exists", fields={"product_ids": message}
        )
    if group.options.count() + len(products) > MAX_OPTIONS:
        raise Conflict(
            str(TOO_MANY_OPTIONS) % {"max": MAX_OPTIONS}, code="combo.too_many_options"
        )
    start = _next_order(group.options)
    for offset, product in enumerate(products):
        option = ChoiceOption(group=group, product=product, sort_order=start + offset)
        _saved(option.save, lambda product=product: _product_free(group, product, "product_ids"))
        _option_event(ctx, events.OPTION_CREATED, option)
    return _group_out(group.id)


@operation(
    "combo.option.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="combo.manage",
    input=OptionPatchIn,
    output=OptionOut,
    expose_api=True,
    ai={
        "description": "Change a choice: its supplement, mark it sold out («no flan today in the menu of the "
        "day»: is_available false) or back on offer, or replace its product. It keeps its place.",
        "risk": "normal",
        # The choice as the write will find it, before its card: the yes holds to it (hub#1231).
        "check": "combo.option.get",
        "asks": {
            "en": (
                "the custard is sold out in the kids' menu",
                "make the steak supplement 4 in the vegan menu",
            ),
            "es": (
                "se han acabado las natillas del menú infantil",
                "el entrecot del menú vegano pasa a llevar 4 de suplemento",
            ),
        },
    },
)
def update_option(ctx: OperationContext, data: OptionPatchIn) -> dict:
    found = find_option(
        data.id,
        combo_id=data.combo_id,
        combo=data.combo,
        group_id=data.group_id,
        group=data.group,
        product=data.product,
    )
    # The course first, as adding a choice does: a change of product and a new choice of it queue.
    _lock_group(found.group_id)
    option = find_option(found.id, lock=True)
    sent = data.model_fields_set
    changed: list[str] = []
    if sent & {"new_product_id", "new_product"} and (
        data.new_product_id or data.new_product
    ):
        field = "new_product_id" if data.new_product_id else "new_product"
        product = _sellable_product(data.new_product_id, data.new_product, field)
        if product.id != option.product_id:
            _product_free(option.group, product, field, exclude=option.id)
            option.product = product
            changed.append("product")
    for field in ("price_delta", "is_available"):
        value = getattr(data, field)
        if field in sent and value is not None and getattr(option, field) != value:
            setattr(option, field, value)
            changed.append(field)
    if changed:
        _saved(
            lambda: option.save(update_fields=[*changed, "updated_at"]),
            lambda: _product_free(option.group, option.product, "new_product_id", exclude=option.id),
        )
        _option_event(ctx, events.OPTION_UPDATED, option)
    return _option_out(option.id)


@operation(
    "combo.option.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="combo.manage",
    input=OptionRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Remove a choice from its course.",
        "risk": "high",
        "check": "combo.option.get",
        "asks": {
            "en": (
                "take the gazpacho off the starters of the vegan menu",
                "we no longer offer soup in the kids' menu",
            ),
            "es": (
                "quita el gazpacho de los entrantes del menú vegano",
                "ya no damos sopa en el menú infantil",
            ),
        },
    },
)
def delete_option(ctx: OperationContext, data: OptionRefIn) -> dict:
    option = find_option(
        data.id,
        combo_id=data.combo_id,
        combo=data.combo,
        group_id=data.group_id,
        group=data.group,
        product=data.product,
        lock=True,
    )
    _option_event(ctx, events.OPTION_DELETED, option)
    option_id = option.id
    option.delete()
    return {"id": option_id}


@operation(
    "combo.option.reorder",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="combo.manage",
    input=OptionReorderIn,
    output=GroupOut,
    expose_api=True,
    ai={
        "description": "Put the choices of a course in a new order (the order the till shows them in): give every "
        "choice id, in order.",
        "risk": "normal",
        "asks": {
            "en": (
                "put the salad first among the starters of the vegan menu",
                "sort the desserts of the kids' menu: ice cream, custard, fruit",
            ),
            "es": (
                "que la ensalada salga la primera entre los entrantes del menú vegano",
                "ordena los postres del menú infantil: helado, natillas y fruta",
            ),
        },
    },
)
def reorder_options(ctx: OperationContext, data: OptionReorderIn) -> dict:
    group = _locked_group(data)
    _reordered(group.options.select_for_update(), data.option_ids)
    record_event(
        ctx,
        events.OPTION_REORDERED,
        {"group_id": str(group.id), "combo_id": str(group.combo_id)},
    )
    return _group_out(group.id)


# --- The reaction to Inventory (COMBO-F13) -------------------------------------------------------


@operation(
    "combo.option.drop_product",
    kind="command",
    permission=SYSTEM,
    input=DropProductIn,
    output=DroppedOut,
    ai={
        "description": "Remove from every menu the choices of a product deleted from the catalogue (run by the "
        "platform when Inventory reports the deletion).",
        "risk": "high",
    },
)
def drop_product(ctx: OperationContext, data: DropProductIn) -> dict:
    options = list(
        ChoiceOption.objects.select_for_update()
        .select_related("group")
        .filter(product_id=data.id)
    )
    for option in options:
        _option_event(ctx, events.OPTION_DELETED, option, reason="product_deleted")
        option.delete()
    return {"dropped": len(options)}
