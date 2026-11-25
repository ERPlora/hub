"""Writes of the prices of a list: add one for a product or a service, change it and remove it."""

from decimal import Decimal
from uuid import UUID

from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import atomic, operation
from live.outbox import record_event

from apps.inventory.models import fits_unit, increment_of
from apps.inventory.queries.reads import find_product
from apps.pricing import events
from apps.pricing.models import PriceItem
from apps.pricing.queries.other_apps import call_service
from apps.pricing.queries.reads import ITEM_NOT_FOUND, find_list, live_items
from apps.pricing.queries.rows import item_row, load_item, removed_row
from apps.pricing.schemas.prices import PriceItemIn, PriceItemOut, PriceItemPatchIn, PriceItemRefIn
from apps.pricing.schemas.price_removed import PriceRemovedOut
from apps.pricing.services.writes import _actor, _constraint, _held_product

LIST_NOT_FOR_PRICES = _("That price list is not available: it does not exist in this business or it is deactivated.")
ITEM_EXISTS = _("That article already has a price in this list from that quantity.")
QUANTITY_OFF_STEP = _("This quantity does not fit the article's unit: use a multiple of %(step)s.")

ITEM_UNIQUE = {"pricing_price_item_product_unique", "pricing_price_item_service_unique"}
THOUSANDTHS = Decimal("0.001")


def _quantity(value: Decimal) -> str:
    """A quantity in an event: always three decimals, so its consumers read it the same way."""
    return str(value.quantize(THOUSANDTHS))


def _check_step(quantity: Decimal, unit: str) -> None:
    """A from quantity in the article's unit and on its step (a service: whole units)."""
    if not fits_unit(quantity, unit):
        message = str(QUANTITY_OFF_STEP) % {"step": f"{increment_of(unit).normalize():f}"}
        raise InvalidPayload(message, code="invalid_field", fields={"min_quantity": message})


def _save_item(item: PriceItem) -> None:
    try:
        with atomic():
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="pricing.manage",
    input=PriceItemIn,
    output=PriceItemOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "add the toast at 2 € to Hospitality",
                "add the croissant to the partners' one",
                "add the orange juice at 1.80 for distributors from ten on",
            ),
            "es": (
                "mete la tostada a 2 € en Hostelería",
                "añade el croissant a la de los socios",
                "agrega el zumo de naranja a 1,80 para distribuidores desde diez",
            ),
        },
        "description": "Put the price a price list (by its code or name) charges for a product (by its SKU or name) "
        "or a service (by its name), in cents, from a minimum quantity on (1 by default). Repeat the product with "
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
        item.product = _held_product(data.product_id, data.product)
        _check_step(data.min_quantity, item.product.unit)
    else:
        service = call_service(ctx, data.service_id, data.service)
        _check_step(data.min_quantity, "ud")
        item.service_id, item.service_name = service.id, service.name
    _save_item(item)
    record_event(
        ctx, events.PRICE_ITEM_ADDED,
        {
            "id": str(item.id),
            "price_list_id": str(price_list.id),
            "product_id": str(item.product_id) if item.product_id else None,
            "service_id": str(item.service_id) if item.service_id else None,
            "min_quantity": _quantity(item.min_quantity),
            "price": item.price,
            "currency": price_list.currency,
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="pricing.manage",
    input=PriceItemPatchIn,
    output=PriceItemOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "raise the muffin to 1.40 for partners",
                "change the beer in Hospitality, it is 2.20 now",
                "change the muffin so it applies from five on",
            ),
            "es": (
                "sube la magdalena a 1,40 para los socios",
                "cambia la caña de Hostelería, que ahora vale 2,20",
                "cambia la magdalena para que valga desde cinco",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="pricing.manage",
    input=PriceItemRefIn,
    output=PriceRemovedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "remove the juice from the distributors' one",
                "delete the sandwich in the hotels' one",
                "partners should pay for the sandwich like everybody else",
            ),
            "es": (
                "quita el zumo de la de distribuidores",
                "borra lo del bocadillo en la de hoteles",
                "que los socios paguen el bocadillo como todo el mundo",
            ),
        },
        "description": "Remove a price from a price list: by its id, or by the list (code or name), the product "
        "(SKU or name) or the service (name) and its from quantity (1 if not said). It answers what the article costs on that list now, read after removing it: "
        "price_now in cents, from the list price_now_list or, when that is null, the catalog's (price_now null: not known). Tell that price, never the price just removed.",
        "risk": "high",
    },
)
def remove_price_item(ctx: OperationContext, data: PriceItemRefIn) -> dict:
    item = _named_item(ctx, data)
    item_id, list_id = item.id, item.price_list_id
    item.delete()
    record_event(ctx, events.PRICE_ITEM_REMOVED, {"id": str(item_id), "price_list_id": str(list_id)})
    return removed_row(ctx, item, item_id)
