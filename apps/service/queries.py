"""Read operations of the service app (``READ ONLY``): the catalog, its categories, the settings, who
performs each service, the vouchers of the catalog, the ones sold with their balance, their movements
and the checks that say whether a voucher can be voided, adjusted or spent, and why not.

Every list pages (``limit`` ≤ 100) with ``id`` as the last tie-break, so pages never overlap. The
``find_*`` helpers resolve how a person names a record (assistant, voice): by id, else an exact name,
else the only name that contains it; several → 409 ``*_ambiguous`` naming them. The balance of a
voucher sold is computed here, from its sessions and its adjustments (WORKBOOK «Para quien lo
mantiene»); services.py reads it again after locking the voucher's row.
"""

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

from django.db.models import (
    Case,
    CharField,
    Count,
    DateTimeField,
    F,
    IntegerField,
    Min,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.customer.queries import find_customer
from apps.service.models import (
    Assignment,
    Category,
    Grant,
    GrantAdjustment,
    Package,
    PackageItem,
    Redemption,
    Service,
    ServiceSettings,
)
from apps.service.schemas import (
    AdjustCheckOut,
    AssignmentListIn,
    AssignmentPage,
    ByIdIn,
    CatalogStatusOut,
    CategoryListIn,
    CategoryOut,
    CategoryPage,
    CategoryRefIn,
    EligibleIn,
    EligiblePage,
    GrantListIn,
    GrantPage,
    MovementListIn,
    MovementPage,
    NoIn,
    OrphanPage,
    PackageListIn,
    PackageOut,
    PackagePage,
    PackageRefIn,
    PageIn,
    RedeemCheckIn,
    RedeemCheckOut,
    ServiceForSaleIn,
    ServiceListIn,
    ServiceOut,
    ServicePage,
    ServiceRefIn,
    ServiceSalePage,
    SettingsOut,
    TenderOptionPage,
    TenderOptionsIn,
    VoidCheckOut,
)
from apps.staff.models import Member
from apps.staff.queries import resolve_member

SERVICE_NOT_FOUND = _("That service does not exist in this business.")
SERVICE_AMBIGUOUS = _("“%(said)s” matches several services: %(names)s. Say which one.")
CATEGORY_NOT_FOUND = _("That category does not exist in this business.")
CATEGORY_AMBIGUOUS = _(
    "“%(said)s” matches several categories: %(names)s. Say which one."
)
PACKAGE_NOT_FOUND = _("That package does not exist in this business.")
PACKAGE_AMBIGUOUS = _("“%(said)s” matches several packages: %(names)s. Say which one.")
GRANT_NOT_FOUND = _("That voucher sale does not exist in this business.")

#: How many names an ambiguous reference lists.
MAX_CANDIDATES = 5
#: Who may read a customer's name (the Customers app's permission).
CUSTOMER_VIEW = "customer.view"
TERMINATED = Member.Status.TERMINATED
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
CATEGORY_ORDER = {
    "sort_order": ("sort_order",),
    "name": ("name",),
    "parent_name": ("parent__name",),
    "service_count": ("service_count",),
}
PACKAGE_ORDER = {
    "sort_order": ("sort_order",),
    "name": ("name",),
    "fixed_price": ("fixed_price",),
    "item_count": ("item_count",),
    "status": ("status",),
}


# --- Shared with services.py, inside the command's own transaction ---------------------------------


def current_settings() -> ServiceSettings:
    """The business's settings; the factory ones (unsaved) if they were never saved."""
    return (
        ServiceSettings.objects.select_related("default_tax_category").first()
        or ServiceSettings()
    )


def _first_match(rows, said: str) -> list:
    """The rows of the first lookup that matches (an exact name, else a part of it), at most six."""
    for lookup in (Q(name__iexact=said), Q(name__icontains=said)):
        found = list(rows.filter(lookup).order_by("name", "id")[: MAX_CANDIDATES + 1])
        if found:
            return found
    return []


def held_rows(rows) -> list:
    """``rows``, each held until the command commits, taken in the same read and in id order, for a write that
    names them (a service put in a category or in a voucher, a voucher sold): their «Delete», archiving one or
    the Hub admin's deletion waits for that write, and in the order a move of the tree takes them, so the two
    never wait for each other in a circle. One taken away meanwhile is read once that ends: gone, or as it was
    left. ``FOR NO KEY UPDATE`` is the ORM's lightest lock: another write that names the same row waits its
    turn, while the database's own checks of what names it go on."""
    return list(rows.order_by("id").select_for_update(no_key=True, of=("self",)))


def _resolve(
    rows,
    item_id,
    said,
    *,
    lock,
    hold=False,
    missing,
    missing_code,
    ambiguous,
    ambiguous_code,
    named=None,
):
    """The row named by ``item_id`` (in ``rows``), or by ``said`` (in ``named``, ``rows`` by default):
    ``lock`` takes it to change it, ``hold`` to name it (``held_rows``)."""
    if item_id is None:
        candidates = _first_match(rows if named is None else named, said or "")
        if len(candidates) > 1:
            names = ", ".join(
                candidate.name for candidate in candidates[:MAX_CANDIDATES]
            )
            raise Conflict(
                str(ambiguous) % {"said": said, "names": names}, code=ambiguous_code
            )
        item_id = candidates[0].pk if candidates else None
    found = rows.filter(pk=item_id)
    if lock:
        found = found.select_for_update(of=("self",))
    elif hold:
        found = found.select_for_update(no_key=True, of=("self",))
    row = found.first()
    if row is None:
        raise NotFound(str(missing), code=missing_code)
    return row


def find_service(
    service_id: UUID | None,
    said: str | None,
    *,
    lock: bool = False,
    hold: bool = False,
    offered: bool = False,
    archived: bool = False,
) -> Service:
    """A service by id (archived too, unless ``offered``), or by its name among the offered ones (the
    archived ones with ``archived``, to restore one by name)."""
    rows = Service.objects.all()
    return _resolve(
        rows.filter(is_active=True) if offered else rows,
        service_id,
        said,
        lock=lock,
        hold=hold,
        missing=SERVICE_NOT_FOUND,
        missing_code="service.service_not_found",
        ambiguous=SERVICE_AMBIGUOUS,
        ambiguous_code="service.service_ambiguous",
        named=rows.filter(is_active=not archived),
    )


def find_category(
    category_id: UUID | None, said: str | None, *, lock: bool = False, hold: bool = False
) -> Category:
    """A live category, by id or by name."""
    return _resolve(
        Category.objects.filter(is_deleted=False),
        category_id,
        said,
        lock=lock,
        hold=hold,
        missing=CATEGORY_NOT_FOUND,
        missing_code="service.category_not_found",
        ambiguous=CATEGORY_AMBIGUOUS,
        ambiguous_code="service.category_ambiguous",
    )


def find_package(
    package_id: UUID | None,
    said: str | None,
    *,
    lock: bool = False,
    hold: bool = False,
    include_deleted: bool = False,
) -> Package:
    """A package by id (a deleted one too with ``include_deleted``), or a live one by its name."""
    rows = Package.objects.all()
    return _resolve(
        rows if include_deleted else rows.filter(is_deleted=False),
        package_id,
        said,
        lock=lock,
        hold=hold,
        missing=PACKAGE_NOT_FOUND,
        missing_code="service.package_not_found",
        ambiguous=PACKAGE_AMBIGUOUS,
        ambiguous_code="service.package_ambiguous",
        named=rows.filter(is_deleted=False),
    )


def lock_grant(grant_id: UUID) -> None:
    """Locks the row of a voucher sold until the end of the command's transaction (or ``NotFound``)."""
    if not Grant.objects.select_for_update().filter(pk=grant_id).exists():
        raise NotFound(str(GRANT_NOT_FOUND), code="service.grant_not_found")


def find_grant(grant_id: UUID) -> Grant:
    """A voucher sold with its balance read now (after ``lock_grant`` in a command: what the lock let through)."""
    grant = grants().filter(pk=grant_id).first()
    if grant is None:
        raise NotFound(str(GRANT_NOT_FOUND), code="service.grant_not_found")
    return grant


# --- Rows -------------------------------------------------------------------------------------------


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


def _service_row(service: Service) -> dict:
    tax = service.tax_category
    return {
        **{field: getattr(service, field) for field in SERVICE_FIELDS},
        "category_name": service.category.name if service.category else None,
        "tax_category_key": tax.key if tax else None,
        "tax_category_name": tax.display_name if tax else None,
        "needs_tax_setup": needs_tax_setup(service),
    }


def load_service(service_id: UUID) -> dict:
    """A service as a ``ServiceOut``; services.py returns it after a write."""
    return _service_row(_services().get(pk=service_id))


def _sale_row(service: Service) -> dict:
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
    }


