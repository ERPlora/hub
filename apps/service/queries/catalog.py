"""The catalog of services: a service by how a person names it, its rows and the reads of the catalog."""

from functools import partial
from uuid import UUID

from django.db.models import Case, CharField, Q, Value, When
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope
from live.operations import operation

from apps.service.models import Service
from apps.service.queries.reads import _bounds, _page, _resolve
from apps.service.schemas import (
    CatalogStatusOut,
    NoIn,
    ServiceForSaleIn,
    ServiceImageSuggestIn,
    ServiceImageSuggestOut,
    ServiceListIn,
    ServiceOut,
    ServicePage,
    ServiceRefIn,
    ServiceSalePage,
)
from base import images
from base.queries.catalog_images import business_language, image_library
from base.ordering import list_order_for

SERVICE_NOT_FOUND = _("That service does not exist in this business.")
SERVICE_AMBIGUOUS = _("“%(said)s” matches several services: %(names)s. Say which one.")

#: Offered services that cannot be charged: no tax category, or one that Taxes deactivated.
UNTAXED = Q(tax_category__isnull=True) | Q(tax_category__is_active=False)

SERVICE_ORDER = {
    "name": ("name",),
    "category_name": ("category__name",),
    "pricing_type": ("pricing_type",),
    "price": ("price",),
    "duration_minutes": ("duration_minutes",),
    "status": ("status",),
    "created_at": ("created_at",),
}


def find_service(  # noqa: PLR0913
    service_id: UUID | None,
    said: str | None,
    *,
    lock: bool = False,
    hold: bool = False,
    offered: bool = False,
    archived: bool = False,
    rows=None,
) -> Service:
    """A service by id (archived too, unless ``offered``), or by its name among the offered ones (the
    archived ones with ``archived``, to restore one by name). It comes from ``rows`` when given (e.g. with
    what its detail shows): one read, so a deletion committed meanwhile is either not seen yet or not
    found, never a row that vanished between two reads."""
    services = Service.objects.all()
    found_in = services if rows is None else rows
    return _resolve(
        found_in.filter(is_active=True) if offered else found_in,
        service_id,
        said,
        lock=lock,
        hold=hold,
        missing=SERVICE_NOT_FOUND,
        missing_code="service.service_not_found",
        ambiguous=SERVICE_AMBIGUOUS,
        ambiguous_code="service.service_ambiguous",
        named=services.filter(is_active=not archived),
    )


def _services():
    return Service.objects.select_related("category", "tax_category").annotate(
        status=Case(
            When(is_active=False, then=Value("archived")),
            When(UNTAXED, then=Value("unconfigured")),
            default=Value("active"),
            output_field=CharField(),
        )
    )


def needs_tax_setup(service: Service) -> bool:
    return service.tax_category is None or not service.tax_category.is_active


SERVICE_FIELDS = (
    "id",
    "name",
    "description",
    "short_description",
    "category_id",
    "pricing_type",
    "price",
    "min_price",
    "max_price",
    "cost",
    "duration_minutes",
    "buffer_before",
    "buffer_after",
    "max_capacity",
    "is_bookable",
    "requires_confirmation",
    "allow_online_booking",
    "sort_order",
    "is_featured",
    "sku",
    "barcode",
    "notes",
    "tax_category_id",
    "is_active",
    "archived_at",
    "created_at",
    "updated_at",
    "status",
)


def _service_row(service: Service, urls: images.Urls) -> dict:
    tax = service.tax_category
    return {
        **{field: getattr(service, field) for field in SERVICE_FIELDS},
        "category_name": service.category.name if service.category else None,
        "tax_category_key": tax.key if tax else None,
        "tax_category_name": tax.display_name if tax else None,
        "needs_tax_setup": needs_tax_setup(service),
        "image": service.image,
        "image_url": urls(service.image),
    }


def load_service(service_id: UUID, scope: Scope) -> dict:
    """A service of ``scope`` as a ``ServiceOut``; services.py returns it after a write."""
    return _service_row(_services().get(pk=service_id), images.Urls(scope))


def _sale_row(service: Service, urls: images.Urls) -> dict:
    fields = (
        "id",
        "name",
        "pricing_type",
        "price",
        "min_price",
        "max_price",
        "duration_minutes",
        "buffer_before",
        "buffer_after",
        "is_bookable",
        "allow_online_booking",
        "category_id",
        "tax_category_id",
    )
    return {
        **{field: getattr(service, field) for field in fields},
        "category_name": service.category.name if service.category else None,
        "tax_category_key": service.tax_category.key if service.tax_category else None,
        "needs_tax_setup": needs_tax_setup(service),
        "image": service.image,
        "image_url": urls(service.image),
    }


