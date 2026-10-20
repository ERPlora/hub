"""Read operations of the sale app (``READ ONLY``) and the helpers the writes share with them.

The helpers that freeze a line (``freeze_product_line``, ``freeze_open_line``, ``freeze_service_line``)
read Inventory's product and units, and Services' service, through those apps' own operations, with
the caller's session: neither is a requirement of the sale app (PLAN §20.5), so their tables are never
read here. ``call_app`` is the one door to an app sale does not require (Services' catalog and voucher sessions,
Invoicing's documents, Cash register's drawer, Appointments' bookings), by the name of its operation. ``valuate`` is the one
valuation of a charge (``pricing.value`` over tax's closing), shared by the preview and the checkout.
"""

import datetime as dt
from collections.abc import Iterable
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

import pydantic
from django.conf import settings as django_settings
from django.db.models import Count, Exists, F, Func, JSONField, OuterRef, Q, QuerySet, Sum
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Coalesce
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import (
    AppInactive,
    Conflict,
    InvalidPayload,
    NotFound,
    PermissionDenied,
)
from live.operations import UnknownOperation, get, operation

from apps.sale import pricing
from apps.sale.models import (
    FACTORY_METHOD_NAMES,
    FiscalStatus,
    Department,
    Order,
    OrderLine,
    PaymentMethod,
    QuickNote,
    Refund,
    RefundLine,
    Sale,
    SaleLine,
    Settings,
)
from apps.sale.schemas import (
    BusinessDayOut,
    ByStaffOut,
    DepartmentListIn,
    DepartmentPage,
    EmptyIn,
    LastDaysOut,
    OpenLineFields,
    OrderListIn,
    OrderOut,
    OrderPage,
    OrderRefIn,
    PaymentMethodListIn,
    PaymentMethodPage,
    PeriodIn,
    PreviewIn,
    PreviewOut,
    ProductLineIn,
    QuickNoteListIn,
    QuickNotePage,
    RefundByKeyIn,
    RefundByKeyOut,
    RefundListOut,
    RefundOptionsOut,
    SaleByKeyIn,
    SaleByKeyOut,
    SaleListIn,
    SaleOut,
    SalePage,
    SaleRefIn,
    ServiceLineFields,
    SettingsOut,
    StatsOut,
    TodayOut,
)
from apps.tax.models import TaxCategory
from apps.tax.queries import (
    business_jurisdiction,
    business_tax_kind,
    business_today,
    category_by_reference,
    current_rates,
)
from apps.tax.schemas import TAX_KIND_NAMES

CURRENCY = "EUR"
#: In a business of Spain, no cash at all from this total on (Ley 7/2012, art. 7), mixed included.
CASH_LIMIT = {"ES": 100_000}
#: In a business of Spain, a ticket (simplified invoice) up to this total, VAT included (RD 1619/2012).
TICKET_LIMIT = {"ES": 300_000}
GRID_FALLBACK = Decimal("0.001")

ORDER_NOT_FOUND = _("That check does not exist.")
ORDER_CHANGED = _(
    "The check changed while it was being charged: a line was added, changed, removed, voided or charged, a "
    "discount was set or removed, or the check was split, merged or closed. Nothing was charged or changed: "
    "review the lines and try again."
)
SALE_NOT_FOUND = _("That sale does not exist.")
CATALOG_UNAVAILABLE = _(
    "Inventory's catalog cannot be read right now, so no product can be sold. Try again in a moment."
)
PRODUCT_NOT_AVAILABLE = _(
    "A product of the ticket is no longer in the catalog. Remove the line and add it again."
)
TAX_CATEGORY_MISSING = _(
    "«%(name)s» cannot be sold: it has no tax category. Its %(tax)s is missing."
)
SERVICES_UNAVAILABLE = _(
    "Services is not active in this business: its services cannot be sold nor its vouchers used. Take the "
    "voucher off the line to charge it."
)
INVOICE_UNAVAILABLE = _(
    "Invoicing is not active in this business: the sale is a ticket without a fiscal document."
)
CASH_REGISTER_UNAVAILABLE = _("Cash register is not active in this business.")
APPOINTMENT_UNAVAILABLE = _("Appointments is not active in this business.")
BOOKED_PRICE_MISMATCH = _(
    "That is not the price the appointment booked for this service: it is cancelled, it is another "
    "customer's, it did not book this service or it booked it cheaper."
)
APPOINTMENT_NOT_VISIBLE = _(
    "You cannot see that appointment: it is another professional's or it no longer exists. Charge it "
    "from the appointment's own professional or at the catalog price."
)
SERVICE_NOT_AVAILABLE = _(
    "That service is no longer offered: it is archived or it does not exist."
)
SERVICE_PRICE_REQUIRED = _(
    "This service has no fixed price: type the amount that is charged."
)
SERVICE_PRICE_FIXED = _("This service has a fixed price: no amount is typed.")
SERVICE_PRICE_OUT_OF_RANGE = _(
    "That amount is outside what the service allows (%(min)s – %(max)s)."
)
QUANTITY_OFF_GRID = _(
    "The quantity does not fit the step of the product (%(step)s %(unit)s)."
)
OPEN_PRICE_PERMISSION = _(
    "Only someone who may sell at an open price can add this line: ask a manager."
)
DEPARTMENT_NOT_FOUND = _(
    "That section is no longer in this business. Reload the list and try again."
)
DEPARTMENT_AMBIGUOUS = _(
    "Several sections match «%(said)s»: %(names)s. Say which one."
)
QUICK_NOTE_NOT_FOUND = _(
    "That quick note is no longer in this business. Reload the list and try again."
)
QUICK_NOTE_AMBIGUOUS = _(
    "Several quick notes match «%(said)s»: %(names)s. Say which one."
)
TAX_CATEGORY_UNKNOWN = _("That tax category does not exist in Taxes.")
METHOD_NOT_AVAILABLE = _("That payment method is not available in this business.")
METHOD_AMBIGUOUS = _(
    "Several payment methods match «%(said)s»: %(names)s. Say which one."
)

#: The settings each method type depends on; «other» is always allowed.
TYPE_SETTING = {
    "cash": "allow_cash",
    "card": "allow_card",
    "transfer": "allow_transfer",
}


# ── The business ─────────────────────────────────────────────────────────────────────────────────


def business_country() -> str:
    """The business's country, from Taxes' one jurisdiction of the business (TAX-F11)."""
    country, _region = business_jurisdiction()
    return country


def actor(ctx: OperationContext) -> str:
    return str(ctx.actor)[:128] if ctx.actor is not None else ""


@operation(
    "sale.business_day.get",
    kind="query",
    permission="sale.view_sale",
    input=EmptyIn,
    output=BusinessDayOut,
    ai={
        "description": "Today's date in the business's time zone (the business day sales are numbered and counted in)."
    },
)
def business_day(ctx: OperationContext, params: EmptyIn) -> dict:
    return {"today": business_today()}


def missing_tax(name: str) -> str:
    """Why an article without a tax category cannot be sold, naming the territory's tax (TAX-F11)."""
    return str(TAX_CATEGORY_MISSING) % {"name": name, "tax": TAX_KIND_NAMES[business_tax_kind()]}


# ── Settings ─────────────────────────────────────────────────────────────────────────────────────

SETTINGS_FIELDS = [
    "allow_cash",
    "allow_card",
    "allow_transfer",
    "show_products",
    "show_services",
    "require_customer",
    "allow_discounts",
    "max_discount_percent",
    "enable_parked_tickets",
    "default_tax_included",
    "auto_invoice_with_tax_id",
    "default_document_type",
    "receipt_header",
    "receipt_footer",
    "receipt_footer_image",
    "receipt_marketing_url",
    "receipt_marketing_text",
]


