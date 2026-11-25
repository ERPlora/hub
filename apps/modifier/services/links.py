"""The writes on what a group applies to: a product or a category of Inventory (MODIFIER-F05, F09)."""

from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.inventory import queries as inventory_queries
from apps.inventory.models import Product
from apps.inventory.queries.reads import find_category, find_product, held
from apps.modifier import events
from apps.modifier.models import ModifierLink
from apps.modifier.queries.reads import LINK_NOT_FOUND, find_group, load_link
from apps.modifier.schemas.fields import DeletedOut
from apps.modifier.schemas.links import DropIn, DropOut, LinkIn, LinkOut, LinkRefIn
from apps.modifier.services.writes import LINK_EXISTS, SYSTEM, _actor, _save


@operation(
    "modifier.link.attach",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="modifier.manage",
    input=LinkIn,
    output=LinkOut,
    ai={
        "description": "Apply a modifier group (named by its id or name) to a product (by its id, SKU or name) or to "
        "a category (by its id or name), so that the till asks for it when that is sold.",
        "risk": "normal",
        "asks": {
            "en": (
                "make the till ask for doneness with the sirloin",
                "apply the Sauces group to the whole Pizzas category",
            ),
            "es": (
                "que el TPV pregunte siempre la salsa al vender una pizza",
                "aplica el grupo Salsas a toda la familia Pizzas",
            ),
        },
    },
)
def attach_link(ctx: OperationContext, data: LinkIn) -> dict:
    # The group's row is locked: a deletion at the same time waits, or is waited for and then said.
    group = find_group(data.group_id, data.group, lock=True)
    product, category = _target(data, hold=True)
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="modifier.manage",
    input=LinkRefIn,
    output=DeletedOut,
    ai={
        "description": "Stop applying a modifier group to a product or a category: by the link's id, or by the group "
        "and the product (id, SKU or name) or category (id or name). It can be applied again later.",
        "risk": "normal",
        "check": "modifier.link.get",
        "asks": {
            "en": (
                "stop asking for sauces with the pizza",
                "unlink the Extras group from the sirloin",
            ),
            "es": (
                "deja de preguntar las salsas con la pizza",
                "suelta el grupo Extras del entrecot pero consérvalo para los demás productos",
            ),
        },
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


def _target(data, *, hold: bool = False):
    """The live product or category a link names: exactly one of them, the other ``None``. ``hold`` keeps it
    for the link written next (see ``held``): one being deleted meanwhile is not found, as one deleted before."""
    if data.product_id is not None or data.product is not None:
        product = find_product(data.product_id, data.product)
        return (_held_product(product) if hold else product), None
    return None, find_category(data.category_id, data.category, hold=hold)


def _held_product(product: Product) -> Product:
    """``product`` read again with its row held: Inventory's ``find_product`` finds it by its SKU or name, and
    has no ``hold`` of its own."""
    live = held(Product.objects.filter(pk=product.pk, is_deleted=False)[:1])
    if not live:
        # Inventory's own text (and its translation), as for a product deleted before.
        raise NotFound(str(inventory_queries.reads.PRODUCT_NOT_FOUND))
    return live[0]


def _drop(ctx: OperationContext, links) -> int:
    dropped = 0
    for link in links.select_for_update().order_by("id"):
        payload = _link_payload(link)
        link.delete()
        record_event(ctx, events.LINK_DETACHED, payload)
        dropped += 1
    return dropped


def _link_payload(link: ModifierLink) -> dict:
    return {
        "id": str(link.id),
        "group_id": str(link.group_id),
        "product_id": str(link.product_id) if link.product_id else None,
        "category_id": str(link.category_id) if link.category_id else None,
    }
