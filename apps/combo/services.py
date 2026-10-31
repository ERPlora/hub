"""Write operations of the combo app: one operation = one transaction, with its events in the outbox.

Only the fields sent change. A new course goes last in its menu and a new choice last in its course;
``reorder`` takes the whole list and saves it at once. Creating a course locks its menu and creating a
choice locks its course (``select_for_update``), so two people adding the same name or product at once
get one row and a 409, and the caps (20 courses, 40 choices) hold; the unique constraints are the last
net. A product must be live, active and sold by units in Inventory to become a choice. A write holds the
product or tax category it names until it commits (``held``, FOR KEY SHARE): a deletion waits for it, and
one already under way is read once it ends, gone, as one deleted before (a 422 on the field, never a 500).
"""

from uuid import UUID

from django.db import IntegrityError
from django.db.models import Max
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import atomic, operation
from live.outbox import record_event

from apps.combo import events
from apps.combo.models import ACTOR_MAX_LENGTH, ChoiceGroup, ChoiceOption, Combo
from apps.combo.queries import (
    find_combo,
    find_group,
    find_option,
    group_row,
    load_detail,
    option_row,
    sold_by_unit,
    takeaway_targets,
)
from apps.combo.schemas import (
    CEILING_BELOW_FLOOR,
    MAX_GROUPS,
    MAX_OPTIONS,
    ComboDetailOut,
    ComboImageIn,
    ComboImageUploadIn,
    ComboIn,
    ComboPatchIn,
    ComboRefIn,
    DeletedOut,
    DroppedOut,
    DropProductIn,
    GroupIn,
    GroupOut,
    GroupPatchIn,
    GroupRefIn,
    GroupReorderIn,
    OptionBulkIn,
    OptionIn,
    OptionOut,
    OptionPatchIn,
    OptionRefIn,
    OptionReorderIn,
)
from apps.inventory import queries as inventory
from apps.inventory.models import Product, Unit
from apps.inventory.queries import find_product, held
from apps.tax.models import TaxCategory
from base import images

TAX_REQUIRED = _(
    "A menu eaten in needs its own VAT category: without it, it cannot be billed."
)
TAX_UNKNOWN = _("That tax category does not exist in Taxes.")
GROUP_EXISTS = _("That menu already has a course “%(name)s”.")
TOO_MANY_GROUPS = _("A menu holds %(max)s courses at most.")
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
REORDER_MISMATCH = _(
    "The new order has to list every one of them, once, and nothing else."
)

#: Run only by the platform (events.py): no role holds it, so no person and no API key reaches it.
SYSTEM = "combo.system"


# --- Shared steps ----------------------------------------------------------------------------------


def _actor(ctx: OperationContext) -> str:
    return str(ctx.actor)[:ACTOR_MAX_LENGTH]


def _field_refusal(error: NotFound, field: str) -> InvalidPayload:
    """A reference of a write that does not exist is a 422 on its field, not a 404 of the write."""
    return InvalidPayload(
        error.message, code="invalid_field", fields={field: error.message}
    )


def _tax_category(key: str) -> TaxCategory:
    """The active tax category of ``key``, held for the write that names it (see ``held``)."""
    category = next(iter(held(TaxCategory.objects.filter(key=key, is_active=True)[:1])), None)
    if category is None:
        raise InvalidPayload(
            str(TAX_UNKNOWN),
            code="invalid_field",
            fields={"tax_category_key": str(TAX_UNKNOWN)},
        )
    return category


def _needs_tax(supply_kind: str, category: TaxCategory | None) -> None:
    if supply_kind == Combo.SupplyKind.SERVICE and category is None:
        raise InvalidPayload(
            str(TAX_REQUIRED),
            code="invalid_field",
            fields={"tax_category_key": str(TAX_REQUIRED)},
        )


def _combo_event(ctx: OperationContext, name: str, combo: Combo) -> None:
    record_event(ctx, name, {"id": str(combo.id), "name": combo.name})


def _group_event(ctx: OperationContext, name: str, group: ChoiceGroup) -> None:
    record_event(ctx, name, {"id": str(group.id), "combo_id": str(group.combo_id)})


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
    try:
        found = find_product(product_id, said)
    except NotFound as error:
        raise _field_refusal(error, field) from None
    live = Product.objects.filter(pk=found.pk, is_deleted=False)
    product = next(iter(held(live[:1])), None)
    if product is None:
        # Deleted between the two reads: Inventory's own refusal, as for one deleted before.
        raise _field_refusal(NotFound(str(inventory.PRODUCT_NOT_FOUND)), field)
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