def _categories():
    return (
        Category.objects.filter(is_deleted=False)
        .select_related("parent")
        .annotate(service_count=Count("services", filter=Q(services__is_active=True)))
    )


def _category_row(category: Category) -> dict:
    fields = (
        "id",
        "name",
        "description",
        "parent_id",
        "icon",
        "color",
        "sort_order",
        "service_count",
        "created_at",
        "updated_at",
    )
    return {
        **{field: getattr(category, field) for field in fields},
        "parent_name": category.parent.name if category.parent else None,
    }


def load_category(category_id: UUID) -> dict:
    return _category_row(_categories().get(pk=category_id))


def settings_row(settings: ServiceSettings) -> dict:
    tax = settings.default_tax_category
    return {
        "default_duration": settings.default_duration,
        "default_buffer_time": settings.default_buffer_time,
        "default_tax_category_id": tax.id if tax else None,
        "default_tax_category_key": tax.key if tax else None,
        "default_tax_category_name": tax.display_name if tax else None,
        "show_prices": settings.show_prices,
        "show_duration": settings.show_duration,
        "allow_online_booking": settings.allow_online_booking,
        "updated_at": None if settings._state.adding else settings.updated_at,
    }


def _assignments():
    return Assignment.objects.select_related("service", "member").exclude(
        member__status=TERMINATED
    )