@operation(
    "service.service.list",
    kind="query",
    permission="service.view_service",
    input=ServiceListIn,
    output=ServicePage,
    expose_api=True,
    ai={
        "description": "List the services of the catalog with their category, pricing, price, duration and status "
        "(active, unconfigured = no tax category so it cannot be charged, archived). status=archived lists the "
        "archived ones.",
        "asks": {
            "en": ("what services do we offer?", "which services are archived?"),
            "es": ("¿qué servicios ofrecemos?", "enséñame los servicios archivados"),
        },
    },
)
def list_services(ctx: OperationContext, params: ServiceListIn) -> dict:
    services = _services()
    if params.status == "archived":
        services = services.filter(is_active=False)
    else:
        services = services.filter(is_active=True)
        if params.status == "unconfigured":
            services = services.filter(UNTAXED)
        elif params.status == "active":
            services = services.filter(
                tax_category__isnull=False, tax_category__is_active=True
            )
    if params.search:
        services = services.filter(
            Q(name__icontains=params.search)
            | Q(category__name__icontains=params.search)
            | Q(sku__icontains=params.search)
        )
    if params.name:
        services = services.filter(name__icontains=params.name)
    if params.category_id:
        services = services.filter(category_id=params.category_id)
    if params.category:
        services = services.filter(category__name__iexact=params.category)
    if params.pricing_type:
        services = services.filter(pricing_type=params.pricing_type)
    services = services.filter(
        **_bounds(
            price__gte=params.price_min,
            price__lte=params.price_max,
            duration_minutes__gte=params.duration_min,
            duration_minutes__lte=params.duration_max,
        )
    )
    return _page(
        services.order_by(*list_order_for(params.sort, "name", columns=SERVICE_ORDER, nulls_last=True)),
        params,
        partial(_service_row, urls=images.Urls(ctx.scope)),
    )


@operation(
    "service.service.get",
    kind="query",
    permission="service.view_service",
    input=ServiceRefIn,
    output=ServiceOut,
    expose_api=True,
    ai={
        "description": "Get one service with everything it has, named by its id or its name (an archived one by its "
        "id).",
        "asks": {
            "en": ("how much is the men's haircut and how long does it take?", "pull up the highlights service"),
            "es": ("¿cuánto cuesta y cuánto dura el tinte de raíz?", "dame los datos del servicio de manicura"),
        },
    },
)
def get_service(ctx: OperationContext, data: ServiceRefIn) -> dict:
    return _service_row(find_service(data.id, data.service, rows=_services()), images.Urls(ctx.scope))


@operation(
    "service.service.suggest_image",
    kind="query",
    permission="service.view_service",
    input=ServiceImageSuggestIn,
    output=ServiceImageSuggestOut,
    expose_api=True,
    ai={
        "description": "Propose images of ERPlora's shared image library for a service's photo («ponle foto al corte "
        "de señora»), the service named by its id or its name: the best matches for its name first, each with its title and its reference (catalog:<folder>/<name>). It "
        "never sets one: show them, and set the one the person picks with service.service.set_image.",
        "asks": {
            "en": (
                "suggest a drawing from the library for the beard trim",
                "which library drawing fits the manicure service?",
            ),
            "es": ("propón dibujos de la biblioteca para la manicura", "¿qué dibujo le pondrías al servicio de tinte?"),
        },
    },
)
def suggest_image(ctx: OperationContext, data: ServiceImageSuggestIn) -> dict:
    """SERVICE-F34: the library searched by the service's name in either of its languages, titled in the business's
    (the one its services are named in)."""
    service = find_service(data.id, data.service)
    language = business_language(ctx)
    found = image_library(ctx).search(service.name, language)
    return {
        "service_id": service.id,
        "query": service.name,
        "rows": [image.row(language) for image in found[: data.limit]],
    }


@operation(
    "service.service.list_for_sale",
    kind="query",
    permission="service.view_service",
    input=ServiceForSaleIn,
    output=ServiceSalePage,
    expose_api=True,
    ai={
        "description": "The catalog to sell and to book: the offered services with their pricing, price, duration, "
        "category and tax category; needs_tax_setup marks the ones that cannot be charged yet.",
        "asks": {
            "en": ("which services can I sell right now?", "what services are ready to be sold and booked?"),
            "es": ("¿qué servicios se pueden vender ahora mismo?", "pásame la lista de servicios a la venta"),
        },
    },
)
def list_for_sale(ctx: OperationContext, params: ServiceForSaleIn) -> dict:
    services = Service.objects.filter(is_active=True).select_related(
        "category", "tax_category"
    )
    if params.search:
        services = services.filter(name__icontains=params.search)
    if params.category_id:
        services = services.filter(category_id=params.category_id)
    return _page(services.order_by("name", "id"), params, partial(_sale_row, urls=images.Urls(ctx.scope)))


@operation(
    "service.catalog.status",
    kind="query",
    permission="service.view_service",
    input=NoIn,
    output=CatalogStatusOut,
    expose_api=True,
    ai={
        "description": "How many services are offered, how many can be charged and how many still need a tax category.",
        "asks": {
            "en": ("how many services in the catalogue can't be charged yet?", "how is the services catalogue doing?"),
            "es": ("¿cuántos servicios siguen sin su IVA?", "¿cómo va el catálogo de servicios?"),
        },
    },
)
def catalog_status(ctx: OperationContext, data: NoIn) -> dict:
    offered = Service.objects.filter(is_active=True)
    services = offered.count()
    sellable = offered.filter(
        tax_category__isnull=False, tax_category__is_active=True
    ).count()
    return {
        "services": services,
        "sellable_services": sellable,
        "needs_tax_setup": services - sellable,
    }