def _next_order(rows) -> int:
    last = rows.aggregate(last=Max("sort_order"))["last"]
    return 0 if last is None else last + 1


def _lock_combo(combo_id: UUID) -> None:
    """Locks the menu's row until the end of the command: writes of a menu's courses queue on it."""
    list(Combo.objects.select_for_update().filter(pk=combo_id).values_list("pk", flat=True))


def _lock_group(group_id: UUID) -> None:
    """Locks the course's row until the end of the command: writes of a course's choices queue on it."""
    list(ChoiceGroup.objects.select_for_update().filter(pk=group_id).values_list("pk", flat=True))


def _saved(write, conflict) -> None:
    """Runs ``write`` in a savepoint; a uniqueness lost to another writer anyway (the database's last net)
    becomes the 409 ``conflict`` raises, never a raw error."""
    try:
        with atomic():
            write()
    except IntegrityError:
        conflict()
        raise


def _option_out(option_id: UUID) -> dict:
    option = ChoiceOption.objects.select_related("product__tax_category", "group__combo").get(pk=option_id)
    return option_row(option, takeaway_targets())


def _group_out(group_id: UUID) -> dict:
    group = ChoiceGroup.objects.select_related("combo").prefetch_related("options__product__tax_category").get(pk=group_id)
    return group_row(group, takeaway_targets())


def _reordered(rows, wanted: list[UUID]) -> None:
    """Each row of ``rows`` to its place in ``wanted``, which must list every one of them, once."""
    current = {row.id: row for row in rows}
    if set(current) != set(wanted) or len(current) != len(wanted):
        raise Conflict(str(REORDER_MISMATCH), code="combo.reorder_mismatch")
    for position, row_id in enumerate(wanted):
        row = current[row_id]
        if row.sort_order != position:
            row.sort_order = position
            row.save(update_fields=["sort_order", "updated_at"])


# --- Menus (COMBO-F02, F03, F04) -------------------------------------------------------------------


@operation(
    "combo.combo.create",
    kind="command",
    permission="combo.manage",
    input=ComboIn,
    output=ComboDetailOut,
    expose_api=True,
    ai={
        "description": "Create a menu or combo at a closed price («menu of the day at 13.50 eaten in, VAT "
        "restaurant.food»). Eaten in needs its tax category; to take away it is split per dish. Then add its "
        "courses and choices.",
        "risk": "normal",
    },
)
def create_combo(ctx: OperationContext, data: ComboIn) -> dict:
    category = _tax_category(data.tax_category_key) if data.tax_category_key else None
    _needs_tax(data.supply_kind, category)
    combo = Combo.objects.create(
        **data.model_dump(exclude={"tax_category_key"}),
        tax_category=category,
        created_by=_actor(ctx),
        updated_by=_actor(ctx),
    )
    _combo_event(ctx, events.COMBO_CREATED, combo)
    return load_detail(combo.id, ctx.scope)


@operation(
    "combo.combo.update",
    kind="command",
    permission="combo.manage",
    input=ComboPatchIn,
    output=ComboDetailOut,
    expose_api=True,
    ai={
        "description": "Change a menu: name, kitchen name, closed price, how it is sold, tax category, order, or "
        "put it on sale / withdraw it from the till. Only the fields sent change. Changing how it is sold or its "
        "tax category changes how it is billed: confirm it with the person.",
        # Per operation, not per field: it may change how the menu is billed (supply_kind, tax_category_key).
        "risk": "high",
    },
)
def update_combo(ctx: OperationContext, data: ComboPatchIn) -> dict:
    combo = find_combo(data.id, data.combo, lock=True)
    sent = data.model_fields_set - {"id", "combo"}
    changed: list[str] = []
    for field in (
        "name",
        "kitchen_name",
        "price",
        "supply_kind",
        "sort_order",
        "is_active",
    ):
        value = getattr(data, field)
        if field in sent and value is not None and getattr(combo, field) != value:
            setattr(combo, field, value)
            changed.append(field)
    if "tax_category_key" in sent:
        category = (
            _tax_category(data.tax_category_key) if data.tax_category_key else None
        )
        if category != combo.tax_category:
            combo.tax_category = category
            changed.append("tax_category")
    _needs_tax(combo.supply_kind, combo.tax_category)
    if changed:
        combo.updated_by = _actor(ctx)
        combo.save(update_fields=[*changed, "updated_by", "updated_at"])
        _combo_event(ctx, events.COMBO_UPDATED, combo)
    return load_detail(combo.id, ctx.scope)