def assignment_row(assignment: Assignment) -> dict:
    service = assignment.service
    return {
        "id": assignment.id,
        "service_id": service.id,
        "service_name": service.name,
        "member_id": assignment.member_id,
        "member_name": assignment.member.full_name,
        "custom_duration": assignment.custom_duration,
        "custom_price": assignment.custom_price,
        "is_primary": assignment.is_primary,
        "is_active": assignment.is_active,
        "duration": assignment.custom_duration or service.duration_minutes,
        "price": service.price
        if assignment.custom_price is None
        else assignment.custom_price,
    }


def load_assignment(assignment_id: UUID) -> dict:
    return assignment_row(_assignments().get(pk=assignment_id))


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


def _adjusted(field: str, condition: Q | None = None):
    rows = GrantAdjustment.objects.filter(grant=OuterRef("pk"))
    if condition is not None:
        rows = rows.filter(condition)
    total = rows.values("grant").annotate(total=Sum(field)).values("total")[:1]
    return Coalesce(
        Subquery(total, output_field=IntegerField()),
        Value(0),
        output_field=IntegerField(),
    )


def live_sessions(now: dt.datetime) -> Q:
    """The sessions that count against a balance ``now``: delivered, or held and inside their deadline."""
    return Q(status=Redemption.Status.CONSUMED) | Q(
        status=Redemption.Status.HELD, hold_until__gt=now
    )


def grants(now: dt.datetime | None = None):
    """Vouchers sold with what their balance needs ``now``: sessions spent or held, sessions added and
    taken, days added."""
    now = now or timezone.now()
    spent = (
        Redemption.objects.filter(live_sessions(now), grant=OuterRef("pk"))
        .values("grant")
        .annotate(n=Count("id"))
        .values("n")[:1]
    )
    return Grant.objects.select_related("package", "customer").annotate(
        used=Coalesce(
            Subquery(spent, output_field=IntegerField()),
            Value(0),
            output_field=IntegerField(),
        ),
        uses_added=_adjusted("uses_delta", Q(uses_delta__gt=0)),
        uses_taken=_adjusted("uses_delta", Q(uses_delta__lt=0)),
        days_added=_adjusted("days_delta"),
    )


@dataclass(frozen=True)
class Balance:
    max_uses: int | None
    remaining: int | None
    expires_at: dt.datetime | None
    is_expired: bool


def balance(grant: Grant, now: dt.datetime | None = None) -> Balance:
    """What a voucher sold (annotated by ``grants()``) has left and when it expires, ``now``."""
    now = now or timezone.now()
    total = (
        None
        if grant.max_uses is None
        else grant.max_uses + grant.uses_added + grant.uses_taken
    )
    expires_at = (
        None
        if grant.validity_days is None
        else grant.granted_at
        + dt.timedelta(days=grant.validity_days + grant.days_added)
    )
    return Balance(
        max_uses=total,
        remaining=None if total is None else total - grant.used,
        expires_at=expires_at,
        is_expired=expires_at is not None and now > expires_at,
    )


