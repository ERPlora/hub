"""A menu's writes: create it, change it, withdraw it, make it again from a separate copy (COMBO-F02 to F04, F15), and
the image it shows (COMBO-F14)."""

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import INTERNAL, operation
from live.outbox import record_event

from apps.combo import events
from apps.combo.models import ACTOR_MAX_LENGTH, Combo
from apps.combo.queries.reads import find_combo
from apps.combo.queries.rows import load_detail
from apps.combo.schemas.fields import DeletedOut
from apps.combo.schemas.images import ComboImageIn, ComboImageUploadIn
from apps.combo.schemas.menus import ComboDetailOut, ComboIn, ComboPatchIn, ComboRecoverIn
from apps.combo.schemas.references import ComboRefIn
from apps.combo.services.writes import SYSTEM
from apps.inventory.queries.reads import held
from apps.tax.models import TaxCategory
from base import images

TAX_REQUIRED = _(
    "A menu eaten in needs its own VAT category: without it, it cannot be billed."
)
# Its own context: it goes under the menu form's «Tipo de IVA», and Sale says the same English with «categoría fiscal».
TAX_UNKNOWN = pgettext_lazy("combo", "That tax category does not exist in Taxes.")


def _actor(ctx: OperationContext) -> str:
    return str(ctx.actor)[:ACTOR_MAX_LENGTH]


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


@operation(
    "combo.combo.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="combo.manage",
    input=ComboIn,
    output=ComboDetailOut,
    expose_api=True,
    ai={
        "description": "Create a menu or combo at a closed price («menu of the day at 13.50 eaten in, VAT "
        "restaurant.food»). Eaten in needs its tax category; to take away it is split per dish. Then add its "
        "courses and choices.",
        "risk": "normal",
        "asks": {
            "en": (
                "create a vegan menu at 12.50 to eat in",
                "set up a new takeaway combo at 9",
            ),
            "es": (
                "crea un menú vegano a 12,50 para comer aquí",
                "da de alta un combo para llevar a 9",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="combo.manage",
    input=ComboPatchIn,
    output=ComboDetailOut,
    expose_api=True,
    ai={
        "description": "Change a menu: name, kitchen name, closed price, how it is sold, tax category or order. Only "
        "the fields sent change. Changing how it is sold or its tax category changes how it is billed. To put it on "
        "sale or take it off the till and change nothing else, combo.combo.set_active.",
        "risk": "high",
        "check": "combo.combo.get",
        "asks": {
            "en": (
                "bring the vegan menu down to 11.90",
                "rename the vegan menu to Green menu",
            ),
            "es": (
                "rebaja el menú vegano a 11,90",
                "cambia el nombre del menú vegano a Menú verde",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="combo.manage",
    input=ComboRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Withdraw a menu for good, with its courses and choices. Tickets already issued keep "
        "their copy. To stop selling it for a while, set it off sale instead.",
        "risk": "high",
        "check": "combo.combo.get",
        "asks": {
            "en": (
                "delete the summer menu for good",
                "get rid of the Christmas menu, we won't sell it again",
            ),
            "es": (
                "retira para siempre el menú de verano",
                "elimina el menú de Navidad, ya no lo vamos a vender",
            ),
        },
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


# Not an assistant tool and no route: its one door is the recovery from a separate copy (BASE-F114, COMBO-F15), for a
# menu the business no longer has at all (withdrawing one deletes it with its courses and choices).
@operation(
    "combo.combo.recover",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=SYSTEM,
    input=ComboRecoverIn,
    output=ComboDetailOut,
    ai=INTERNAL,
)
def recover_combo(ctx: OperationContext, data: ComboRecoverIn) -> dict:
    """A menu of a separate copy made again by ``combo.combo.create``, with the image of the library it showed there
    set as ``combo.combo.set_image`` sets it (a photo of its own does not come back: ``base.images.from_copy``). It
    keeps which of the copy's it is made again for (``stands_for``), so its courses come back to it."""
    made = create_combo(ctx, ComboIn.model_validate(data.model_dump(include=set(ComboIn.model_fields))))
    Combo.objects.filter(pk=made.id).update(stands_for=data.stands_for)
    if image := images.from_copy(ctx, data.image):
        _change_image(ctx, find_combo(made.id, None), image)
    return load_detail(made.id, ctx.scope)


# --- The menu's image (COMBO-F14, base.images) -------------------------------------------------------

#: Where a menu's own photos are kept under its hub's prefix: the folder ``public_media`` serves (apps.py).
PHOTOS = "combo/combos/"


@operation(
    "combo.combo.set_image",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="combo.manage",
    input=ComboImageIn,
    output=ComboDetailOut,
    expose_api=True,
    ai={
        "description": "Set the image («foto») a menu shows on the till («ponle foto al menú del día»), named by its id "
        "or its name: an image of ERPlora's shared library by its reference (catalog:<folder>/<name>, from combo.combo.suggest_image or "
        "base.catalog_image.search), or empty to show none (its initials).",
        "risk": "normal",
        "check": "combo.combo.get",
        "asks": {
            "en": (
                "put a photo on the tasting menu",
                "use the paella drawing as the summer menu's picture",
            ),
            "es": (
                "ponle foto al menú degustación",
                "usa el dibujo de la paella como imagen del menú de verano",
            ),
        },
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