@operation(
    "combo.combo.delete",
    kind="command",
    permission="combo.manage",
    input=ComboRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Withdraw a menu for good, with its courses and choices. Tickets already issued keep "
        "their copy. To stop selling it for a while, set it off sale instead.",
        "risk": "high",
    },
)
def delete_combo(ctx: OperationContext, data: ComboRefIn) -> dict:
    """COMBO-F04: its photo of its own goes with it (COMBO-F14), once this is saved."""
    combo = find_combo(data.id, data.combo, lock=True)
    # A choice being added to one of its courses commits first: the cascade then sees it.
    list(combo.groups.select_for_update().values_list("pk", flat=True))
    _combo_event(ctx, events.COMBO_DELETED, combo)
    combo_id, photo = combo.id, combo.image
    combo.delete()
    images.let_go(ctx, photo)
    return {"id": combo_id}


# --- The menu's image (COMBO-F14; round 2026-10-30, base.images) -------------------------------------

#: Where a menu's own photos are kept under its hub's prefix: the folder ``members_media`` serves (apps.py).
PHOTOS = "combo/combos/"


@operation(
    "combo.combo.set_image",
    kind="command",
    permission="combo.manage",
    input=ComboImageIn,
    output=ComboDetailOut,
    expose_api=True,
    ai={
        "description": "Set the image («foto») a menu shows on the till («ponle foto al menú del día»), named by its id "
        "or its name: an image of ERPlora's shared library by its reference (catalog:<folder>/<name>, from combo.combo.suggest_image or "
        "base.catalog_image.search), or empty to show none (its initials).",
        "risk": "normal",
    },
)
def set_image(ctx: OperationContext, data: ComboImageIn) -> dict:
    """COMBO-F14: an image of the library or none; anything else (a photo of its own too, which only its upload
    writes) is refused before anything changes. The photo of its own it let go is deleted once this is saved."""
    combo = find_combo(data.id, data.combo, lock=True)
    images.check(ctx, data.image)
    _change_image(ctx, combo, data.image)
    return load_detail(combo.id, ctx.scope)


@operation(
    "combo.combo.upload_image",
    kind="command",
    permission="combo.manage",
    input=ComboImageUploadIn,
    output=ComboDetailOut,
    expose_api=True,
    ai={
        "description": "Not an assistant tool (it takes the photo the person picks in the menu's form): keeps a "
        "photo of the menu, a JPG, PNG or WebP of 2 MB at most, as its image.",
        "risk": "normal",
    },
)
def upload_image(ctx: OperationContext, data: ComboImageUploadIn) -> dict:
    """COMBO-F14: the photo becomes a 512 × 512 WebP of its own (``base.images``), within the plan's space, and takes
    the place of the one the menu had, which is deleted once this is saved."""
    webp = images.to_webp(images.decode(data.data_base64, language=ctx.language), language=ctx.language)
    combo = find_combo(data.id, data.combo, lock=True)
    _change_image(ctx, combo, images.keep_photo(ctx, PHOTOS, webp))
    return load_detail(combo.id, ctx.scope)


def _change_image(ctx: OperationContext, combo: Combo, image: str) -> None:
    """Show ``image`` on ``combo`` (no change, no event); the photo of its own it let go is deleted once saved."""
    if combo.image == image:
        return
    previous = combo.image
    combo.image = image
    combo.updated_by = _actor(ctx)
    combo.save(update_fields=["image", "updated_by", "updated_at"])
    _combo_event(ctx, events.COMBO_UPDATED, combo)
    images.let_go(ctx, previous)


# --- Courses (COMBO-F05) ---------------------------------------------------------------------------


def _name_free(combo_id: UUID, name: str, exclude: UUID | None = None) -> None:
    taken = ChoiceGroup.objects.filter(combo_id=combo_id, name__iexact=name).exclude(
        pk=exclude
    )
    if taken.exists():
        message = str(GROUP_EXISTS) % {"name": name}
        raise Conflict(message, code="combo.group_exists", fields={"name": message})


@operation(
    "combo.group.create",
    kind="command",
    permission="combo.manage",
    input=GroupIn,
    output=GroupOut,
    expose_api=True,
    ai={
        "description": "Add a course to a menu («add Starters to the menu of the day, pick 1»): it goes last. "
        "min_choices 1 or more makes it compulsory; max_choices 0 is no limit.",
        "risk": "normal",
    },
)
def create_group(ctx: OperationContext, data: GroupIn) -> dict:
    combo = find_combo(data.combo_id, data.combo, lock=True)
    if combo.groups.count() >= MAX_GROUPS:
        raise Conflict(
            str(TOO_MANY_GROUPS) % {"max": MAX_GROUPS}, code="combo.too_many_groups"
        )
    _name_free(combo.id, data.name)
    group = ChoiceGroup(
        combo=combo,
        name=data.name,
        min_choices=data.min_choices,
        max_choices=data.max_choices,
        allow_repeat=data.allow_repeat,
        sort_order=_next_order(combo.groups),
    )
    _saved(group.save, lambda: _name_free(combo.id, data.name))
    _group_event(ctx, events.GROUP_CREATED, group)
    return _group_out(group.id)