def _customer_name(ctx: OperationContext, grant: Grant) -> str | None:
    customer = grant.customer
    return (
        customer.name
        if ctx.has(CUSTOMER_VIEW) and customer.deleted_at is None
        else None
    )


def grant_row(
    ctx: OperationContext, grant: Grant, now: dt.datetime | None = None
) -> dict:
    fields = (
        "id",
        "package_id",
        "customer_id",
        "granted_at",
        "source",
        "sale_id",
        "amount",
        "net_amount",
        "tax_amount",
        "note",
        "voided_at",
        "voided_by",
        "void_reason",
        "used",
        "uses_added",
        "days_added",
    )
    state = balance(grant, now)
    voided = grant.voided_at is not None
    return {
        **{field: getattr(grant, field) for field in fields},
        "package_name": grant.package.name,
        "customer_name": _customer_name(ctx, grant),
        "customer_deleted_at": grant.customer.deleted_at,
        "uses_removed": -grant.uses_taken,
        "max_uses": state.max_uses,
        "remaining": state.remaining,
        "expires_at": state.expires_at,
        "is_expired": state.is_expired,
        "status": "voided" if voided else "active",
        "can_void": not voided and grant.used == 0,
        "can_adjust": not voided
        and (grant.max_uses is not None or grant.validity_days is not None),
    }


def load_grant(ctx: OperationContext, grant_id: UUID) -> dict:
    return grant_row(ctx, find_grant(grant_id))


# --- Services -------------------------------------------------------------------------------------


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
        "archived ones."
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
        _sorted(services, params.sort, SERVICE_ORDER, ("name", "id")),
        params,
        _service_row,
    )


@operation(
    "service.service.get",
    kind="query",
    permission="service.view_service",
    input=ServiceRefIn,
    output=ServiceOut,
    expose_api=True,
    ai={
        "description": "Get one service with everything it has, named by its id or its name (an archived one by its id)."
    },
)
def get_service(ctx: OperationContext, data: ServiceRefIn) -> dict:
    return load_service(find_service(data.id, data.service).id)


