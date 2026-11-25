"""The services of the catalog (SERVICE-F01 to F06): created one by one or several at once, changed, archived and
restored, each holding the tax category and the category it names until it commits.
"""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.service import events
from apps.service.models import Category, Service, ServiceSettings
from apps.service.queries.catalog import find_service, load_service
from apps.service.queries.categories import find_category
from apps.service.queries.reads import held_rows
from apps.service.queries.settings import current_settings
from apps.service.schemas.catalog import (
    PRICE_RANGE_UPSIDE_DOWN,
    ServiceBulkIn,
    ServiceIn,
    ServiceOut,
    ServicePatchIn,
    ServicesOut,
)
from apps.service.schemas.fields import ServiceRefIn
from apps.service.services.writes import TAX_UNKNOWN, _actor, _apply, _changes, _refuse, _tax_category
from apps.tax.queries.categories import held_categories

TAX_REQUIRED = _("Pick a tax category: without one the service cannot be charged.")

CATEGORY_UNAVAILABLE = _(
    "That category is not available: it does not exist in this business or it has been deleted."
)

BULK_INVALID = _("Some services cannot be created: nothing was created.")

# The plain fields of a service an edit may change (the others need a lookup or may be emptied).
SERVICE_PLAIN = (
    "name",
    "pricing_type",
    "price",
    "cost",
    "duration_minutes",
    "buffer_before",
    "buffer_after",
    "max_capacity",
    "description",
    "short_description",
    "is_bookable",
    "requires_confirmation",
    "allow_online_booking",
    "sort_order",
    "is_featured",
    "sku",
    "barcode",
    "notes",
)


def _service_category(category_id, said, field: str) -> Category | None:
    if category_id is None and said is None:
        return None
    try:
        return find_category(category_id, said)
    except NotFound as exc:
        raise _refuse(
            CATEGORY_UNAVAILABLE, "service.category_unavailable", field
        ) from exc


def _hold_named(lines: list[tuple]) -> list[InvalidPayload]:
    """Holds the tax category and the category each line names (``(tax category, category, what it said, field
    prefix)``) until the command commits: each kind in one read, in key and id order, so deleting one, or the
    «Delete» of a category that takes them all, waits for this write and never in a circle. A line whose own went
    while it was read is refused as one deleted before: the refusals, under each line's field."""
    taxes = held_categories(tax.key for tax, _, _, _ in lines if tax is not None)
    named = [category.pk for _, category, _, _ in lines if category is not None]
    categories = {row.pk for row in held_rows(Category.objects.filter(pk__in=named, is_deleted=False))}
    refusals = []
    for tax, category, said, prefix in lines:
        if tax is not None and tax.key not in taxes:
            message, code = (
                (TAX_UNKNOWN, "service.tax_category_unknown")
                if said.tax_category_key
                else (TAX_REQUIRED, "service.tax_category_required")
            )
            refusals.append(_refuse(message, code, f"{prefix}tax_category_key"))
        elif category is not None and category.pk not in categories:
            field = "category_id" if said.category_id else "category"
            refusals.append(
                _refuse(CATEGORY_UNAVAILABLE, "service.category_unavailable", f"{prefix}{field}")
            )
    return refusals


def _new_service(
    ctx: OperationContext, data: ServiceIn, settings: ServiceSettings, prefix: str = ""
) -> Service:
    """A service built from ``data``, with what it does not say taken from ``settings`` (not saved)."""
    if data.tax_category_key:
        tax = _tax_category(data.tax_category_key, f"{prefix}tax_category_key")
    else:
        tax = settings.default_tax_category
        if tax is None or not tax.is_active:
            raise _refuse(
                TAX_REQUIRED,
                "service.tax_category_required",
                f"{prefix}tax_category_key",
            )
    field = "category_id" if data.category_id else "category"
    category = _service_category(data.category_id, data.category, f"{prefix}{field}")
    plain = {
        name: getattr(data, name)
        for name in SERVICE_PLAIN
        if getattr(data, name) is not None
    }
    defaults = {
        "duration_minutes": settings.default_duration,
        "buffer_before": settings.default_buffer_time,
        "buffer_after": settings.default_buffer_time,
        "allow_online_booking": settings.allow_online_booking,
    }
    return Service(
        **(defaults | plain),
        min_price=data.min_price,
        max_price=data.max_price,
        category=category,
        tax_category=tax,
        created_by=_actor(ctx),
        updated_by=_actor(ctx),
    )


def _announce_created(ctx: OperationContext, service: Service) -> None:
    record_event(
        ctx, events.SERVICE_CREATED, {"id": str(service.id), "name": service.name}
    )


@operation(
    "service.service.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.add_service",
    input=ServiceIn,
    output=ServiceOut,
    expose_api=True,
    ai={
        "description": "Create a service of the catalog with its price, duration and tax category (the settings' "
        "default when not said); what it does not say takes the settings.",
        "risk": "normal",
        "asks": {
            "en": ("add a new service: men's haircut, 30 minutes, 15 euros", "create a keratin treatment at 90 euros"),
            "es": (
                "da de alta el servicio de corte de caballero a 15 €",
                "crea un servicio de alisado de keratina de 90 minutos",
            ),
        },
    },
)
def create_service(ctx: OperationContext, data: ServiceIn) -> dict:
    service = _new_service(ctx, data, current_settings())
    if refusals := _hold_named([(service.tax_category, service.category, data, "")]):
        raise refusals[0]
    service.save()
    _announce_created(ctx, service)
    return load_service(service.id, ctx.scope)


