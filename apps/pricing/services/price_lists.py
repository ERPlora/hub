"""Writes of the price lists: create and edit one, make it the general list, deactivate and activate it."""

from typing import Any

from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import atomic, operation
from live.outbox import record_event

from apps.pricing import events
from apps.pricing.models import PriceList
from apps.pricing.queries.reads import find_list
from apps.pricing.queries.rows import list_row
from apps.pricing.schemas import (
    DEFAULT_CURRENCY,
    DEFAULT_HAS_GROUP,
    RANGE_BACKWARDS,
    PriceListDefaultIn,
    PriceListIn,
    PriceListOut,
    PriceListPatchIn,
    PriceListRefIn,
)
from apps.pricing.services.writes import _actor, _constraint, _group_id
from base import operations as platform

DUPLICATE_LIST_CODE = _("A price list with that code already exists. Pick a different code.")
LIST_INACTIVE = _("A deactivated price list cannot be the general one.")
DEFAULT_BUSY = _("Someone else is changing the general price list right now. Try again in a moment.")
LIST_IS_DEFAULT = _(
    "This is the general price list: make another one general or take its mark off before deactivating it."
)
LIST_ALREADY_INACTIVE = _("That price list is already deactivated.")
LIST_ALREADY_ACTIVE = _("That price list is already active.")

LIST_CODE_UNIQUE = "pricing_price_list_code_unique"
ONE_DEFAULT = "pricing_price_list_one_default"
#: Tries of a general list against another choice at the same time (the last one stays).
DEFAULT_TRIES = 3


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
            with atomic():
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="pricing.manage",
    input=PriceListIn,
    output=PriceListOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "create a separate one for the partners' club",
                "start a new one for hotels with code HOT-1",
                "create the club's own one, code CLUB-1",
            ),
            "es": (
                "crea una aparte para el club de socios",
                "da de alta una nueva para hoteles con código HOT-1",
                "crea la del club con código CLUB-1",
            ),
        },
        "description": "Create a price list: its code (unique, e.g. WHOLESALE) and name, and if wanted its currency, "
        "whether its prices carry the tax, the customer group whose members get it (by name, e.g. VIP), its first "
        "and last day, and whether it is the general list for everybody. It starts with no prices: add them with "
        "pricing.price_item.add.",
        "risk": "normal",
    },
)
def create_price_list(ctx: OperationContext, data: PriceListIn) -> dict:
    """Without a currency, the list is in the business's (its country's); the general one, only in that one."""
    business = platform.business_currency(ctx.scope)
    currency = data.currency or business
    if data.is_default and currency != business:
        message = str(DEFAULT_CURRENCY) % {"currency": business}
        raise InvalidPayload(message, code="invalid_field", fields={"is_default": message})
    actor = _actor(ctx)
    price_list = PriceList(
        code=data.code,
        name=data.name,
        currency=currency,
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="pricing.manage",
    input=PriceListPatchIn,
    output=PriceListOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "rename the summer one to Summer 2027",
                "the summer one has to last until October",
                "move the end of the summer one to October",
            ),
            "es": (
                "renombra la de verano como Verano 2027",
                "que la de verano dure hasta octubre",
                "cambia las fechas de la de verano",
            ),
        },
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
    if price_list.is_default and "currency" in changes:
        business = platform.business_currency(ctx.scope)
        if changes["currency"] != business:
            message = str(DEFAULT_CURRENCY) % {"currency": business}
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="pricing.manage",
    input=PriceListDefaultIn,
    output=PriceListOut,
    ai={
        "asks": {
            "en": (
                "make Distributors the general one",
                "the normal one for everybody has to be Distributors",
                "Distributors should stop being the general one",
            ),
            "es": (
                "haz que Distribuidores sea la general",
                "la normal para todo el mundo tiene que ser la de Distribuidores",
                "que Distribuidores deje de ser la general",
            ),
        },
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
        business = platform.business_currency(ctx.scope)
        if price_list.currency != business:
            raise Conflict(str(DEFAULT_CURRENCY) % {"currency": business}, code="pricing.default_currency")
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="pricing.manage",
    input=PriceListRefIn,
    output=PriceListOut,
    ai={
        "asks": {
            "en": (
                "freeze the winter one and keep what it has for later",
                "switch off the winter one during January",
                "stop applying the summer one for now",
            ),
            "es": (
                "congela la de invierno y guarda lo suyo para más adelante",
                "apaga la de invierno durante enero",
                "deja de aplicar la de verano por ahora",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="pricing.manage",
    input=PriceListRefIn,
    output=PriceListOut,
    ai={
        "asks": {
            "en": (
                "reactivate the Christmas one for the coming holidays",
                "bring the Christmas one back for the coming sales",
                "the winter one has to apply again",
            ),
            "es": (
                "reactiva la de Navidad para las próximas fiestas",
                "que la de Navidad vuelva a valer en las ventas",
                "recupera la de invierno para este año",
            ),
        },
        "description": "Bring a deactivated price list (by its id, code or name) back, so it prices new sales again.",
        "risk": "high",
    },
)
def activate_price_list(ctx: OperationContext, data: PriceListRefIn) -> dict:
    return _switch_list(ctx, data, active=True)