@operation(
    "service.service.list_for_sale",
    kind="query",
    permission="service.view_service",
    input=ServiceForSaleIn,
    output=ServiceSalePage,
    expose_api=True,
    ai={
        "description": "The catalog to sell and to book: the offered services with their pricing, price, duration, "
        "category and tax category; needs_tax_setup marks the ones that cannot be charged yet."
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
    return _page(services.order_by("name", "id"), params, _sale_row)


@operation(
    "service.catalog.status",
    kind="query",
    permission="service.view_service",
    input=NoIn,
    output=CatalogStatusOut,
    expose_api=True,
    ai={
        "description": "How many services are offered, how many can be charged and how many still need a tax category."
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


# --- Categories -----------------------------------------------------------------------------------


@operation(
    "service.category.list",
    kind="query",
    permission="service.view_category",
    input=CategoryListIn,
    output=CategoryPage,
    expose_api=True,
    ai={
        "description": "List the service categories by their order, with their parent and how many offered services each has."
    },
)
def list_categories(ctx: OperationContext, params: CategoryListIn) -> dict:
    categories = _categories()
    if params.search:
        categories = categories.filter(name__icontains=params.search)
    if params.parent_id:
        categories = categories.filter(parent_id=params.parent_id)
    return _page(
        _sorted(categories, params.sort, CATEGORY_ORDER, ("sort_order", "name", "id")),
        params,
        _category_row,
    )


@operation(
    "service.category.get",
    kind="query",
    permission="service.view_category",
    input=CategoryRefIn,
    output=CategoryOut,
    expose_api=True,
    ai={"description": "Get one service category, named by its id or its name."},
)
def get_category(ctx: OperationContext, data: CategoryRefIn) -> dict:
    return load_category(find_category(data.id, data.category).id)


# --- Settings -------------------------------------------------------------------------------------


@operation(
    "service.settings.get",
    kind="query",
    permission="service.view_service",
    input=NoIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "The service settings: the duration, buffer, tax category and online booking a new service takes."
    },
)
def get_settings(ctx: OperationContext, data: NoIn) -> dict:
    return settings_row(current_settings())


# --- Who performs each service --------------------------------------------------------------------


@operation(
    "service.assignment.list",
    kind="query",
    permission="service.view_service",
    input=AssignmentListIn,
    output=AssignmentPage,
    expose_api=True,
    ai={
        "description": "List who performs each service: the professionals of a service, or the services of a "
        "professional, with their own duration and price and their main service first."
    },
)
def list_assignments(ctx: OperationContext, params: AssignmentListIn) -> dict:
    assignments = _assignments()
    if params.service_id or params.service:
        assignments = assignments.filter(
            service=find_service(params.service_id, params.service)
        )
    if params.member_id or params.member:
        assignments = assignments.filter(
            member=resolve_member(params.member_id, params.member)
        )
    ordered = assignments.order_by(
        "-is_primary", "member__first_name", "member__last_name", "service__name", "id"
    )
    return _page(ordered, params, assignment_row)


@operation(
    "service.assignment.eligible",
    kind="query",
    permission="service.view_service",
    input=EligibleIn,
    output=EligiblePage,
    expose_api=True,
    ai={
        "description": "Who may perform a service: the active, bookable professionals with an active assignment, "
        "with their own duration and price, main service first. Empty = nobody declared (the diary then lets the "
        "whole bookable team do it)."
    },
)
def eligible(ctx: OperationContext, params: EligibleIn) -> dict:
    service = find_service(params.service_id, params.service)
    assignments = (
        Assignment.objects.select_related("service", "member")
        .filter(
            service=service,
            is_active=True,
            member__status=Member.Status.ACTIVE,
            member__is_bookable=True,
        )
        .order_by("-is_primary", "member__first_name", "member__last_name", "id")
    )

    def row(assignment: Assignment) -> dict:
        out = assignment_row(assignment)
        member = assignment.member
        return {
            **{
                field: out[field]
                for field in (
                    "member_id",
                    "custom_duration",
                    "custom_price",
                    "is_primary",
                    "duration",
                    "price",
                )
            },
            "full_name": member.full_name,
            "color": member.color,
            "booking_buffer": member.booking_buffer,
        }

    return _page(assignments, params, row)


# --- Packages -------------------------------------------------------------------------------------


@operation(
    "service.package.list",
    kind="query",
    permission="service.view_package",
    input=PackageListIn,
    output=PackagePage,
    expose_api=True,
    ai={
        "description": "List the vouchers of the catalog with their lines, discount, closed price, uses and validity. "
        "status=deleted lists the deleted ones somebody bought."
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
        _sorted(packages, params.sort, PACKAGE_ORDER, ("sort_order", "name", "id")),
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
        "description": "Get one voucher of the catalog with its lines, named by its id or its name."
    },
)
def get_package(ctx: OperationContext, data: PackageRefIn) -> dict:
    return load_package(find_package(data.id, data.package, include_deleted=True).id)


# --- Vouchers sold --------------------------------------------------------------------------------


@operation(
    "service.grant.list",
    kind="query",
    permission="service.view_package_balance",
    input=GrantListIn,
    output=GrantPage,
    expose_api=True,
    ai={
        "description": "List the vouchers sold, most recent first: the ones of a package, or the ones a customer owns "
        "(by name or phone), with the sessions used and left, the expiry and whether it was voided."
    },
)
def list_grants(ctx: OperationContext, params: GrantListIn) -> dict:
    sold = grants()
    if params.package_id or params.package:
        sold = sold.filter(
            package=find_package(
                params.package_id, params.package, include_deleted=True
            )
        )
    if params.customer_id or params.customer:
        card = find_customer(params.customer_id, params.customer, live=False)
        # A card merged into this one (Customers keeps the chain one level deep) still shows its
        # vouchers until the reaction to customer.customer.merged moves them.
        sold = sold.filter(Q(customer=card) | Q(customer__merged_into=card))
    if params.status is not None:
        sold = sold.filter(voided_at__isnull=params.status == "active")
    now = timezone.now()
    return _page(
        sold.order_by("-granted_at", "-id"),
        params,
        lambda grant: grant_row(ctx, grant, now),
    )


@operation(
    "service.grant.list_orphans",
    kind="query",
    permission="service.view_orphan_grant",
    input=PageIn,
    output=OrphanPage,
    expose_api=True,
    ai={
        "description": "List the live vouchers whose customer card was deleted or erased, most recent first, with "
        "what is left and the customer's reference (no personal data)."
    },
)
def list_orphans(ctx: OperationContext, params: PageIn) -> dict:
    orphans = grants().filter(
        voided_at__isnull=True,
        customer__deleted_at__isnull=False,
        customer__merged_into__isnull=True,
    )
    now = timezone.now()

    def row(grant: Grant) -> dict:
        state = balance(grant, now)
        return {
            "id": grant.id,
            "package_id": grant.package_id,
            "package_name": grant.package.name,
            "customer_id": grant.customer_id,
            "customer_deleted_at": grant.customer.deleted_at,
            "granted_at": grant.granted_at,
            "amount": grant.amount,
            "remaining": state.remaining,
            "is_expired": state.is_expired,
        }

    return _page(orphans.order_by("-customer__deleted_at", "-id"), params, row)


@operation(
    "service.grant.void_check",
    kind="query",
    permission="service.void_grant",
    input=ByIdIn,
    output=VoidCheckOut,
    expose_api=True,
    ai={
        "description": "Whether a voucher sold can be voided now and, if not, why (already_voided, in_use)."
    },
)
def void_check(ctx: OperationContext, data: ByIdIn) -> dict:
    grant = find_grant(data.id)
    reason = void_refusal(grant)
    return {
        "id": grant.id,
        "voidable": reason == "",
        "reason": reason,
        "used": grant.used,
    }


def void_refusal(grant: Grant) -> str:
    """Why a voucher sold cannot be voided (``""`` when it can): only an untouched one is."""
    if grant.voided_at is not None:
        return "already_voided"
    if grant.used > 0:
        return "in_use"
    return ""


@operation(
    "service.grant.adjust_check",
    kind="query",
    permission="service.adjust_grant",
    input=ByIdIn,
    output=AdjustCheckOut,
    expose_api=True,
    ai={
        "description": "What can be adjusted on a voucher sold: sessions (if it has a limit) and its expiry (if it has one)."
    },
)
def adjust_check(ctx: OperationContext, data: ByIdIn) -> dict:
    grant = find_grant(data.id)
    state = balance(grant)
    return {
        "id": grant.id,
        "can_add_uses": grant.max_uses is not None,
        "can_extend": grant.validity_days is not None,
        "uses_left": state.remaining,
        "expires_at": state.expires_at,
        "reason": "already_voided" if grant.voided_at is not None else "",
    }


@operation(
    "service.grant.redeem_check",
    kind="query",
    permission="service.redeem_package",
    input=RedeemCheckIn,
    output=RedeemCheckOut,
    expose_api=True,
    ai={
        "description": "Whether a session of a voucher sold can be spent now (optionally on a service) and, if not, "
        "why: voided, expired, no_uses_left or does_not_cover_service."
    },
)
def redeem_check(ctx: OperationContext, data: RedeemCheckIn) -> dict:
    grant = find_grant(data.id)
    service = (
        find_service(data.service_id, data.service)
        if (data.service_id or data.service)
        else None
    )
    state = balance(grant)
    reason = redeem_refusal(grant, state, service)
    return {"id": grant.id, "redeemable": reason == "", "reason": reason, "remaining": state.remaining}


def redeem_refusal(grant: Grant, state: Balance, service: Service | None) -> str:
    """Why a session cannot be spent (``""`` when it can), in the order the WORKBOOK says them."""
    if grant.voided_at is not None:
        return "voided"
    if state.is_expired:
        return "expired"
    if state.remaining is not None and state.remaining <= 0:
        return "no_uses_left"
    if (
        service is not None
        and not PackageItem.objects.filter(
            package_id=grant.package_id, service=service
        ).exists()
    ):
        return "does_not_cover_service"
    return ""


# --- The voucher as a tender of the till (SERVICE-F22) -----------------------------------------------


@operation(
    "service.grant.tender_options",
    kind="query",
    permission="service.redeem_package",
    input=TenderOptionsIn,
    output=TenderOptionPage,
    expose_api=True,
    ai={
        "description": "The vouchers a customer (by id, name or phone) owns that can pay a line of a service now: they "
        "cover it, have sessions left and have not expired. The first one is the one the till spends first, with why: "
        "counted sessions before unlimited, then the one expiring first, the one already started, the one with fewest "
        "sessions left, the one bought first."
    },
)
def tender_options(ctx: OperationContext, params: TenderOptionsIn) -> dict:
    card = find_customer(params.customer_id, params.customer, live=False)
    service = find_service(params.service_id, params.service)
    now = timezone.now()
    started = (
        Redemption.objects.filter(live_sessions(now), grant=OuterRef("pk"))
        .values("grant")
        .annotate(first=Min("redeemed_at"))
        .values("first")[:1]
    )
    candidates = (
        grants(now)
        .filter(
            Q(customer=card) | Q(customer__merged_into=card),
            voided_at__isnull=True,
            package__items__service=service,
        )
        .annotate(first_used=Subquery(started, output_field=DateTimeField()))
    )
    eligible = []
    for grant in candidates:
        state = balance(grant, now)
        if state.is_expired or (state.remaining is not None and state.remaining <= 0):
            continue
        eligible.append((grant, state))
    eligible.sort(key=lambda option: _tender_rank(*option))
    reason = _first_reason(eligible)
    rows = [
        {
            "grant_id": grant.id,
            "package_id": grant.package_id,
            "package_name": grant.package.name,
            "granted_at": grant.granted_at,
            "max_uses": state.max_uses,
            "used": grant.used,
            "remaining_before": state.remaining,
            "remaining_after": None if state.remaining is None else state.remaining - 1,
            "is_unlimited": state.max_uses is None,
            "expires_at": state.expires_at,
            "is_default": position == 0,
            "default_reason": reason if position == 0 else "",
            "candidate_count": len(eligible),
        }
        for position, (grant, state) in enumerate(eligible)
    ]
    return {
        "rows": rows[params.offset : params.offset + params.limit],
        "total": len(rows),
        "limit": params.limit,
        "offset": params.offset,
    }


_LAST = dt.datetime.max.replace(tzinfo=dt.UTC)


def _tender_rank(grant: Grant, state: Balance) -> tuple:
    """The order the till spends vouchers in (the old module's tie-break, ADR-0386)."""
    return (
        state.max_uses is None,
        state.expires_at or _LAST,
        grant.first_used or _LAST,
        state.remaining if state.remaining is not None else 0,
        grant.granted_at,
        grant.id,
    )


#: The steps of the tie-break, in order, and the reason each one gives when it decides.
_TIE_BREAK = (
    (lambda grant, state: state.max_uses is None, "finite_before_unlimited"),
    (lambda grant, state: state.expires_at, "expires_first"),
    (lambda grant, state: grant.first_used, "already_started"),
    (lambda grant, state: state.remaining, "fewest_sessions_left"),
    (lambda grant, state: grant.granted_at, "oldest_voucher"),
)


def _first_reason(eligible: list) -> str:
    """Why the first option goes first: the first step of the tie-break that tells it from the second."""
    if not eligible:
        return ""
    if len(eligible) == 1:
        return "only_option"
    first, second = eligible[0], eligible[1]
    for step, reason in _TIE_BREAK:
        if step(*first) != step(*second):
            return reason
    return "stable_order"


# --- Movements --------------------------------------------------------------------------------------


@operation(
    "service.movement.list",
    kind="query",
    permission="service.view_package_balance",
    input=MovementListIn,
    output=MovementPage,
    expose_api=True,
    ai={
        "description": "The movements of a voucher of the catalog, most recent first: every session spent and every "
        "courtesy (adjusted) or correction (corrected), of every customer, with who and why."
    },
)
def list_movements(ctx: OperationContext, params: MovementListIn) -> dict:
    package = find_package(params.package_id, params.package, include_deleted=True)
    now = timezone.now()
    sessions = (
        Redemption.objects.filter(grant__package=package)
        .select_related("grant__customer", "service")
        .annotate(at=_session_moment(now))
    )
    adjustments = GrantAdjustment.objects.filter(grant__package=package).select_related(
        "grant__customer"
    )
    take = params.offset + params.limit
    rows = [
        _session_row(ctx, session, now)
        for session in sessions.order_by("-at", "-id")[:take]
    ]
    rows += [
        _adjustment_row(ctx, adjustment)
        for adjustment in adjustments.order_by("-created_at", "-id")[:take]
    ]
    rows.sort(key=lambda row: (row["at"], row["id"]), reverse=True)
    return {
        "rows": rows[params.offset : take],
        "total": sessions.count() + adjustments.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


def _movement(ctx: OperationContext, grant: Grant) -> dict:
    customer = grant.customer
    visible = ctx.has(CUSTOMER_VIEW) and customer.deleted_at is None
    return {
        "grant_id": grant.id,
        "customer_id": customer.id,
        "customer_name": customer.name if visible else None,
    }


def _lapsed(now: dt.datetime) -> Q:
    """A hold past its deadline that the hourly task has not marked yet: it reads as expired."""
    return Q(status=Redemption.Status.HELD, hold_until__lte=now)


def _session_moment(now: dt.datetime):
    """When a session took its last step: given back, released or expired, delivered, or held."""
    ended = [
        Redemption.Status.RELEASED,
        Redemption.Status.EXPIRED,
        Redemption.Status.RETURNED,
    ]
    return Case(
        When(status__in=ended, ended_at__isnull=False, then=F("ended_at")),
        When(_lapsed(now), then=F("hold_until")),
        When(
            status=Redemption.Status.CONSUMED,
            settled_at__isnull=False,
            then=F("settled_at"),
        ),
        default=F("redeemed_at"),
        output_field=DateTimeField(),
    )


def session_kind(session: Redemption, now: dt.datetime) -> str:
    if session.status == Redemption.Status.HELD and session.hold_until <= now:
        return Redemption.Status.EXPIRED
    return session.status


def _session_actor(session: Redemption, kind: str, ended: bool) -> str:
    """Who took the session's last step; a hold that lapsed on its own was the platform's."""
    if not ended:
        return session.actor
    if kind == Redemption.Status.EXPIRED:
        return session.ended_by or "system"
    return session.ended_by


def _session_row(ctx: OperationContext, session: Redemption, now: dt.datetime) -> dict:
    kind = session_kind(session, now)
    ended = kind in (
        Redemption.Status.RELEASED,
        Redemption.Status.EXPIRED,
        Redemption.Status.RETURNED,
    )
    return {
        **_movement(ctx, session.grant),
        "id": session.id,
        "kind": kind,
        "at": session.at,
        "service_id": session.service_id,
        "service_name": session.service.name if session.service else None,
        "sale_id": session.sale_id,
        "appointment_id": session.appointment_id,
        "note": session.note,
        "actor": _session_actor(session, kind, ended),
        "uses_delta": 0 if ended else -1,
        "days_delta": 0,
        "reason": session.return_reason if kind == Redemption.Status.RETURNED else "",
    }


def _adjustment_row(ctx: OperationContext, adjustment: GrantAdjustment) -> dict:
    return {
        **_movement(ctx, adjustment.grant),
        "id": adjustment.id,
        "kind": "corrected" if adjustment.uses_delta < 0 else "adjusted",
        "at": adjustment.created_at,
        "service_id": None,
        "service_name": None,
        "sale_id": None,
        "appointment_id": None,
        "note": "",
        "actor": adjustment.actor,
        "uses_delta": adjustment.uses_delta,
        "days_delta": adjustment.days_delta,
        "reason": adjustment.reason,
    }


# --- Helpers ----------------------------------------------------------------------------------------


def _bounds(**lookups) -> dict:
    """The lookups whose value was given (a filter left empty narrows nothing)."""
    return {lookup: value for lookup, value in lookups.items() if value is not None}


def _sorted(
    rows, sort: str, columns: dict[str, tuple[str, ...]], tie_break: tuple[str, ...]
):
    """``rows`` by ``sort`` (a leading «-» reverses it), then by ``tie_break``; nulls last either way."""
    descending = sort.startswith("-")
    keys = [
        F(column).desc(nulls_last=True)
        if descending
        else F(column).asc(nulls_last=True)
        for column in columns[sort.lstrip("-")]
    ]
    return rows.order_by(*keys, *tie_break)


def _page(queryset, params, row) -> dict:
    return {
        "rows": [
            row(item) for item in queryset[params.offset : params.offset + params.limit]
        ],
        "total": queryset.count(),
        "limit": params.limit,
        "offset": params.offset,
    }