@operation(
    "service.service.bulk_create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.change_service",
    input=ServiceBulkIn,
    output=ServicesOut,
    expose_api=True,
    ai={
        "description": "Create up to 500 services at once, all of them or none: a line that cannot be created says "
        "why under its own field and nothing is created.",
        "risk": "high",
        "asks": {
            "en": (
                "add these three services at once: cut, colour and blow-dry",
                "create the whole list of beauty services in one go",
            ),
            "es": ("da de alta de golpe corte, tinte y peinado", "crea de una vez todos estos servicios de estética"),
        },
    },
)
def bulk_create_services(ctx: OperationContext, data: ServiceBulkIn) -> dict:
    settings = current_settings()
    built, named, problems = [], [], {}
    for index, line in enumerate(data.services):
        prefix = f"services.{index}."
        try:
            service = _new_service(ctx, line, settings, prefix=prefix)
        except InvalidPayload as exc:
            problems.update(exc.fields or {})
        else:
            built.append(service)
            named.append((service.tax_category, service.category, line, prefix))
    if not problems:
        for refusal in _hold_named(named):
            problems.update(refusal.fields or {})
    if problems:
        raise InvalidPayload(
            str(BULK_INVALID), code="service.bulk_invalid", fields=problems
        )
    for service in built:
        service.save()
        _announce_created(ctx, service)
    return {"created": len(built), "ids": [service.id for service in built]}


@operation(
    "service.service.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.change_service",
    input=ServicePatchIn,
    output=ServiceOut,
    expose_api=True,
    ai={
        "description": "Change a service (named by its id or its name): only the fields sent change; null empties "
        "its category or its minimum and maximum prices. Its tax category can be changed, never emptied.",
        "risk": "normal",
        "asks": {
            "en": ("raise the colour service to 45 euros", "the manicure now lasts 50 minutes"),
            "es": ("sube el tinte a 45 €", "cambia la duración de la manicura a 50 minutos"),
        },
    },
)
def update_service(ctx: OperationContext, data: ServicePatchIn) -> dict:
    service_id = find_service(data.id, data.service).pk
    sent = data.model_fields_set
    values = {
        name: getattr(data, name)
        for name in SERVICE_PLAIN
        if name in sent and getattr(data, name) is not None
    }
    values |= {
        name: getattr(data, name) for name in ("min_price", "max_price") if name in sent
    }
    if data.tax_category_key:
        values["tax_category"] = _tax_category(
            data.tax_category_key, "tax_category_key"
        )
    if sent & {"category_id", "category"}:
        field = "category_id" if data.category_id else "category"
        values["category"] = _service_category(data.category_id, data.category, field)
    # What it names is held before its own row, in the order the «Delete» of a category takes them (every
    # category, then their services): the other way round, each waited for the other.
    if refusals := _hold_named([(values.get("tax_category"), values.get("category"), data, "")]):
        raise refusals[0]
    service = find_service(service_id, None, lock=True)
    low, high = (
        values.get("min_price", service.min_price),
        values.get("max_price", service.max_price),
    )
    if low is not None and high is not None and low > high:
        raise InvalidPayload(str(PRICE_RANGE_UPSIDE_DOWN), code="service.price_range")
    changes = _changes(service, values)
    if changes:
        _apply(service, changes, ctx)
        service.save()
        record_event(ctx, events.SERVICE_UPDATED, {"id": str(service.id)})
    return load_service(service.id, ctx.scope)


@operation(
    "service.service.archive",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.delete_service",
    input=ServiceRefIn,
    output=ServiceOut,
    expose_api=True,
    ai={
        "description": "Archive a service: it is no longer offered nor bookable; its history, the appointments "
        "already booked and the vouchers that include it are kept. Archiving it again changes nothing.",
        "risk": "high",
        "asks": {
            "en": ("we no longer do perms, archive them", "stop offering the beard trim"),
            "es": ("ya no hacemos permanentes, archívalo", "deja de ofrecer el arreglo de barba"),
        },
    },
)
def archive_service(ctx: OperationContext, data: ServiceRefIn) -> dict:
    service = find_service(data.id, data.service, lock=True)
    if service.is_active:
        _apply(service, {"is_active": False, "archived_at": timezone.now()}, ctx)
        service.save()
        record_event(ctx, events.SERVICE_ARCHIVED, {"id": str(service.id)})
    return load_service(service.id, ctx.scope)


@operation(
    "service.service.restore",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.change_service",
    input=ServiceRefIn,
    output=ServiceOut,
    expose_api=True,
    ai={
        "description": "Restore an archived service (named by its id or its name): it is offered and bookable again.",
        "risk": "normal",
        "asks": {
            "en": ("bring back the perm service", "restore the archived beard trim"),
            "es": (
                "recupera el masaje relajante para venderlo otra vez",
                "restaura el servicio de mechas que archivamos",
            ),
        },
    },
)
def restore_service(ctx: OperationContext, data: ServiceRefIn) -> dict:
    service = find_service(data.id, data.service, lock=True, archived=True)
    if not service.is_active:
        _apply(service, {"is_active": True, "archived_at": None}, ctx)
        service.save()
        record_event(ctx, events.SERVICE_RESTORED, {"id": str(service.id)})
    return load_service(service.id, ctx.scope)