def current_settings() -> Settings:
    """The business's row, or an unsaved one with the factory values."""
    return Settings.objects.first() or Settings()


def settings_row(settings: Settings) -> dict:
    row = {field: getattr(settings, field) for field in SETTINGS_FIELDS}
    row["updated_at"] = None if settings._state.adding else settings.updated_at
    return row


@operation(
    "sale.settings.get",
    kind="query",
    permission="sale.manage_settings",
    input=EmptyIn,
    output=SettingsOut,
    ai={
        "description": "Read the till settings: payment methods allowed, products and services shown, customer required, "
        "discounts and their cap, parked checks, prices with VAT, default document and the receipt's texts."
    },
)
def get_settings(ctx: OperationContext, params: EmptyIn) -> dict:
    return settings_row(current_settings())


@operation(
    "sale.pos_settings.get",
    kind="query",
    permission="sale.view_sale",
    input=EmptyIn,
    output=SettingsOut,
    ai={
        "description": "Read the till settings the till needs to sell (the same fields, readable by whoever sells)."
    },
)
def get_pos_settings(ctx: OperationContext, params: EmptyIn) -> dict:
    return settings_row(current_settings())


# ── Rows a write names ───────────────────────────────────────────────────────────────────────────


def held(rows: QuerySet) -> list:
    """``rows``, each held until this transaction ends with a key-share lock taken in the same read, for a write
    that names them (an open-price line at a department, a tender of a payment method). The Hub admin's «Delete»
    locks them first (``services.lock_rows``): it waits for this write and then finds what it wrote, so it answers
    «Cannot delete» instead of either of them failing at its COMMIT. A key share is the lock the foreign key itself
    takes at the COMMIT, taken earlier: it only stops a deletion, while another write that names the row (every sale
    names Cash) or changes it (a rename, a deactivation) goes on. One being deleted meanwhile is read once the
    deletion ends: gone, as one deleted before. The ORM has no ``FOR KEY SHARE``: it is appended to the SQL the ORM
    wrote, and the rows still come from the hub's database by the router."""
    sql, params = rows.query.sql_with_params()
    return list(rows.model.objects.raw(f"{sql} FOR KEY SHARE", params))


# ── Payment methods ──────────────────────────────────────────────────────────────────────────────


def method_display_name(name: str) -> str:
    """A factory method's name in the active language (stored canonical English)."""
    label = FACTORY_METHOD_NAMES.get(name)
    return str(label) if label else name


def allowed_types(settings: Settings, methods: Iterable[PaymentMethod]) -> set[str]:
    """The method types the settings let charge; if they leave no active method, every type."""
    allowed = {"other"} | {
        kind for kind, field in TYPE_SETTING.items() if getattr(settings, field)
    }
    if not any(method.type in allowed for method in methods):
        return {"cash", "card", "transfer", "other"}
    return allowed


def payment_method_row(method: PaymentMethod, allowed: set[str]) -> dict:
    return {
        "id": method.id,
        "name": method.name,
        "display_name": method.display_name,
        "type": method.type,
        "sort_order": method.sort_order,
        "requires_change": method.requires_change,
        "allowed": method.type in allowed,
    }


def _said(text: str) -> str:
    return " ".join(text.split()).casefold()


def _names_in_every_language(label) -> set[str]:
    names = set()
    for language, _name in django_settings.LANGUAGES:
        with translation.override(language):
            names.add(_said(str(label)))
    return names


def find_method(method_id: UUID | None, said: str | None) -> PaymentMethod:
    """An active payment method by its id, its name (a factory one in any language) or its type."""
    active = PaymentMethod.objects.filter(is_active=True)
    if method_id is not None:
        method = active.filter(pk=method_id).first()
        if method is None:
            raise Conflict(
                str(METHOD_NOT_AVAILABLE), code="sale.payment_method_not_available"
            )
        return method
    wanted = _said(said or "")
    methods = list(active.order_by("sort_order", "name", "id"))
    by_name = [
        m
        for m in methods
        if _said(m.name) == wanted
        or (
            m.is_system
            and wanted
            in _names_in_every_language(FACTORY_METHOD_NAMES.get(m.name, m.name))
        )
    ]
    if not by_name:
        types = {
            kind
            for kind, label in PaymentMethod.Type.choices
            if wanted == kind or wanted in _names_in_every_language(label)
        }
        by_name = [m for m in methods if m.type in types]
    if not by_name:
        raise Conflict(
            str(METHOD_NOT_AVAILABLE), code="sale.payment_method_not_available"
        )
    if len(by_name) > 1:
        names = ", ".join(m.display_name for m in by_name[:5])
        raise Conflict(
            str(METHOD_AMBIGUOUS) % {"said": said, "names": names},
            code="sale.payment_method_ambiguous",
        )
    return by_name[0]


def held_methods(ids: Iterable[UUID]) -> set[UUID]:
    """The payment methods ``ids`` still there, each held (``held``) in id order until the write that records a
    tender of them ends; a write that names several takes them in the order the admin's «Delete selected» does."""
    ids = set(ids)
    if not ids:
        return set()
    return {method.pk for method in held(PaymentMethod.objects.filter(pk__in=ids).order_by("id"))}


@operation(
    "sale.payment_method.list",
    kind="query",
    permission="sale.view_paymentmethod",
    input=PaymentMethodListIn,
    output=PaymentMethodPage,
    expose_api=True,
    ai={
        "description": "List the active payment methods in the order of the charge sheet, with their type (cash, card, "
        "transfer, other) and whether the till settings let them charge today."
    },
)
def list_payment_methods(ctx: OperationContext, params: PaymentMethodListIn) -> dict:
    with translation.override(ctx.language):
        methods = PaymentMethod.objects.filter(is_active=True).order_by(
            "sort_order", "name", "id"
        )
        allowed = allowed_types(current_settings(), methods)
        if params.search:
            methods = methods.filter(name__icontains=params.search.strip())
        page = methods[params.offset : params.offset + params.limit]
        return {
            "rows": [payment_method_row(method, allowed) for method in page],
            "total": methods.count(),
            "limit": params.limit,
            "offset": params.offset,
        }


# ── Departments and quick notes ──────────────────────────────────────────────────────────────────


def department_row(department: Department, rates: dict) -> dict:
    resolution = rates.get(department.tax_category_id)
    return {
        "id": department.id,
        "name": department.name,
        "tax_category_key": department.tax_category.key,
        "tax_category_name": department.tax_category.display_name,
        "tax_rate_pct": resolution.rate_pct if resolution else None,
        "sort_order": department.sort_order,
    }


def department_rates(departments: list[Department]) -> dict:
    categories = list({d.tax_category_id: d.tax_category for d in departments}.values())
    return current_rates(categories, *business_jurisdiction(), business_today())


def _find_named(
    rows, item_id, said, field: str, *, missing, ambiguous, code: str, lock: bool
):
    rows = rows.filter(is_deleted=False)
    if lock:
        rows = rows.select_for_update()
    if item_id is not None:
        found = rows.filter(pk=item_id).first()
    else:
        exact = list(rows.filter(**{f"{field}__iexact": said.strip()})[:2])
        found_rows = exact or list(
            rows.filter(**{f"{field}__icontains": said.strip()})[:6]
        )
        if len(found_rows) > 1:
            names = ", ".join(getattr(row, field) for row in found_rows[:5])
            raise Conflict(
                str(ambiguous) % {"said": said, "names": names},
                code=f"sale.{code}_ambiguous",
            )
        found = found_rows[0] if found_rows else None
    if found is None:
        raise NotFound(str(missing), code=f"sale.{code}_not_found")
    return found