@operation(
    "combo.group.update",
    kind="command",
    permission="combo.manage",
    input=GroupPatchIn,
    output=GroupOut,
    expose_api=True,
    ai={
        "description": "Change a course: its name, minimum and maximum picks, or whether a choice may repeat. "
        "Only the fields sent change; it keeps its place.",
        "risk": "normal",
    },
)
def update_group(ctx: OperationContext, data: GroupPatchIn) -> dict:
    # The menu first, as creating a course does: a rename and a new course of the same name queue.
    _lock_combo(find_group(data.id, data.combo_id, data.combo, data.group).combo_id)
    group = find_group(data.id, data.combo_id, data.combo, data.group, lock=True)
    sent = data.model_fields_set
    changed: list[str] = []
    for field in ("name", "min_choices", "max_choices", "allow_repeat"):
        value = getattr(data, field)
        if field in sent and value is not None and getattr(group, field) != value:
            setattr(group, field, value)
            changed.append(field)
    if group.max_choices and group.max_choices < group.min_choices:
        message = str(CEILING_BELOW_FLOOR) % {
            "max": group.max_choices,
            "min": group.min_choices,
        }
        field = "max_choices" if "max_choices" in sent else "min_choices"
        raise InvalidPayload(message, code="invalid_field", fields={field: message})
    if "name" in changed:
        _name_free(group.combo_id, group.name, exclude=group.id)
    if changed:
        _saved(
            lambda: group.save(update_fields=[*changed, "updated_at"]),
            lambda: _name_free(group.combo_id, group.name, exclude=group.id),
        )
        _group_event(ctx, events.GROUP_UPDATED, group)
    return _group_out(group.id)


@operation(
    "combo.group.delete",
    kind="command",
    permission="combo.manage",
    input=GroupRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Remove a course from its menu, with its choices.",
        "risk": "high",
    },
)
def delete_group(ctx: OperationContext, data: GroupRefIn) -> dict:
    group = find_group(data.id, data.combo_id, data.combo, data.group, lock=True)
    _group_event(ctx, events.GROUP_DELETED, group)
    group_id = group.id
    group.delete()
    return {"id": group_id}


@operation(
    "combo.group.reorder",
    kind="command",
    permission="combo.manage",
    input=GroupReorderIn,
    output=ComboDetailOut,
    expose_api=True,
    ai={
        "description": "Put the courses of a menu in a new order (the order the till asks them in): give every "
        "course id, in order.",
        "risk": "normal",
    },
)
def reorder_groups(ctx: OperationContext, data: GroupReorderIn) -> dict:
    combo = find_combo(data.id, data.combo, lock=True)
    _reordered(combo.groups.select_for_update(), data.group_ids)
    record_event(ctx, events.GROUP_REORDERED, {"combo_id": str(combo.id)})
    return load_detail(combo.id, ctx.scope)


# --- Choices (COMBO-F06, F12) --------------------------------------------------------------------


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
    permission="combo.manage",
    input=OptionIn,
    output=OptionOut,
    expose_api=True,
    ai={
        "description": "Offer a product as a choice of a course («put the lentils in Starters of the menu of the "
        "day», «hake in Mains with 2 euros supplement»): it goes last. The supplement adds to the closed price.",
        "risk": "normal",
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
    permission="combo.manage",
    input=OptionBulkIn,
    output=GroupOut,
    expose_api=True,
    ai={
        "description": "Offer several products at once in a course, without supplement, in the order given; all "
        "or nothing.",
        "risk": "normal",
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
    permission="combo.manage",
    input=OptionPatchIn,
    output=OptionOut,
    expose_api=True,
    ai={
        "description": "Change a choice: its supplement, mark it sold out («no flan today in the menu of the "
        "day»: is_available false) or back on offer, or replace its product. It keeps its place.",
        "risk": "normal",
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
    permission="combo.manage",
    input=OptionRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={"description": "Remove a choice from its course.", "risk": "high"},
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
    permission="combo.manage",
    input=OptionReorderIn,
    output=GroupOut,
    expose_api=True,
    ai={
        "description": "Put the choices of a course in a new order (the order the till shows them in): give every "
        "choice id, in order.",
        "risk": "normal",
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
