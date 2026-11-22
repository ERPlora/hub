"""The vouchers of the catalog: a voucher by how a person names it, its rows and its reads."""

from uuid import UUID

from django.db.models import Case, CharField, Count, Prefetch, Value, When
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.operations import operation

from apps.service.models import Package, PackageItem
from apps.service.queries.reads import _page, _resolve
from apps.service.schemas.fields import PackageRefIn
from apps.service.schemas.packages import PackageListIn, PackageOut, PackagePage
from base.ordering import list_order_for

PACKAGE_NOT_FOUND = _("That package does not exist in this business.")
PACKAGE_AMBIGUOUS = _("“%(said)s” matches several packages: %(names)s. Say which one.")

PACKAGE_ORDER = {
    "sort_order": ("sort_order",),
    "name": ("name",),
    "fixed_price": ("fixed_price",),
    "item_count": ("item_count",),
    "status": ("status",),
}


def find_package(  # noqa: PLR0913
    package_id: UUID | None,
    said: str | None,
    *,
    lock: bool = False,
    hold: bool = False,
    include_deleted: bool = False,
    rows=None,
) -> Package:
    """A package by id (a deleted one too with ``include_deleted``), or a live one by its name; from
    ``rows`` when given, in one read (as ``find_service``)."""
    packages = Package.objects.all()
    found_in = packages if rows is None else rows
    return _resolve(
        found_in if include_deleted else found_in.filter(is_deleted=False),
        package_id,
        said,
        lock=lock,
        hold=hold,
        missing=PACKAGE_NOT_FOUND,
        missing_code="service.package_not_found",
        ambiguous=PACKAGE_AMBIGUOUS,
        ambiguous_code="service.package_ambiguous",
        named=packages.filter(is_deleted=False),
    )


def _packages():
    lines = PackageItem.objects.select_related("service").order_by("sort_order", "id")
    return Package.objects.annotate(
        item_count=Count("items", distinct=True),
        grant_count=Count("grants", distinct=True),
        status=Case(
            When(is_deleted=True, then=Value("deleted")),
            When(is_active=False, then=Value("archived")),
            default=Value("active"),
            output_field=CharField(),
        ),
    ).prefetch_related(Prefetch("items", queryset=lines))


def _package_row(package: Package) -> dict:
    fields = (
        "id",
        "name",
        "description",
        "discount_type",
        "discount_percent_bp",
        "discount_amount",
        "fixed_price",
        "validity_days",
        "max_uses",
        "is_active",
        "is_featured",
        "sort_order",
        "status",
        "item_count",
        "grant_count",
        "created_at",
        "updated_at",
    )
    return {
        **{field: getattr(package, field) for field in fields},
        "items": [
            {
                "id": item.id,
                "service_id": item.service_id,
                "service_name": item.service.name,
                "service_price": item.service.price,
                "sessions": item.sessions,
                "sort_order": item.sort_order,
            }
            for item in package.items.all()
        ],
    }


def load_package(package_id: UUID) -> dict:
    return _package_row(_packages().get(pk=package_id))


@operation(
    "service.package.list",
    kind="query",
    permission="service.view_package",
    input=PackageListIn,
    output=PackagePage,
    expose_api=True,
    ai={
        "description": "List the vouchers of the catalog with their lines, discount, closed price, uses and validity. "
        "status=deleted lists the deleted ones somebody bought.",
        "asks": {
            "en": ("list our vouchers", "show me the session packs on offer"),
            "es": ("enséñame la lista de bonos", "dime qué bonos ofrecemos y cuántas sesiones trae cada uno"),
        },
    },
)
def list_packages(ctx: OperationContext, params: PackageListIn) -> dict:
    packages = _packages()
    if params.status == "deleted":
        packages = packages.filter(is_deleted=True, grant_count__gt=0)
    else:
        packages = packages.filter(is_deleted=False)
        if params.status is not None:
            packages = packages.filter(is_active=params.status == "active")
    for text in (params.search, params.name):
        if text:
            packages = packages.filter(name__icontains=text)
    return _page(
        packages.order_by(*list_order_for(params.sort, "sort_order", "name", columns=PACKAGE_ORDER, nulls_last=True)),
        params,
        _package_row,
    )


@operation(
    "service.package.get",
    kind="query",
    permission="service.view_package",
    input=PackageRefIn,
    output=PackageOut,
    expose_api=True,
    ai={
        "description": "Get one voucher of the catalog with its lines, named by its id or its name.",
        "asks": {
            "en": ("what's in the ten-session laser voucher?", "show me the details of the massage pack"),
            "es": ("¿qué incluye el bono de diez sesiones de láser?", "dame los detalles del bono de masajes"),
        },
    },
)
def get_package(ctx: OperationContext, data: PackageRefIn) -> dict:
    return _package_row(
        find_package(data.id, data.package, include_deleted=True, rows=_packages())
    )