def find_department(
    department_id: UUID | None, said: str | None, *, lock: bool = False
) -> Department:
    return _find_named(
        Department.objects.select_related("tax_category"),
        department_id,
        said,
        "name",
        missing=DEPARTMENT_NOT_FOUND,
        ambiguous=DEPARTMENT_AMBIGUOUS,
        code="department",
        lock=lock,
    )


def hold_departments(lines: Iterable[tuple[OpenLineFields, OrderLine]]) -> None:
    """Holds the departments of the open-price ``lines`` (each with the input that named it) in id order
    (``held``) until the write that adds them ends; one deleted since it was read is refused as one that never was.
    The business's own «Delete» only retires one (lines keep it), so a retired one is still there to hold."""
    named = {line.department_id: data for data, line in lines if line.department_id is not None}
    if not named:
        return
    kept = {row.pk for row in held(Department.objects.filter(pk__in=named).order_by("id"))}
    for department_id, data in named.items():
        if department_id not in kept:
            raise _department_refused(data, str(DEPARTMENT_NOT_FOUND))


def find_quick_note(
    note_id: UUID | None, said: str | None, *, lock: bool = False
) -> QuickNote:
    return _find_named(
        QuickNote.objects.all(),
        note_id,
        said,
        "text",
        missing=QUICK_NOTE_NOT_FOUND,
        ambiguous=QUICK_NOTE_AMBIGUOUS,
        code="quick_note",
        lock=lock,
    )


def find_tax_category(reference: str, field: str = "tax_category_key") -> TaxCategory:
    """An active tax category by its key, its name or an alias; else a 422 on ``field``."""
    category = category_by_reference(reference)
    if category is None or not category.is_active:
        raise InvalidPayload(
            str(TAX_CATEGORY_UNKNOWN),
            code="invalid_field",
            fields={field: str(TAX_CATEGORY_UNKNOWN)},
        )
    return category


def _ordering(column: str, direction: str, *ties: str) -> list:
    first = F(column).desc() if direction == "desc" else F(column).asc()
    return [first, *ties]


@operation(
    "sale.department.list",
    kind="query",
    permission="sale.view_sale",
    input=DepartmentListIn,
    output=DepartmentPage,
    ai={
        "description": "List the departments of the till's open price, in the order they are shown, with the tax category "
        "each one charges at and its rate today."
    },
)
def list_departments(ctx: OperationContext, params: DepartmentListIn) -> dict:
    with translation.override(ctx.language):
        departments = Department.objects.filter(is_deleted=False).select_related(
            "tax_category"
        )
        if params.search:
            departments = departments.filter(name__icontains=params.search.strip())
        ordered = departments.order_by(
            *_ordering(params.sort, params.dir, "name", "id")
        )
        page = list(ordered[params.offset : params.offset + params.limit])
        rates = department_rates(page)
        return {
            "rows": [department_row(department, rates) for department in page],
            "total": departments.count(),
            "limit": params.limit,
            "offset": params.offset,
        }


def quick_note_row(note: QuickNote) -> dict:
    return {"id": note.id, "text": note.text, "sort_order": note.sort_order}


@operation(
    "sale.quick_note.list",
    kind="query",
    permission="sale.view_sale",
    input=QuickNoteListIn,
    output=QuickNotePage,
    ai={
        "description": "List the quick notes the line-note sheet of the till offers, in the order they are shown."
    },
)
def list_quick_notes(ctx: OperationContext, params: QuickNoteListIn) -> dict:
    notes = QuickNote.objects.filter(is_deleted=False)
    if params.search:
        notes = notes.filter(text__icontains=params.search.strip())
    page = notes.order_by(*_ordering(params.sort, params.dir, "text", "id"))[
        params.offset : params.offset + params.limit
    ]
    return {
        "rows": [quick_note_row(note) for note in page],
        "total": notes.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


# ── Freezing a line ──────────────────────────────────────────────────────────────────────────────


def _inventory(ctx: OperationContext, name: str, data: dict):
    """Runs Inventory's operation ``name`` for the caller; Inventory off or absent → catalog unavailable."""
    try:
        op = get(name)
    except UnknownOperation:
        raise Conflict(
            str(CATALOG_UNAVAILABLE), code="sale.catalog_unavailable"
        ) from None
    try:
        return op(ctx, op.input.model_validate(data))
    except AppInactive:
        raise Conflict(
            str(CATALOG_UNAVAILABLE), code="sale.catalog_unavailable"
        ) from None


def inventory_units(ctx: OperationContext) -> dict:
    """``{code: (factor_num, factor_den, increment)}`` of Inventory's units of measure."""
    page = _inventory(ctx, "inventory.unit.list", {"limit": 100})
    return {
        unit.code: (unit.factor_num, unit.factor_den, Decimal(unit.increment))
        for unit in page.rows
    }


#: What a 409 of an app sale does not require says when that app is not in this business.
UNAVAILABLE = {
    "sale.services_unavailable": SERVICES_UNAVAILABLE,
    "sale.invoice_unavailable": INVOICE_UNAVAILABLE,
    "sale.cash_register_unavailable": CASH_REGISTER_UNAVAILABLE,
    "sale.appointment_unavailable": APPOINTMENT_UNAVAILABLE,
}


def call_app(ctx: OperationContext, name: str, data: dict, unavailable_code: str):
    """Runs the operation ``name`` of an app sale does not require, for the caller (its permission and
    its active-app check apply): the app off or absent (``UnknownOperation``, ``app_inactive``) → 409
    ``unavailable_code``. Its own refusals reach the caller as they are; nested in a write, it runs in a
    savepoint, so a refusal caught by the caller leaves nothing of it behind."""
    unavailable = Conflict(str(UNAVAILABLE[unavailable_code]), code=unavailable_code)
    try:
        op = get(name)
    except UnknownOperation:
        raise unavailable from None
    try:
        payload = op.input.model_validate(data)
    except pydantic.ValidationError as invalid:
        # What the other app does not accept is a 422 of the caller, as a route would answer it.
        fields = {".".join(map(str, error["loc"])): error["msg"] for error in invalid.errors()}
        raise InvalidPayload(
            next(iter(fields.values()), str(invalid)), code="invalid_payload", fields=fields
        ) from None
    try:
        return op(ctx, payload)
    except AppInactive:
        raise unavailable from None


def call_services(ctx: OperationContext, name: str, data: dict):
    """Services' operation ``name`` (``call_app``); off or absent → ``sale.services_unavailable``.

    Its refusals (a voucher spent, a session no longer held…) reach the caller as they are."""
    return call_app(ctx, name, data, "sale.services_unavailable")


def _euros(cents: int | None) -> str:
    return "—" if cents is None else f"{Decimal(cents) / 100:.2f} €"


def _line_price(
    ctx: OperationContext, service, data: ServiceLineFields, booking: "Booking | None"
) -> int:
    if data.booked_price is not None:
        return booked_price(ctx, booking, service.id, data.booked_price)
    price = _service_price(service, data.unit_price)
    if service.pricing_type == "fixed":
        return own_price(ctx, service.id, data.staff_id) or price
    return price


def _service_price(service, unit_price: int | None) -> int:
    """The price a line of ``service`` is charged at: its own when fixed, the amount typed otherwise."""
    if service.pricing_type == "fixed":
        if unit_price is not None:
            message = str(SERVICE_PRICE_FIXED)
            raise Conflict(message, code="sale.service_price_fixed", fields={"unit_price": message})
        return service.price
    if unit_price is None:
        message = str(SERVICE_PRICE_REQUIRED)
        raise Conflict(message, code="sale.service_price_required", fields={"unit_price": message})
    low, high = service.min_price, service.max_price
    if (low is not None and unit_price < low) or (high is not None and unit_price > high):
        message = str(SERVICE_PRICE_OUT_OF_RANGE) % {"min": _euros(low), "max": _euros(high)}
        raise Conflict(
            message, code="sale.service_price_out_of_range", fields={"unit_price": message}
        )
    return unit_price


class Booking:
    """The appointment a check charges (SALE-F26), asked once and by name to Appointments
    (``appointment.appointment.get``, with the seller's session) when a line brings its ``booked_price``.
    ``customer_id``, when the charge knows it, must be the appointment's."""

    UNAVAILABLE = object()

    def __init__(self, appointment_id: UUID | None, customer_id: UUID | None = None):
        self.appointment_id = appointment_id
        self.customer_id = customer_id
        self._read = None

    def read(self, ctx: OperationContext):
        """The appointment; ``None`` when the seller cannot see it (it does not exist, was deleted, is
        another's); ``UNAVAILABLE`` when Appointments cannot be asked (off, absent, not allowed)."""
        if self._read is None:
            try:
                self._read = call_app(
                    ctx,
                    "appointment.appointment.get",
                    {"id": self.appointment_id},
                    "sale.appointment_unavailable",
                )
            except NotFound:
                self._read = False
            except (Conflict, PermissionDenied) as failure:
                if isinstance(failure, Conflict) and failure.code != "sale.appointment_unavailable":
                    raise
                self._read = self.UNAVAILABLE
        return self._read or None


#: An appointment that no longer charges: its booked price is gone with it.
_UNCHARGEABLE = {"cancelled", "no_show"}


def booked_price(
    ctx: OperationContext, booking: "Booking | None", service_id: UUID, price: int
) -> int:
    """``price`` as the line's frozen price when the check's appointment booked that service at it (lower
    only with ``sale.sell_open_price``); without an appointment, or without Appointments to ask, an open
    price (403 without the right). 409 ``sale.booked_price_mismatch`` otherwise."""
    may_open = ctx.has("sale.sell_open_price")
    appointment = (
        booking.read(ctx) if booking and booking.appointment_id else Booking.UNAVAILABLE
    )
    if appointment is Booking.UNAVAILABLE:
        if not may_open:
            raise PermissionDenied(str(OPEN_PRICE_PERMISSION))
        return price
    booked = (
        []
        if appointment is None
        or appointment.status in _UNCHARGEABLE
        or appointment.sale_id is not None
        or (booking.customer_id and appointment.customer_id != booking.customer_id)
        else [line.price for line in appointment.services if line.service_id == service_id]
    )
    if price in booked or (booked and price < max(booked) and may_open):
        return price
    # One the seller cannot see (another professional's, deleted) is said as such: she cannot know why.
    message = str(APPOINTMENT_NOT_VISIBLE if appointment is None else BOOKED_PRICE_MISMATCH)
    raise Conflict(message, code="sale.booked_price_mismatch", fields={"booked_price": message})


def own_price(ctx: OperationContext, service_id: UUID, staff_id: UUID | None) -> int | None:
    """The professional's own price for the service (Services' assignment, SERVICE-F05), as Fresha,
    Phorest and Timely charge it; ``None`` when she has none (or is no professional of Staff)."""
    if staff_id is None:
        return None
    try:
        page = call_services(
            ctx,
            "service.assignment.list",
            {"service_id": service_id, "member_id": staff_id, "limit": 100},
        )
    except NotFound:
        return None
    return next(
        (row.custom_price for row in page.rows if row.is_active and row.custom_price is not None),
        None,
    )


def freeze_service_line(
    ctx: OperationContext, data: ServiceLineFields, booking: Booking | None = None
) -> OrderLine:
    """An unsaved row for a service of Services: its name, price and tax category frozen from it. The
    price: the one the appointment booked (``booked_price``, checked); else, of a fixed-price service,
    the professional's own or the service's; else the amount typed, within the service's range."""
    try:
        service = call_services(
            ctx, "service.service.get", {"id": data.service_id, "service": data.service}
        )
    except NotFound:
        raise Conflict(
            str(SERVICE_NOT_AVAILABLE), code="sale.service_not_available"
        ) from None
    if not service.is_active:
        raise Conflict(str(SERVICE_NOT_AVAILABLE), code="sale.service_not_available")
    if service.needs_tax_setup or not service.tax_category_key:
        raise Conflict(
            missing_tax(service.name),
            code="sale.tax_category_missing",
        )
    check_grid(data.quantity, GRID_FALLBACK, "ud")
    line = OrderLine(
        service_id=service.id,
        name=service.name,
        sku=service.sku,
        is_service=True,
        unit="ud",
        increment=GRID_FALLBACK,
        quantity=data.quantity,
        unit_price=_line_price(ctx, service, data, booking),
        cost=service.cost,
        tax_category_key=service.tax_category_key,
        notes=data.notes,
        staff_id=data.staff_id,
        is_gift=data.is_gift,
        gift_reason=data.gift_reason if data.is_gift else "",
        created_by=actor(ctx),
    )
    line.line_total = provisional_total(line)
    return line


def check_grid(quantity: Decimal, increment: Decimal, unit: str) -> None:
    if increment and quantity % increment != 0:
        message = str(QUANTITY_OFF_GRID) % {
            "step": f"{increment.normalize():f}",
            "unit": unit,
        }
        raise Conflict(
            message, code="sale.quantity_off_grid", fields={"quantity": message}
        )


def provisional_total(line: OrderLine) -> int:
    """What the row paints: its frozen price by its quantity, with its own discount; a comp, 0; a line a
    voucher pays, 0."""
    if line.voucher_session_id is not None:
        return 0
    return pricing.line_amount(
        line.unit_price,
        ratio_of(line),
        line_percent=line.discount_percent,
        is_gift=line.is_gift,
    )


def ratio_of(line: OrderLine | object):
    return pricing.price_ratio(
        line.quantity,
        (line.unit_factor_num, line.unit_factor_den),
        (line.pricing_factor_num, line.pricing_factor_den),
        line.price_quantity,
    )


def freeze_product_line(
    ctx: OperationContext, data: ProductLineIn, units: dict | None = None
) -> OrderLine:
    """An unsaved row for a product of Inventory: its price, unit and category frozen from the catalog."""
    try:
        product = _inventory(
            ctx,
            "inventory.product.get",
            {"id": data.product_id, "product": data.product},
        )
    except NotFound:
        raise Conflict(
            str(PRODUCT_NOT_AVAILABLE), code="sale.product_not_available"
        ) from None
    if not product.is_active:
        raise Conflict(str(PRODUCT_NOT_AVAILABLE), code="sale.product_not_available")
    if product.needs_tax_setup or not product.tax_category_key:
        raise Conflict(
            missing_tax(product.name),
            code="sale.tax_category_missing",
        )
    units = units if units is not None else inventory_units(ctx)
    unit = units[product.unit]
    priced_in = units[product.pricing_unit]
    check_grid(data.quantity, unit[2], product.unit)
    line = OrderLine(
        product_id=product.id,
        name=product.name,
        sku=product.sku,
        is_service=product.product_type == "service",
        category_id=product.category_ids[0] if product.category_ids else None,
        unit=product.unit,
        unit_factor_num=unit[0],
        unit_factor_den=unit[1],
        increment=unit[2],
        price_quantity=product.price_quantity,
        pricing_unit=product.pricing_unit,
        pricing_factor_num=priced_in[0],
        pricing_factor_den=priced_in[1],
        quantity=data.quantity,
        unit_price=product.price,
        cost=product.cost,
        tax_category_key=product.tax_category_key,
        notes=data.notes,
        staff_id=data.staff_id,
        is_gift=data.is_gift,
        gift_reason=data.gift_reason if data.is_gift else "",
        created_by=actor(ctx),
    )
    line.line_total = provisional_total(line)
    return line


def _department_refused(data: OpenLineFields, message: str) -> InvalidPayload:
    """The 422 of an open-price line whose department is not there, on the field that named it."""
    field = "department_id" if data.department_id is not None else "department"
    return InvalidPayload(message, code="invalid_field", fields={field: message})


def freeze_open_line(ctx: OperationContext, data: OpenLineFields) -> OrderLine:
    """An unsaved open-price row: the amount typed, the department's (or a category's) VAT."""
    if not ctx.has("sale.sell_open_price"):
        raise PermissionDenied(str(OPEN_PRICE_PERMISSION))
    department = None
    if data.department_id is not None or data.department is not None:
        try:
            department = find_department(data.department_id, data.department)
        except NotFound as missing:
            raise _department_refused(data, missing.message) from None
        category = department.tax_category
    else:
        category = find_tax_category(data.tax_category_key)
    with translation.override(ctx.language):
        name = data.name or (department.name if department else category.display_name)
    check_grid(data.quantity, GRID_FALLBACK, "ud")
    line = OrderLine(
        department=department,
        name=name,
        unit="ud",
        increment=GRID_FALLBACK,
        quantity=data.quantity,
        unit_price=data.unit_price,
        tax_category_key=category.key,
        notes=data.notes,
        staff_id=data.staff_id,
        is_gift=data.is_gift,
        gift_reason=data.gift_reason if data.is_gift else "",
        created_by=actor(ctx),
    )
    line.line_total = provisional_total(line)
    return line


# ── Open checks ──────────────────────────────────────────────────────────────────────────────────


def find_order(order_id: UUID, *, lock: bool = False) -> Order:
    orders = Order.objects.select_for_update() if lock else Order.objects.all()
    order = orders.filter(pk=order_id).first()
    if order is None:
        raise NotFound(str(ORDER_NOT_FOUND), code="sale.order_not_found")
    return order


def pending_lines(order: Order) -> list[OrderLine]:
    """The lines left to charge, in order."""
    return list(order.lines.live().unpaid().order_by("position", "id"))


def order_line_row(line: OrderLine) -> dict:
    return {
        "id": line.id,
        "position": line.position,
        "product_id": line.product_id,
        "department_id": line.department_id,
        "name": line.name,
        "sku": line.sku,
        "is_service": line.is_service,
        "unit": line.unit,
        "quantity": line.quantity,
        "unit_price": line.unit_price,
        "price_quantity": line.price_quantity,
        "pricing_unit": line.pricing_unit,
        "tax_category_key": line.tax_category_key,
        "discount_percent": line.discount_percent,
        "discount_approved": bool(line.discount_approved_by),
        "is_gift": line.is_gift,
        "gift_reason": line.gift_reason,
        "notes": line.notes,
        "staff_id": line.staff_id,
        "service_id": line.service_id,
        "paid_by_voucher": line.paid_by_voucher,
        "voucher_session_id": line.voucher_session_id,
        "voucher_grant_id": line.voucher_grant_id,
        "voucher_name": line.voucher_name,
        "voucher_remaining": line.voucher_remaining,
        "voucher_hold_until": line.voucher_hold_until,
        "line_total": line.line_total,
        "round_no": line.round_no,
        "fired_at": line.fired_at,
    }


def order_detail(order: Order) -> dict:
    lines = pending_lines(order)
    return {
        "id": order.id,
        "status": order.status,
        "label": order.label,
        "notes": order.notes,
        "appointment_id": order.appointment_id,
        "discount_percent": order.discount_percent,
        "discount_amount": order.discount_amount,
        "discount_approved": bool(order.discount_approved_by),
        "provisional_total": order.provisional_total,
        "version": order.version,
        "lines_count": len(lines),
        "created_at": order.created_at,
        "updated_at": order.updated_at,
        "lines": [order_line_row(line) for line in lines],
    }


@operation(
    "sale.order.get",
    kind="query",
    permission="sale.view_sale",
    input=OrderRefIn,
    output=OrderOut,
    expose_api=True,
    ai={
        "description": "Get an open check with the lines left to charge (each with its frozen price, quantity, discount, comp, "
        "note, professional and kitchen round), its ticket discount and its provisional total."
    },
)
def get_order(ctx: OperationContext, params: OrderRefIn) -> dict:
    return order_detail(find_order(params.order_id))


@operation(
    "sale.order.list",
    kind="query",
    permission="sale.view_sale",
    input=OrderListIn,
    output=OrderPage,
    expose_api=True,
    ai={
        "description": "List the open checks of the business (or of another status), newest first, with their title and total."
    },
)
def list_orders(ctx: OperationContext, params: OrderListIn) -> dict:
    orders = Order.objects.annotate(
        pending=Count(
            "lines", filter=Q(lines__removed_at__isnull=True, lines__sale__isnull=True)
        )
    )
    if params.status:
        orders = orders.filter(status=params.status)
    if params.search:
        orders = orders.filter(label__icontains=params.search.strip())
    page = orders.order_by("-created_at", "-id")[
        params.offset : params.offset + params.limit
    ]
    rows = [
        {
            "id": order.id,
            "status": order.status,
            "label": order.label,
            "provisional_total": order.provisional_total,
            "lines_count": order.pending,
            "appointment_id": order.appointment_id,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }
        for order in page
    ]
    return {
        "rows": rows,
        "total": orders.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


# ── The valuation of a charge ────────────────────────────────────────────────────────────────────


def lines_to_charge(order: Order, line_ids: list[UUID]) -> tuple[list[OrderLine], bool]:
    """``(lines, closes)``: the lines named (all that are left when none is) and whether the charge
    takes the last of them. A line named that is gone (removed, voided, charged, of another check)
    means the check changed under the screen."""
    pending = pending_lines(order)
    if not line_ids:
        return pending, True
    wanted = set(line_ids)
    chosen = [line for line in pending if line.id in wanted]
    if len(chosen) != len(wanted):
        raise Conflict(str(ORDER_CHANGED), code="sale.order_changed")
    return chosen, len(chosen) == len(pending)


def valuate(
    lines: list[OrderLine],
    *,
    discount_percent: Decimal,
    discount_amount: int,
    tax_included: bool,
    on: dt.date | None = None,
) -> pricing.Valuation:
    return pricing.value(
        [
            pricing.LineIn(
                key=index,
                unit_price=line.unit_price,
                ratio=ratio_of(line),
                tax_category_key=line.tax_category_key,
                line_percent=line.discount_percent,
                is_gift=line.is_gift,
                covered=line.voucher_session_id is not None,
                cost=line.cost,
                quantity=line.quantity,
                name=line.name,
            )
            for index, line in enumerate(lines)
        ],
        tax_included=tax_included,
        close=pricing.tax_closer(on),
        ticket_percent=discount_percent,
        ticket_amount=discount_amount,
    )


def breakdown_rows(breakdown: list[dict]) -> list[dict]:
    """The valuation's breakdown as a sale keeps it: one row per fiscal key and component."""
    return [
        {
            "rate_pct": row["rate_pct"],
            "label": row["label"],
            "tax_type": str(row["tax_type"]),
            "regime": str(row["regime"]),
            "qualification": str(row["qualification"]),
            "exempt_reason": str(row["exempt_reason"]),
            "base": row["base"],
            "tax": row["tax"],
        }
        for row in breakdown
    ]


def operation_total(order: Order | None, closes: bool, valuation: pricing.Valuation, *, on: dt.date | None = None) -> int:
    """The whole operation the cash limit looks at (Ley 7/2012, art. 7.Uno.1, second paragraph: the
    payments a supply is split into add up). A check charged in parts is one operation: what it already
    charged (voided sales aside) plus all it has left, valued as the charge that would close it. A
    counter sale, or a charge that closes the check, adds its own total to what was charged before."""
    if order is None:
        return valuation.total
    charged = (
        Sale.objects.filter(order=order, status__in=[Sale.Status.COMPLETED, Sale.Status.REFUNDED])
        .aggregate(total=Sum("total"))["total"]
        or 0
    )
    if closes:
        return charged + valuation.total
    rest = valuate(
        pending_lines(order),
        discount_percent=order.discount_percent,
        discount_amount=order.discount_amount,
        tax_included=current_settings().default_tax_included,
        on=on,
    )
    return charged + rest.total


def loose_lines(
    ctx: OperationContext,
    lines: list,
    open_lines: list,
    service_lines: list = (),
    booking: Booking | None = None,
    *,
    hold: bool = False,
) -> list[OrderLine]:
    """Unsaved rows for a counter sale: catalog lines frozen from Inventory, services from Services (at the
    price ``booking`` booked, when a line brings it), then open-price ones. A write that adds them ``hold``s the
    departments of the open-price ones (``hold_departments``)."""
    frozen: list[OrderLine] = []
    if lines:
        units = inventory_units(ctx)
        frozen += [freeze_product_line(ctx, line, units) for line in lines]
    frozen += [freeze_service_line(ctx, line, booking) for line in service_lines]
    priced = [freeze_open_line(ctx, line) for line in open_lines]
    if hold:
        hold_departments(zip(open_lines, priced, strict=True))
    frozen += priced
    for position, line in enumerate(frozen, start=1):
        line.position = position
    return frozen


@operation(
    "sale.checkout.preview",
    kind="query",
    permission="sale.view_sale",
    input=PreviewIn,
    output=PreviewOut,
    ai={
        "description": "Value a charge WITHOUT charging nor writing anything: an open check (all of it, or some lines) or loose "
        "lines. Same arithmetic as the charge: total, taxable base, tax by rate, discounts and comps in cents, and each line."
    },
)
def preview(ctx: OperationContext, params: PreviewIn) -> dict:
    settings = current_settings()
    order = None
    closes = True
    if params.order_id is not None:
        order = find_order(params.order_id)
        if order.status != Order.Status.OPEN:
            raise Conflict(str(ORDER_CHANGED), code="sale.order_changed")
        lines, closes = lines_to_charge(order, params.line_ids)
        percent, amount = order.discount_percent, order.discount_amount if closes else 0
        version = order.version
    else:
        lines = loose_lines(ctx, params.lines, params.open_lines, params.service_lines)
        percent, amount, version = params.discount_percent, params.discount_amount, None
    valuation = valuate(
        lines,
        discount_percent=percent,
        discount_amount=amount,
        tax_included=settings.default_tax_included,
    )
    country = business_country()
    return {
        "order_id": params.order_id,
        "order_version": version,
        "lines_count": len(lines),
        "tax_included": settings.default_tax_included,
        "subtotal": valuation.subtotal,
        "tax_total": valuation.tax_total,
        "discount_amount": valuation.discount_amount,
        "discount_percent": percent,
        "ticket_discount_amount": amount,
        "gift_total": valuation.gift_total,
        "total": valuation.total,
        "breakdown": breakdown_rows(valuation.breakdown),
        "lines": [
            {
                "order_line_id": line.id if line.pk and params.order_id else None,
                "name": line.name,
                "quantity": line.quantity,
                "unit": line.unit,
                "unit_price": line.unit_price,
                "discount_percent": line.discount_percent,
                "is_gift": line.is_gift,
                "service_id": line.service_id,
                "paid_by_voucher": line.paid_by_voucher,
                "voucher_name": line.voucher_name,
                "voucher_remaining": line.voucher_remaining,
                "tax_category_key": line.tax_category_key,
                "tax_rate": out.tax_rate,
                "net_amount": out.net_amount,
                "tax_amount": out.tax_amount,
                "line_total": out.line_total,
            }
            for line, out in zip(lines, valuation.lines, strict=True)
        ],
        "operation_total": operation_total(order, closes, valuation),
        "cash_limit": CASH_LIMIT.get(country),
        "ticket_limit": TICKET_LIMIT.get(country),
    }


# ── Sales ────────────────────────────────────────────────────────────────────────────────────────


def find_sale(sale_id: UUID | None, number: str | None, *, lock: bool = False) -> Sale:
    sales = Sale.objects.select_for_update() if lock else Sale.objects.all()
    sale = (
        sales.filter(pk=sale_id).first()
        if sale_id is not None
        else sales.filter(number=(number or "").strip()).first()
    )
    if sale is None:
        raise NotFound(str(SALE_NOT_FOUND), code="sale.sale_not_found")
    return sale


def returned_by_line(sale: Sale) -> dict[UUID, Decimal]:
    totals = (
        RefundLine.objects.filter(sale_line__sale=sale)
        .values("sale_line_id")
        .annotate(q=Sum("quantity"))
    )
    return {row["sale_line_id"]: row["q"] for row in totals}


def sale_line_row(line: SaleLine, returned: Decimal) -> dict:
    return {
        "id": line.id,
        "position": line.position,
        "order_line_id": line.order_line_id,
        "product_id": line.product_id,
        "department_id": line.department_id,
        "name": line.name,
        "sku": line.sku,
        "is_service": line.is_service,
        "unit": line.unit,
        "quantity": line.quantity,
        "unit_price": line.unit_price,
        "price_quantity": line.price_quantity,
        "pricing_unit": line.pricing_unit,
        "discount_percent": line.discount_percent,
        "is_gift": line.is_gift,
        "gift_reason": line.gift_reason,
        "notes": line.notes,
        "staff_id": line.staff_id,
        "service_id": line.service_id,
        "paid_by_voucher": line.paid_by_voucher,
        "voucher_name": line.voucher_name,
        "tax_category_key": line.tax_category_key,
        "tax_rate": line.tax_rate,
        "tax_country_code": line.tax_country_code,
        "tax_region_code": line.tax_region_code,
        "tax_rule_id": line.tax_rule_id,
        "net_amount": line.net_amount,
        "tax_amount": line.tax_amount,
        "line_total": line.line_total,
        "returned_quantity": returned,
    }


def sessions_to_return(sale: Sale) -> int:
    """Lines of ``sale`` paid with a voucher whose session has not come back (a refund returns a line of
    one unit whole)."""
    return sale.lines.filter(
        voucher_session_id__isnull=False, refunds__isnull=True
    ).count()


def documents_pending(sale: Sale) -> bool:
    """A fiscal document of ``sale`` waits: its own, its void's or one of its refunds'."""
    return (
        FiscalStatus.PENDING in (sale.invoice_status, sale.void_invoice_status)
        or sale.refunds.filter(invoice_status=FiscalStatus.PENDING).exists()
    )


def sale_detail(sale: Sale, *, already: bool = False) -> dict:
    returned = returned_by_line(sale)
    return {
        "id": sale.id,
        "number": sale.number,
        "business_day": sale.business_day,
        "status": sale.status,
        "document_type": sale.document_type,
        "order_id": sale.order_id,
        "customer_id": sale.customer_id,
        "customer_name": sale.customer_name,
        "staff_id": sale.staff_id,
        "appointment_id": sale.appointment_id,
        "tax_included": sale.tax_included,
        "currency": sale.currency,
        "subtotal": sale.subtotal,
        "tax_total": sale.tax_total,
        "discount_percent": sale.discount_percent,
        "discount_amount": sale.discount_amount,
        "gift_total": sale.gift_total,
        "total": sale.total,
        "tendered_total": sale.tendered_total,
        "change_total": sale.change_total,
        "refunded_total": sale.refunded_total,
        "refundable_total": sale.refundable_total,
        "sessions_to_return": sessions_to_return(sale)
        if sale.status == Sale.Status.COMPLETED
        else 0,
        "payment_method_name": method_display_name(sale.payment_method_name),
        "breakdown": sale.tax_breakdown,
        "notes": sale.notes,
        "voided_at": sale.voided_at,
        "voided_by": sale.voided_by,
        "void_reason": sale.void_reason,
        "invoice_status": sale.invoice_status,
        "invoice_id": sale.invoice_id,
        "invoice_number": sale.invoice_number,
        "invoice_type": sale.invoice_type,
        "void_invoice_status": sale.void_invoice_status,
        "void_invoice_number": sale.void_invoice_number,
        "documents_pending": documents_pending(sale),
        "created_at": sale.created_at,
        "created_by": sale.created_by,
        "lines": [
            sale_line_row(line, returned.get(line.id, Decimal(0)))
            for line in sale.lines.order_by("position", "id")
        ],
        "payments": [
            {
                "id": payment.id,
                "position": payment.position,
                "method_id": payment.method_id,
                "method_name": method_display_name(payment.method_name),
                "method_type": payment.method_type,
                "amount": payment.amount,
                "tendered": payment.tendered,
                "change": payment.change,
                "reference": payment.reference,
            }
            for payment in sale.payments.order_by("position", "id")
        ],
        "already": already,
    }


@operation(
    "sale.sale.get",
    kind="query",
    permission="sale.view_sale",
    input=SaleRefIn,
    output=SaleOut,
    expose_api=True,
    ai={
        "description": "Get a sale by its id or its number (e.g. 20261014-0007): header, lines with their VAT, tenders with "
        "tendered and change, the tax breakdown, what was refunded and, if voided, why."
    },
)
def get_sale(ctx: OperationContext, params: SaleRefIn) -> dict:
    with translation.override(ctx.language):
        return sale_detail(find_sale(params.sale_id, params.sale))


@operation(
    "sale.sale.by_idempotency_key",
    kind="query",
    permission="sale.view_sale",
    input=SaleByKeyIn,
    output=SaleByKeyOut,
    ai={
        "description": "Find the sale recorded with a charge attempt's key: a charge whose answer was lost resolves to the "
        "very sale it created instead of a second one."
    },
)
def sale_by_key(ctx: OperationContext, params: SaleByKeyIn) -> dict:
    sale = Sale.objects.filter(idempotency_key=params.idempotency_key).first()
    with translation.override(ctx.language):
        return {"found": sale is not None, "sale": sale_detail(sale) if sale else None}


_SALE_SORT = {"number": ("business_day", "sequence"), "created_at": ("created_at",)}


def sale_row(sale: Sale) -> dict:
    return {
        "id": sale.id,
        "number": sale.number,
        "business_day": sale.business_day,
        "created_at": sale.created_at,
        "status": sale.status,
        "document_type": sale.document_type,
        "customer_id": sale.customer_id,
        "customer_name": sale.customer_name,
        "payment_method_name": method_display_name(sale.payment_method_name),
        "staff_id": sale.staff_id,
        "total": sale.total,
        "tax_total": sale.tax_total,
        "refunded_total": sale.refunded_total,
        "refundable_total": sale.refundable_total,
        "sessions_to_return": sale.voucher_lines_left
        if sale.status == Sale.Status.COMPLETED
        else 0,
        "has_refunds": sale.has_refunds,
        "invoice_status": sale.invoice_status,
        "documents_pending": FiscalStatus.PENDING in (sale.invoice_status, sale.void_invoice_status)
        or sale.refunds_pending,
    }


@operation(
    "sale.sale.list",
    kind="query",
    permission="sale.view_sale",
    input=SaleListIn,
    output=SalePage,
    expose_api=True,
    ai={
        "description": "List the sales, newest first: search by number or customer; filter by status (completed, voided, "
        "refunded), main payment method, customer, professional, business days (inclusive) and total in cents."
    },
)
def list_sales(ctx: OperationContext, params: SaleListIn) -> dict:
    sales = Sale.objects.annotate(
        voucher_lines_left=Count(
            "lines",
            filter=Q(
                lines__voucher_session_id__isnull=False, lines__refunds__isnull=True
            ),
        ),
        has_refunds=Exists(Refund.objects.filter(sale=OuterRef("pk"))),
        refunds_pending=Exists(
            Refund.objects.filter(sale=OuterRef("pk"), invoice_status=FiscalStatus.PENDING)
        ),
    )
    if params.search:
        text = params.search.strip()
        sales = sales.filter(
            Q(number__icontains=text) | Q(customer_name__icontains=text)
        )
    exact = {
        "status": params.status,
        "payment_method_name": params.payment_method_name,
        "customer_id": params.customer_id,
        "staff_id": params.staff_id,
        "business_day__gte": params.date_from,
        "business_day__lte": params.date_to,
        "total__gte": params.total_min,
        "total__lte": params.total_max,
    }
    sales = sales.filter(
        **{key: value for key, value in exact.items() if value is not None}
    )
    if params.customer_name:
        sales = sales.filter(customer_name__icontains=params.customer_name.strip())
    if params.number:
        sales = sales.filter(number__icontains=params.number.strip())
    columns = _SALE_SORT.get(params.sort, (params.sort,))
    order = [
        F(column).desc() if params.dir == "desc" else F(column).asc()
        for column in columns
    ]
    page = sales.order_by(*order, "-id" if params.dir == "desc" else "id")[
        params.offset : params.offset + params.limit
    ]
    with translation.override(ctx.language):
        rows = [sale_row(sale) for sale in page]
    return {
        "rows": rows,
        "total": sales.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


# ── Figures ──────────────────────────────────────────────────────────────────────────────────────

#: A voided sale is no revenue; one refunded (in part or in full) is, minus what went back.
COUNTED = [Sale.Status.COMPLETED, Sale.Status.REFUNDED]


def _period(sales, period: PeriodIn):
    if period.date_from:
        sales = sales.filter(business_day__gte=period.date_from)
    if period.date_to:
        sales = sales.filter(business_day__lte=period.date_to)
    return sales


def declared_tax_kind(sales) -> str | None:
    """The tax ``sales`` were declared with (the ``tax_type`` of their breakdown rows), what their tax figure
    is named by (SALE-F28): the one family a territory declares (VAT, IGIC, IPSI) when they all share it;
    ``None`` for a mix — a change of territory in the period — or a tax of no territory (the equivalence
    surcharge, another country's). Without any row, the business territory's, what it would declare now."""
    elements = Func(F("tax_breakdown"), function="jsonb_array_elements", output_field=JSONField())
    declared = (
        sales.order_by()
        .annotate(family=KeyTextTransform("tax_type", elements))
        .values_list("family", flat=True)
        .distinct()
    )
    families = set(declared[:2])
    if not families:
        return business_tax_kind()
    if len(families) > 1:
        return None
    family = families.pop()
    return family if family in TAX_KIND_NAMES else None


@operation(
    "sale.sale.stats",
    kind="query",
    permission="sale.view_reports",
    input=PeriodIn,
    output=StatsOut,
    ai={
        "description": "Sales figures of a period of business days (inclusive; empty = all): tickets, revenue (refunds taken "
        "off), average ticket, taxable base, tax, discounts, refunds and voided sales, in cents; and the tax the "
        "sales were declared with (VAT, IGIC, IPSI; empty when they mix taxes)."
    },
)
def stats(ctx: OperationContext, params: PeriodIn) -> dict:
    sales = _period(Sale.objects.all(), params)
    zero = 0
    charged = sales.filter(status__in=COUNTED)
    counted = charged.aggregate(
        count=Count("id"),
        gross=Coalesce(Sum("total"), zero),
        refunded=Coalesce(Sum("refunded_total"), zero),
        net=Coalesce(Sum("subtotal"), zero),
        tax=Coalesce(Sum("tax_total"), zero),
        discounts=Coalesce(Sum("discount_amount"), zero),
    )
    revenue = counted["gross"] - counted["refunded"]
    count = counted["count"]
    return {
        "count": count,
        "total_revenue": revenue,
        "avg_ticket": pricing.half_up(Fraction(revenue, count)) if count else 0,
        "net_total": counted["net"],
        "tax_total": counted["tax"],
        "discount_total": counted["discounts"],
        "refunded_total": counted["refunded"],
        "voided_count": sales.filter(status=Sale.Status.VOIDED).count(),
        "tax_kind": declared_tax_kind(charged),
    }


def _revenue_by_day(first: dt.date, last: dt.date) -> dict[dt.date, int]:
    rows = (
        Sale.objects.filter(
            status__in=COUNTED, business_day__gte=first, business_day__lte=last
        )
        .values("business_day")
        .annotate(total=Sum(F("total") - F("refunded_total")))
    )
    return {row["business_day"]: row["total"] for row in rows}


@operation(
    "sale.sale.today",
    kind="query",
    permission="sale.view_reports",
    input=EmptyIn,
    output=TodayOut,
    ai={
        "description": "What was sold today (business day) in cents, refunds taken off, and how many tickets."
    },
)
def today(ctx: OperationContext, params: EmptyIn) -> dict:
    day = business_today()
    sales = Sale.objects.filter(status__in=COUNTED, business_day=day)
    return {
        "day": day,
        "total": _revenue_by_day(day, day).get(day, 0),
        "tickets": sales.count(),
    }


@operation(
    "sale.sale.last_7_days",
    kind="query",
    permission="sale.view_reports",
    input=EmptyIn,
    output=LastDaysOut,
    ai={
        "description": "What was sold each of the last seven business days, today included, oldest first, 0 on a day without sales."
    },
)
def last_7_days(ctx: OperationContext, params: EmptyIn) -> dict:
    last = business_today()
    first = last - dt.timedelta(days=6)
    totals = _revenue_by_day(first, last)
    days = [first + dt.timedelta(days=offset) for offset in range(7)]
    return {"rows": [{"day": day, "total": totals.get(day, 0)} for day in days]}


@operation(
    "sale.sale.by_staff",
    kind="query",
    permission="sale.view_reports",
    input=PeriodIn,
    output=ByStaffOut,
    expose_api=True,
    ai={
        "description": "What each professional sold in a period of business days: their lines (a line's own professional wins "
        "over the sale's), the sales they served, gross, base and tax in cents. For the per-professional close."
    },
)
def by_staff(ctx: OperationContext, params: PeriodIn) -> dict:
    lines = SaleLine.objects.filter(sale__status__in=COUNTED)
    if params.date_from:
        lines = lines.filter(sale__business_day__gte=params.date_from)
    if params.date_to:
        lines = lines.filter(sale__business_day__lte=params.date_to)
    rows = (
        lines.annotate(served_by=Coalesce("staff_id", "sale__staff_id"))
        .filter(served_by__isnull=False)
        .values("served_by")
        .annotate(
            sales_count=Count("sale", distinct=True),
            gross=Sum("line_total"),
            net=Sum("net_amount"),
        )
        .order_by("-gross", "served_by")
    )
    return {
        "rows": [
            {
                "staff_id": row["served_by"],
                "sales_count": row["sales_count"],
                "gross_total": row["gross"],
                "net_total": row["net"],
                "tax_total": row["gross"] - row["net"],
            }
            for row in rows
        ]
    }


# ── Refunds ──────────────────────────────────────────────────────────────────────────────────────


def tender_options(sale: Sale) -> list[dict]:
    """One row per tender of ``sale``, always: what it charged, gave back and has left, and whether
    the money can go back through its own method."""
    rows = []
    for payment in sale.payments.select_related("method").order_by("position", "id"):
        refunded = payment.refunds.aggregate(total=Coalesce(Sum("amount"), 0))["total"]
        remaining = payment.amount - refunded
        if remaining <= 0:
            refundable, reason = False, "already_refunded"
        elif not payment.method.is_active:
            refundable, reason = False, "method_unavailable"
        else:
            refundable, reason = True, ""
        rows.append(
            {
                "payment_id": payment.id,
                "position": payment.position,
                "method_id": payment.method_id,
                "method_name": method_display_name(payment.method_name),
                "method_type": payment.method_type,
                "charged": payment.amount,
                "refunded": refunded,
                "remaining": remaining,
                "refundable": refundable,
                "reason": reason,
            }
        )
    return rows


@operation(
    "sale.refund.options",
    kind="query",
    permission="sale.view_sale",
    input=SaleRefIn,
    output=RefundOptionsOut,
    expose_api=True,
    ai={
        "description": "What a sale can still give back: for each tender, what it charged, what it already returned, what is "
        "left and whether it can go back through its own method; for each line, the units already returned and left."
    },
)
def refund_options(ctx: OperationContext, params: SaleRefIn) -> dict:
    sale = find_sale(params.sale_id, params.sale)
    returned = returned_by_line(sale)
    with translation.override(ctx.language):
        return {
            "sale_id": sale.id,
            "number": sale.number,
            "status": sale.status,
            "total": sale.total,
            "refunded_total": sale.refunded_total,
            "refundable_total": sale.refundable_total,
            "tenders": tender_options(sale),
            "lines": [
                {
                    "line_id": line.id,
                    "name": line.name,
                    "unit": line.unit,
                    "quantity": line.quantity,
                    "returned": returned.get(line.id, Decimal(0)),
                    "left": line.quantity - returned.get(line.id, Decimal(0)),
                    "line_total": line.line_total,
                    "is_gift": line.is_gift,
                    "paid_by_voucher": line.paid_by_voucher,
                    "voucher_name": line.voucher_name,
                }
                for line in sale.lines.order_by("position", "id")
            ],
        }


def refund_row(refund: Refund) -> dict:
    return {
        "id": refund.id,
        "sale_id": refund.sale_id,
        "total": refund.total,
        "reason": refund.reason,
        "note": refund.note,
        "created_at": refund.created_at,
        "created_by": refund.created_by,
        "invoice_status": refund.invoice_status,
        "invoice_number": refund.invoice_number,
        "invoice_type": refund.invoice_type,
    }


@operation(
    "sale.refund.list",
    kind="query",
    permission="sale.view_sale",
    input=SaleRefIn,
    output=RefundListOut,
    expose_api=True,
    ai={
        "description": "List the refunds of a sale, newest first, with their amount, reason and who made them."
    },
)
def list_refunds(ctx: OperationContext, params: SaleRefIn) -> dict:
    sale = find_sale(params.sale_id, params.sale)
    return {
        "rows": [
            refund_row(refund) for refund in sale.refunds.order_by("-created_at", "-id")
        ]
    }


@operation(
    "sale.refund.by_idempotency_key",
    kind="query",
    permission="sale.view_sale",
    input=RefundByKeyIn,
    output=RefundByKeyOut,
    expose_api=True,
    ai={
        "description": "Find the refund recorded with a refund attempt's key, so a retry recovers it instead of refunding twice."
    },
)
def refund_by_key(ctx: OperationContext, params: RefundByKeyIn) -> dict:
    refund = Refund.objects.filter(idempotency_key=params.idempotency_key).first()
    return {
        "found": refund is not None,
        "refund": refund_row(refund) if refund else None,
    }
