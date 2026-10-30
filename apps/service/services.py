"""Write operations of the service app: one operation = one transaction, with its events in the outbox.

Every check runs before the first write, so a refusal leaves no trace. Writes on a voucher sold (spend,
void, adjust) lock its row first and read its balance again afterwards: two tills on the same voucher
go one after the other and the second decides on what the first left. Writes on the services a
professional performs lock the professional's record first, so two of them never fight over the
«main service». A name two writes take at once ends in the database's unique constraint, translated
to the same 409 as the check. A write that names a row (a tax category, a category, a service, a voucher
of the catalog, a customer's card) holds it until it commits: its deletion waits for the write instead of
breaking it at the COMMIT, and one deleted meanwhile is refused as one deleted before.
"""

import datetime as dt

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.customer.models import Customer
from apps.customer.queries import find_customer
from apps.service import events
from apps.service.models import (
    ACTOR_MAX_LENGTH,
    CATEGORY_CYCLE,
    CATEGORY_LOOP,
    Assignment,
    Category,
    Grant,
    GrantAdjustment,
    Package,
    PackageItem,
    Redemption,
    Service,
    ServiceSettings,
    parent_problem,
)
from apps.service.queries import (
    PACKAGE_NOT_FOUND,
    balance,
    current_settings,
    find_category,
    find_grant,
    find_package,
    find_service,
    grants,
    held_rows,
    load_assignment,
    load_category,
    load_grant,
    load_package,
    load_service,
    lock_grant,
    redeem_refusal,
    settings_row,
    void_refusal,
)
from apps.service.schemas import (
    PRICE_RANGE_UPSIDE_DOWN,
    SERVICE_REPEATED,
    AdjustIn,
    ForgetCustomerIn,
    ForgottenOut,
    AssignIn,
    AssignmentOut,
    AssignmentPatchIn,
    ByIdIn,
    CategoryIn,
    CategoryOut,
    CategoryPatchIn,
    CategoryRefIn,
    DeletedOut,
    ExpiredOut,
    GrantIn,
    GrantOut,
    HoldIn,
    MemberReleaseIn,
    PackageIn,
    PackageOut,
    PackagePatchIn,
    PackageRefIn,
    ReassignedOut,
    ReassignIn,
    RedeemIn,
    RedemptionOut,
    ReleasedOut,
    ReturnIn,
    ServiceBulkIn,
    ServiceIn,
    ServiceImageIn,
    ServiceImageUploadIn,
    ServiceOut,
    ServicePatchIn,
    ServiceRefIn,
    ServicesOut,
    SessionOut,
    SessionRefIn,
    SessionsOut,
    SettingsIn,
    SettingsOut,
    SettleIn,
    NoIn,
    VoidIn,
)
from apps.staff.models import Member
from apps.staff.queries import resolve_member
from apps.tax.models import TaxCategory
from apps.tax.queries import held_categories
from base import images

TAX_REQUIRED = _("Pick a tax category: without one the service cannot be charged.")
TAX_UNKNOWN = _("That tax category does not exist in Taxes or is deactivated.")
CATEGORY_UNAVAILABLE = _(
    "That category is not available: it does not exist in this business or it has been deleted."
)
PARENT_UNAVAILABLE = _(
    "That parent category is not available: it does not exist in this business or it has been deleted."
)
CATEGORY_NAME_TAKEN = _(
    "There is already a category with that name. Pick another name."
)
PACKAGE_NAME_TAKEN = _("There is already a package with that name. Pick another name.")
LINE_SERVICE_MISSING = _("That service does not exist in this business.")
LINE_SERVICE_ARCHIVED = _("That service is archived: it cannot go into a voucher.")
BULK_INVALID = _("Some services cannot be created: nothing was created.")
ASSIGNMENT_NOT_FOUND = _("That assignment does not exist in this business.")
GRANT_ALREADY_VOIDED = _("That voucher was already voided.")
GRANT_IN_USE = _("That voucher was already used: it cannot be voided.")
GRANT_UNLIMITED = _(
    "That voucher has no session limit: there are no sessions to add or remove."
)
GRANT_NO_EXPIRY = _("That voucher never expires: there is no expiry to extend.")
GRANT_BELOW_USED = _("You cannot take away more sessions than the customer has left.")
CUSTOMER_UNAVAILABLE = _("That customer's card does not exist in this business.")
#: Why a session cannot be spent (queries.redeem_refusal) → its code and its message.
REDEEM_REFUSALS = {
    "voided": (
        "service.grant_voided",
        _("This voucher was voided: it can no longer be used."),
    ),
    "expired": ("service.grant_expired", _("This voucher has expired.")),
    "no_uses_left": (
        "service.grant_no_uses_left",
        _("This voucher has no sessions left."),
    ),
    "does_not_cover_service": (
        "service.grant_does_not_cover_service",
        _(
            "This voucher does not cover that service. A voucher of haircuts pays for haircuts, not for the shampoo."
        ),
    ),
}

SESSION_NOT_FOUND = _("That voucher session does not exist in this business.")
LINE_ALREADY_HELD = _("That line already holds a session of a voucher.")
HOLD_LOST = _(
    "The session held from «%(name)s» is no longer held (its day passed or it was released). Take the voucher "
    "off the line and apply it again."
)
HOLD_CUSTOMER_MISMATCH = _(
    "The voucher «%(name)s» belongs to another customer: charge the sale to its owner or take the voucher off "
    "the line."
)
SESSION_SETTLED = _(
    "That voucher session can no longer be released: the sale is charged. Giving it back is a refund."
)
SESSION_NOT_SETTLED = _("That session was never charged, so there is nothing to give back.")
SESSION_ALREADY_RETURNED = _("That session was already given back by another refund.")
#: How long a session held at the till waits to be charged (SERVICE-F25).
HOLD_DURATION = dt.timedelta(days=1)

#: Run only by the platform (events.py): no role holds it, so no person and no API key reaches it.
SYSTEM = "service.system"

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
PACKAGE_PLAIN = (
    "name",
    "description",
    "discount_type",
    "discount_percent_bp",
    "discount_amount",
    "is_active",
    "is_featured",
    "sort_order",
)
PACKAGE_NULLABLE = ("fixed_price", "validity_days", "max_uses")


def _actor(ctx: OperationContext) -> str:
    """Who acted, as a person reads it («Voided by …»): an account's full name, else its email, else
    its username; the platform or an API key as they name themselves."""
    actor = ctx.actor
    if actor is None:
        return ""
    if hasattr(actor, "get_username"):
        name = actor.get_full_name() or actor.email or actor.get_username()
    else:
        name = str(actor)
    return name[:ACTOR_MAX_LENGTH]


def _tidy(name: str) -> str:
    """A name as it is kept: single spaces (two names that differ only in spaces are the same name)."""
    return " ".join(name.split())


def _refuse(message, code: str, field: str):
    return InvalidPayload(str(message), code=code, fields={field: str(message)})


def _tax_category(key: str, field: str, *, hold: bool = False) -> TaxCategory:
    """The active tax category ``key``; with ``hold``, held until the command commits (Taxes' read)."""
    if hold:
        tax = held_categories([key]).get(key)
    else:
        tax = TaxCategory.objects.filter(key=key, is_active=True).first()
    if tax is None:
        raise _refuse(TAX_UNKNOWN, "service.tax_category_unknown", field)
    return tax


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


def _changes(instance, values: dict) -> dict:
    return {
        field: value
        for field, value in values.items()
        if getattr(instance, field) != value
    }


def _apply(instance, changes: dict, ctx: OperationContext) -> None:
    for field, value in changes.items():
        setattr(instance, field, value)
    instance.updated_by = _actor(ctx)


# ── Services (SERVICE-F01 to F06) ─────────────────────────────────────────────────────────────


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
    permission="service.add_service",
    input=ServiceIn,
    output=ServiceOut,
    expose_api=True,
    ai={
        "description": "Create a service of the catalog with its price, duration and tax category (the settings' "
        "default when not said); what it does not say takes the settings.",
        "risk": "normal",
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
    permission="service.change_service",
    input=ServiceBulkIn,
    output=ServicesOut,
    expose_api=True,
    ai={
        "description": "Create up to 500 services at once, all of them or none: a line that cannot be created says "
        "why under its own field and nothing is created.",
        "risk": "high",
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
    permission="service.change_service",
    input=ServicePatchIn,
    output=ServiceOut,
    expose_api=True,
    ai={
        "description": "Change a service (named by its id or its name): only the fields sent change; null empties "
        "its category or its minimum and maximum prices. Its tax category can be changed, never emptied.",
        "risk": "normal",
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
    permission="service.delete_service",
    input=ServiceRefIn,
    output=ServiceOut,
    expose_api=True,
    ai={
        "description": "Archive a service: it is no longer offered nor bookable; its history, the appointments "
        "already booked and the vouchers that include it are kept. Archiving it again changes nothing.",
        "risk": "high",
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
    permission="service.change_service",
    input=ServiceRefIn,
    output=ServiceOut,
    expose_api=True,
    ai={
        "description": "Restore an archived service (named by its id or its name): it is offered and bookable again.",
        "risk": "normal",
    },
)
def restore_service(ctx: OperationContext, data: ServiceRefIn) -> dict:
    service = find_service(data.id, data.service, lock=True, archived=True)
    if not service.is_active:
        _apply(service, {"is_active": True, "archived_at": None}, ctx)
        service.save()
        record_event(ctx, events.SERVICE_RESTORED, {"id": str(service.id)})
    return load_service(service.id, ctx.scope)


# ── The service's image (SERVICE-F34, F35; round 2026-10-30, base.images) ─────────────────────────────────────

#: Where a service's own photos are kept under its hub's prefix: the folder ``members_media`` serves (apps.py).
PHOTOS = "service/services/"


@operation(
    "service.service.set_image",
    kind="command",
    permission="service.change_service",
    input=ServiceImageIn,
    output=ServiceOut,
    expose_api=True,
    ai={
        "description": "Set the image («foto») a service shows on the till («ponle foto al corte de señora»), named by "
        "its id or its name: an image of ERPlora's shared library by its reference (catalog:<folder>/<name>, from service.service.suggest_image or "
        "base.catalog_image.search), or empty to show none (its initials).",
        "risk": "normal",
    },
)
def set_image(ctx: OperationContext, data: ServiceImageIn) -> dict:
    """SERVICE-F34: an image of the library or none; anything else (a photo of its own too, which only its upload
    writes) is refused before anything changes. The photo of its own it let go is deleted once this is saved."""
    service = find_service(data.id, data.service, lock=True)
    images.check(ctx, data.image)
    _change_image(ctx, service, data.image)
    return load_service(service.id, ctx.scope)


@operation(
    "service.service.upload_image",
    kind="command",
    permission="service.change_service",
    input=ServiceImageUploadIn,
    output=ServiceOut,
    expose_api=True,
    ai={
        "description": "Not an assistant tool (it takes the photo the person picks in the service's form): keeps a "
        "photo of the service, a JPG, PNG or WebP of 2 MB at most, as its image.",
        "risk": "normal",
    },
)
def upload_image(ctx: OperationContext, data: ServiceImageUploadIn) -> dict:
    """SERVICE-F35: the photo becomes a 512 × 512 WebP of its own (``base.images``), within the plan's space, and
    takes the place of the one the service had, which is deleted once this is saved."""
    webp = images.to_webp(images.decode(data.data_base64, language=ctx.language), language=ctx.language)
    service = find_service(data.id, data.service, lock=True)
    _change_image(ctx, service, images.keep_photo(ctx, PHOTOS, webp))
    return load_service(service.id, ctx.scope)


def _change_image(ctx: OperationContext, service: Service, image: str) -> None:
    """Show ``image`` on ``service`` (no change, no event); the photo of its own it let go is deleted once saved.
    Archiving keeps it (SERVICE-F05 restores the service with it)."""
    if service.image == image:
        return
    previous = service.image
    _apply(service, {"image": image}, ctx)
    service.save(update_fields=["image", "updated_by", "updated_at"])
    record_event(ctx, events.SERVICE_UPDATED, {"id": str(service.id)})
    images.let_go(ctx, previous)


# ── Categories (SERVICE-F07, F08) ─────────────────────────────────────────────────────────────


def _check_category_name(name: str, *, other_than=None) -> None:
    taken = Category.objects.filter(is_deleted=False, name__iexact=name)
    if other_than is not None:
        taken = taken.exclude(pk=other_than)
    if taken.exists():
        raise Conflict(
            str(CATEGORY_NAME_TAKEN),
            code="service.category_name_taken",
            fields={"name": str(CATEGORY_NAME_TAKEN)},
        )


def _parent(parent_id, said, *, hold: bool = False) -> Category | None:
    if parent_id is None and said is None:
        return None
    try:
        return find_category(parent_id, said, hold=hold)
    except NotFound as exc:
        field = "parent_id" if parent_id else "parent"
        raise _refuse(
            PARENT_UNAVAILABLE, "service.parent_category_unavailable", field
        ) from exc


def _save_unique(instance, constraint: str, message, code: str) -> None:
    """Save in a savepoint: a name another write took meanwhile says so with the check's 409."""
    try:
        with transaction.atomic():
            instance.save()
    except IntegrityError as exc:
        if constraint in str(exc):
            raise Conflict(
                str(message), code=code, fields={"name": str(message)}
            ) from exc
        raise


def lock_tree() -> dict:
    """Locks every live category in id order; their parents as they are now (id → parent id). Moving or
    deleting a category takes it first, and so does the Hub admin's «Delete» (admin.py): a write that holds a
    category it names and then its own row never waits in a circle with them."""
    rows = Category.objects.select_for_update().filter(is_deleted=False).order_by("id")
    return dict(rows.values_list("id", "parent_id"))


@operation(
    "service.category.create",
    kind="command",
    permission="service.add_category",
    input=CategoryIn,
    output=CategoryOut,
    expose_api=True,
    ai={
        "description": "Create a service category, optionally inside another one; its name is unique.",
        "risk": "normal",
    },
)
def create_category(ctx: OperationContext, data: CategoryIn) -> dict:
    name = _tidy(data.name)
    _check_category_name(name)
    category = Category(
        name=name,
        description=data.description,
        parent=_parent(data.parent_id, data.parent, hold=True),
        icon=data.icon,
        color=data.color,
        sort_order=data.sort_order,
        created_by=_actor(ctx),
        updated_by=_actor(ctx),
    )
    _save_unique(
        category,
        "service_category_live_name_unique",
        CATEGORY_NAME_TAKEN,
        "service.category_name_taken",
    )
    record_event(ctx, events.CATEGORY_CREATED, {"id": str(category.id)})
    return load_category(category.id)


@operation(
    "service.category.update",
    kind="command",
    permission="service.change_category",
    input=CategoryPatchIn,
    output=CategoryOut,
    expose_api=True,
    ai={
        "description": "Change a service category (named by its id or its name): only the fields sent change; "
        "parent_id null makes it a root category.",
        "risk": "normal",
    },
)
def update_category(ctx: OperationContext, data: CategoryPatchIn) -> dict:
    sent = data.model_fields_set
    moving = bool(sent & {"parent_id", "parent"})
    category_id = find_category(data.id, data.category).pk
    # Moving a category takes every live category, in id order, before its own row: two moves at
    # once go one after the other, and the second sees where the first left the tree.
    parent_of = lock_tree() if moving else {}
    category = find_category(category_id, None, lock=True)
    values = {
        field: getattr(data, field)
        for field in ("description", "icon", "color", "sort_order")
        if field in sent and getattr(data, field) is not None
    }
    if data.name is not None:
        values["name"] = _tidy(data.name)
        _check_category_name(values["name"], other_than=category.pk)
    if moving:
        parent = _parent(data.parent_id, data.parent)
        problem = parent_problem(category.pk, parent.pk if parent else None, parent_of)
        if problem == "cycle":
            raise _refuse(CATEGORY_CYCLE, "service.category_cycle", "parent_id" if data.parent_id else "parent")
        if problem == "loop":
            raise Conflict(str(CATEGORY_LOOP), code="service.category_cycle")
        values["parent"] = parent
    changes = _changes(category, values)
    if changes:
        _apply(category, changes, ctx)
        _save_unique(
            category,
            "service_category_live_name_unique",
            CATEGORY_NAME_TAKEN,
            "service.category_name_taken",
        )
        record_event(ctx, events.CATEGORY_UPDATED, {"id": str(category.id)})
    return load_category(category.id)


@operation(
    "service.category.delete",
    kind="command",
    permission="service.delete_category",
    input=CategoryRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a service category: its services stay, without a category, and its subcategories "
        "move up to its parent; its name is free again.",
        "risk": "high",
    },
)
def delete_category(ctx: OperationContext, data: CategoryRefIn) -> dict:
    category_id = find_category(data.id, data.category).pk
    lock_tree()  # its children move: the same order as a move, so the two never wait for each other
    category = find_category(category_id, None, lock=True)
    now = timezone.now()
    Service.objects.filter(category=category).update(category=None, updated_at=now)
    children = Category.objects.filter(parent=category)
    # Its children go up to its parent; one that is that parent (a loop a raw write left) goes to the root.
    children.exclude(pk=category.parent_id).update(parent=category.parent_id, updated_at=now)
    children.filter(pk=category.parent_id).update(parent=None, updated_at=now)
    _apply(category, {"is_deleted": True, "deleted_at": timezone.now()}, ctx)
    category.save()
    record_event(ctx, events.CATEGORY_DELETED, {"id": str(category.id)})
    return {"id": category.id}


# ── Settings (SERVICE-F11) ────────────────────────────────────────────────────────────────────


@operation(
    "service.settings.update",
    kind="command",
    permission="service.manage_settings",
    input=SettingsIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "Save the service settings: only the fields sent change. The duration, buffer, online booking "
        "and tax category are what a new service takes when it does not say them.",
        "risk": "high",
    },
)
def update_settings(ctx: OperationContext, data: SettingsIn) -> dict:
    _, created = ServiceSettings.objects.get_or_create(singleton=True)
    settings = (
        ServiceSettings.objects.select_for_update(of=("self",))
        .select_related("default_tax_category")
        .get(singleton=True)
    )
    sent = data.model_fields_set
    values = {
        field: getattr(data, field)
        for field in (
            "default_duration",
            "default_buffer_time",
            "show_prices",
            "show_duration",
            "allow_online_booking",
        )
        if field in sent and getattr(data, field) is not None
    }
    if "default_tax_category_key" in sent:
        key = data.default_tax_category_key
        values["default_tax_category"] = (
            _tax_category(key, "default_tax_category_key", hold=True) if key else None
        )
    changes = _changes(settings, values)
    if changes or created:
        _apply(settings, changes, ctx)
        settings.save()
        record_event(ctx, events.SETTINGS_UPDATED)
    return settings_row(settings)


# ── Who performs each service (SERVICE-F31, F32) ──────────────────────────────────────────────


def _demote_other_primaries(member: Member, keep) -> None:
    Assignment.objects.filter(member=member, is_primary=True).exclude(pk=keep).update(
        is_primary=False, updated_at=timezone.now()
    )


def _assignment_payload(assignment: Assignment) -> dict:
    return {
        "id": str(assignment.id),
        "service_id": str(assignment.service_id),
        "member_id": str(assignment.member_id),
    }


@operation(
    "service.assignment.assign",
    kind="command",
    permission="service.change_service",
    input=AssignIn,
    output=AssignmentOut,
    expose_api=True,
    ai={
        "description": "Assign a professional of Staff (by name) to a service (by name), with their own duration and "
        "price if they have them; assigning them again changes those.",
        "risk": "normal",
    },
)
def assign(ctx: OperationContext, data: AssignIn) -> dict:
    service_id = find_service(data.service_id, data.service).pk
    member = resolve_member(data.member_id, data.member, lock=True)
    # The assignment is locked before the service is held, in the order the Hub admin's deletion of the
    # service takes them (its assignments, then itself): the other way round, each waited for the other.
    assignment = (
        Assignment.objects.select_for_update()
        .filter(service_id=service_id, member=member)
        .first()
    )
    service = find_service(service_id, None, hold=True)
    created = assignment is None
    if created:
        assignment = Assignment(service=service, member=member)
    assignment.custom_duration = data.custom_duration
    assignment.custom_price = data.custom_price
    # Assigning someone again changes their main service only when it is said.
    if created or "is_primary" in data.model_fields_set:
        assignment.is_primary = data.is_primary
    assignment.is_active = True
    if assignment.is_primary:
        _demote_other_primaries(member, keep=assignment.pk)
    assignment.save()
    name = events.ASSIGNMENT_ASSIGNED if created else events.ASSIGNMENT_UPDATED
    record_event(ctx, name, _assignment_payload(assignment))
    return load_assignment(assignment.id)


def _locked_assignment(assignment_id) -> Assignment:
    """An assignment of a live professional, the professional's record locked first and then its row."""
    found = (
        Assignment.objects.exclude(member__status=Member.Status.TERMINATED)
        .filter(pk=assignment_id)
        .first()
    )
    if found is None:
        raise NotFound(str(ASSIGNMENT_NOT_FOUND), code="service.assignment_not_found")
    resolve_member(found.member_id, None, lock=True)
    assignment = Assignment.objects.select_for_update().filter(pk=assignment_id).first()
    if assignment is None:
        raise NotFound(str(ASSIGNMENT_NOT_FOUND), code="service.assignment_not_found")
    return assignment


@operation(
    "service.assignment.update",
    kind="command",
    permission="service.change_service",
    input=AssignmentPatchIn,
    output=AssignmentOut,
    expose_api=True,
    ai={
        "description": "Change who performs a service: their own duration or price (null = the service's), their main "
        "service, or switch the assignment on or off.",
        "risk": "normal",
    },
)
def update_assignment(ctx: OperationContext, data: AssignmentPatchIn) -> dict:
    assignment = _locked_assignment(data.id)
    sent = data.model_fields_set
    values = {
        field: getattr(data, field)
        for field in ("custom_duration", "custom_price")
        if field in sent
    }
    values |= {
        field: getattr(data, field)
        for field in ("is_primary", "is_active")
        if getattr(data, field) is not None
    }
    changes = _changes(assignment, values)
    if changes:
        if changes.get("is_primary"):
            _demote_other_primaries(assignment.member, keep=assignment.pk)
        for field, value in changes.items():
            setattr(assignment, field, value)
        assignment.save()
        record_event(ctx, events.ASSIGNMENT_UPDATED, _assignment_payload(assignment))
    return load_assignment(assignment.id)


@operation(
    "service.assignment.remove",
    kind="command",
    permission="service.change_service",
    input=ByIdIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Remove a professional from a service: they no longer perform it.",
        "risk": "normal",
    },
)
def remove_assignment(ctx: OperationContext, data: ByIdIn) -> dict:
    assignment = _locked_assignment(data.id)
    payload = _assignment_payload(assignment)
    assignment.delete()
    record_event(ctx, events.ASSIGNMENT_REMOVED, payload)
    return {"id": data.id}


@operation(
    "service.assignment.release_member",
    kind="command",
    permission=SYSTEM,
    input=MemberReleaseIn,
    output=ReleasedOut,
    ai={
        "description": "Platform reaction to staff.member.terminated: the professional who left stops performing "
        "every service.",
        "risk": "normal",
    },
)
def release_member(ctx: OperationContext, data: MemberReleaseIn) -> dict:
    assignments = list(
        Assignment.objects.select_for_update().filter(member_id=data.id).order_by("id")
    )
    for assignment in assignments:
        payload = _assignment_payload(assignment)
        assignment.delete()
        record_event(ctx, events.ASSIGNMENT_REMOVED, payload)
    return {"removed": len(assignments)}


# ── Packages (SERVICE-F12, F13) ───────────────────────────────────────────────────────────────


def _check_package_name(name: str, *, other_than=None) -> None:
    taken = Package.objects.filter(is_deleted=False, name__iexact=name)
    if other_than is not None:
        taken = taken.exclude(pk=other_than)
    if taken.exists():
        raise Conflict(
            str(PACKAGE_NAME_TAKEN),
            code="service.package_name_taken",
            fields={"name": str(PACKAGE_NAME_TAKEN)},
        )


def _offered(service: Service | None, field: str) -> Service:
    """``service`` as a line of a voucher takes it: refused when it does not exist or is archived."""
    if service is None:
        raise _refuse(LINE_SERVICE_MISSING, "service.service_not_found", field)
    if not service.is_active:
        raise _refuse(LINE_SERVICE_ARCHIVED, "service.service_archived", field)
    return service


def _line_services(data: PackageIn) -> list[Service]:
    lines = []
    for index, line in enumerate(data.items):
        field = f"items.{index}.{'service_id' if line.service_id else 'service'}"
        try:
            service = find_service(line.service_id, line.service)
        except NotFound:
            service = None
        lines.append((_offered(service, field), field))
    if len({service.pk for service, _ in lines}) != len(lines):
        raise _refuse(SERVICE_REPEATED, "service.service_repeated", "items")
    # Held in one read and in id order (two vouchers of the same services never wait in a circle): archiving
    # one or deleting it in the Hub admin waits for this write, and one taken away meanwhile is refused.
    held = {row.pk: row for row in held_rows(Service.objects.filter(pk__in=[s.pk for s, _ in lines]))}
    return [_offered(held.get(service.pk), field) for service, field in lines]


@operation(
    "service.package.create",
    kind="command",
    permission="service.add_package",
    input=PackageIn,
    output=PackageOut,
    expose_api=True,
    ai={
        "description": "Create a voucher of the catalog: the services it covers (each once, with its sessions), its "
        "uses in all (none = unlimited), its validity in days from the purchase (none = never expires), its "
        "discount and its closed price.",
        "risk": "normal",
    },
)
def create_package(ctx: OperationContext, data: PackageIn) -> dict:
    name = _tidy(data.name)
    _check_package_name(name)
    services = _line_services(data)
    package = Package(
        name=name,
        **{field: getattr(data, field) for field in PACKAGE_PLAIN if field != "name"},
        **{field: getattr(data, field) for field in PACKAGE_NULLABLE},
        created_by=_actor(ctx),
        updated_by=_actor(ctx),
    )
    _save_unique(
        package,
        "service_package_live_name_unique",
        PACKAGE_NAME_TAKEN,
        "service.package_name_taken",
    )
    PackageItem.objects.bulk_create(
        PackageItem(
            package=package,
            service=service,
            sessions=line.sessions,
            sort_order=position,
        )
        for position, (service, line) in enumerate(
            zip(services, data.items, strict=True)
        )
    )
    record_event(ctx, events.PACKAGE_CREATED, {"id": str(package.id)})
    return load_package(package.id)


@operation(
    "service.package.update",
    kind="command",
    permission="service.change_package",
    input=PackagePatchIn,
    output=PackageOut,
    expose_api=True,
    ai={
        "description": "Change a voucher of the catalog (named by its id or its name): only the fields sent change; "
        "null removes its closed price, validity or uses limit. Its lines never change, and the vouchers already "
        "sold keep their terms.",
        "risk": "normal",
    },
)
def update_package(ctx: OperationContext, data: PackagePatchIn) -> dict:
    package = find_package(data.id, data.package, lock=True)
    sent = data.model_fields_set
    values = {
        field: getattr(data, field)
        for field in PACKAGE_PLAIN
        if field in sent and getattr(data, field) is not None
    }
    values |= {
        field: getattr(data, field) for field in PACKAGE_NULLABLE if field in sent
    }
    if "name" in values:
        values["name"] = _tidy(values["name"])
        _check_package_name(values["name"], other_than=package.pk)
    changes = _changes(package, values)
    if changes:
        _apply(package, changes, ctx)
        _save_unique(
            package,
            "service_package_live_name_unique",
            PACKAGE_NAME_TAKEN,
            "service.package_name_taken",
        )
        record_event(ctx, events.PACKAGE_UPDATED, {"id": str(package.id)})
    return load_package(package.id)


@operation(
    "service.package.delete",
    kind="command",
    permission="service.delete_package",
    input=PackageRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a voucher from the catalog: it can no longer be sold; the ones already sold are still "
        "spent, adjusted and voided as before.",
        "risk": "high",
    },
)
def delete_package(ctx: OperationContext, data: PackageRefIn) -> dict:
    package = find_package(data.id, data.package, lock=True)
    _apply(package, {"is_deleted": True, "deleted_at": timezone.now()}, ctx)
    package.save()
    record_event(ctx, events.PACKAGE_DELETED, {"id": str(package.id)})
    return {"id": package.id}


# ── Vouchers sold (SERVICE-F14, F17, F18, F21, F28) ───────────────────────────────────────────


def _grant_payload(grant: Grant) -> dict:
    return {
        "id": str(grant.id),
        "package_id": str(grant.package_id),
        "customer_id": str(grant.customer_id),
    }


@operation(
    "service.grant.create",
    kind="command",
    permission="service.grant_package",
    input=GrantIn,
    output=GrantOut,
    expose_api=True,
    ai={
        "description": "Grant (sell) a voucher of the catalog to a customer (by name or phone), with the amount paid "
        "and the sale if any: its uses and validity are frozen and its expiry counts from the purchase.",
        "risk": "normal",
    },
)
def create_grant(ctx: OperationContext, data: GrantIn) -> dict:
    package = find_package(data.package_id, data.package, hold=True)
    if not package.is_active:
        raise NotFound(str(PACKAGE_NOT_FOUND), code="service.package_not_found")
    customer = find_customer(data.customer_id, data.customer, lock=True)
    grant = Grant.objects.create(
        package=package,
        customer=customer,
        granted_at=data.granted_at or timezone.now(),
        sale_id=data.sale_id,
        amount=data.amount,
        net_amount=data.net_amount,
        tax_amount=data.tax_amount,
        max_uses=package.max_uses,
        validity_days=package.validity_days,
        note=data.note,
        created_by=_actor(ctx),
    )
    record_event(ctx, events.GRANT_GRANTED, _grant_payload(grant))
    return load_grant(ctx, grant.id)


@operation(
    "service.grant.void",
    kind="command",
    permission="service.void_grant",
    input=VoidIn,
    output=GrantOut,
    expose_api=True,
    ai={
        "description": "Void a voucher sold by mistake, with the reason: only one never used. It can no longer be "
        "spent and stays as a trail; no money moves (a refund is done in Sales).",
        "risk": "high",
    },
)
def void_grant(ctx: OperationContext, data: VoidIn) -> dict:
    lock_grant(data.id)
    grant = find_grant(data.id)
    refusal = void_refusal(grant)
    if refusal == "already_voided":
        raise Conflict(str(GRANT_ALREADY_VOIDED), code="service.grant_already_voided")
    if refusal == "in_use":
        raise Conflict(str(GRANT_IN_USE), code="service.grant_in_use")
    Grant.objects.filter(pk=grant.pk).update(
        voided_at=timezone.now(),
        voided_by=_actor(ctx),
        void_reason=data.reason,
        updated_at=timezone.now(),
    )
    record_event(ctx, events.GRANT_VOIDED, _grant_payload(grant))
    return load_grant(ctx, grant.id)


@operation(
    "service.grant.adjust",
    kind="command",
    permission="service.adjust_grant",
    input=AdjustIn,
    output=GrantOut,
    expose_api=True,
    ai={
        "description": "Adjust a voucher sold, with the reason: give sessions or a later expiry as a courtesy, or take "
        "sessions to correct its balance (never more than are left). It stays as a movement.",
        "risk": "high",
    },
)
def adjust_grant(ctx: OperationContext, data: AdjustIn) -> dict:
    lock_grant(data.id)
    grant = find_grant(data.id)
    if grant.voided_at is not None:
        raise Conflict(str(GRANT_ALREADY_VOIDED), code="service.grant_already_voided")
    if data.uses_delta and grant.max_uses is None:
        raise Conflict(str(GRANT_UNLIMITED), code="service.grant_unlimited")
    if data.days_delta and grant.validity_days is None:
        raise Conflict(str(GRANT_NO_EXPIRY), code="service.grant_no_expiry")
    remaining = balance(grant).remaining
    if data.uses_delta < 0 and remaining is not None and -data.uses_delta > remaining:
        raise Conflict(str(GRANT_BELOW_USED), code="service.grant_adjust_below_used")
    GrantAdjustment.objects.create(
        grant=grant,
        uses_delta=data.uses_delta,
        days_delta=data.days_delta,
        reason=data.reason,
        actor=_actor(ctx),
    )
    record_event(
        ctx,
        events.GRANT_ADJUSTED,
        {
            "id": str(grant.id),
            "uses_delta": data.uses_delta,
            "days_delta": data.days_delta,
        },
    )
    return load_grant(ctx, grant.id)


@operation(
    "service.grant.redeem",
    kind="command",
    permission="service.redeem_package",
    input=RedeemIn,
    output=RedemptionOut,
    expose_api=True,
    ai={
        "description": "Spend one session of a voucher sold (outside the till), optionally on a service it covers and "
        "linked to an appointment or a sale. Refused when voided, expired or without sessions left.",
        "risk": "normal",
    },
)
def redeem(ctx: OperationContext, data: RedeemIn) -> dict:
    service = (
        find_service(data.service_id, data.service)
        if (data.service_id or data.service)
        else None
    )
    lock_grant(data.id)
    grant = find_grant(data.id)
    state = balance(grant)
    refusal = redeem_refusal(grant, state, service)
    if refusal:
        code, message = REDEEM_REFUSALS[refusal]
        raise Conflict(str(message), code=code)
    session = Redemption.objects.create(
        grant=grant,
        service=service,
        appointment_id=data.appointment_id,
        sale_id=data.sale_id,
        note=data.note,
        actor=_actor(ctx),
    )
    record_event(
        ctx,
        events.GRANT_REDEEMED,
        {
            "id": str(grant.id),
            "redemption_id": str(session.id),
            "service_id": str(service.id) if service else None,
        },
    )
    return {
        "id": session.id,
        "grant_id": grant.id,
        "service_id": service.id if service else None,
        "service_name": service.name if service else None,
        "redeemed_at": session.redeemed_at,
        "remaining": None if state.remaining is None else state.remaining - 1,
    }


@operation(
    "service.grant.reassign",
    kind="command",
    permission=SYSTEM,
    input=ReassignIn,
    output=ReassignedOut,
    ai={
        "description": "Platform reaction to customer.customer.merged: the absorbed card's vouchers move to the card "
        "that stays, with their sessions and adjustments.",
        "risk": "normal",
    },
)
def reassign_grants(ctx: OperationContext, data: ReassignIn) -> dict:
    if data.id == data.absorbed_id:
        return {"moved": 0}
    if not Customer.objects.select_for_update().filter(pk=data.id).exists():
        raise NotFound(str(CUSTOMER_UNAVAILABLE), code="service.customer_unavailable")
    moved = Grant.objects.filter(customer_id=data.absorbed_id).update(
        customer_id=data.id, updated_at=timezone.now()
    )
    if moved:
        record_event(
            ctx,
            events.GRANT_REASSIGNED,
            {"id": str(data.id), "absorbed_id": str(data.absorbed_id)},
        )
    return {"moved": moved}


@operation(
    "service.grant.forget_customer",
    kind="command",
    permission=SYSTEM,
    input=ForgetCustomerIn,
    output=ForgottenOut,
    ai={
        "description": "Platform reaction to customer.customer.erased (GDPR): the free texts of the card's vouchers "
        "(notes, void reasons, adjustment reasons, session notes) are emptied; ids, amounts and sessions stay.",
        "risk": "normal",
    },
)
def forget_customer(ctx: OperationContext, data: ForgetCustomerIn) -> dict:
    grants = Grant.objects.filter(customer_id=data.id)
    touched = set(grants.exclude(note="", void_reason="").values_list("id", flat=True))
    touched |= set(GrantAdjustment.objects.filter(grant__customer_id=data.id).exclude(reason="").values_list("grant_id", flat=True))
    touched |= set(
        Redemption.objects.filter(grant__customer_id=data.id)
        .exclude(note="", return_reason="")
        .values_list("grant_id", flat=True)
    )
    if touched:
        now = timezone.now()
        grants.filter(pk__in=touched).update(note="", void_reason="", updated_at=now)
        GrantAdjustment.objects.filter(grant_id__in=touched).update(reason="")
        Redemption.objects.filter(grant_id__in=touched).update(note="", return_reason="")
        record_event(ctx, events.GRANT_ERASED, {"id": str(data.id)})
    return {"erased": len(touched)}




# ── Sessions of the till (SERVICE-F22–F27) ────────────────────────────────────────────────────
#
# Sales runs them by name, with the seller's context, inside its own transaction: they lock the
# vouchers' rows first (in id order when there are several) and then the sessions, as every write on
# a voucher does, so two tills on the same voucher go one after the other.

HELD = Redemption.Status.HELD
CONSUMED = Redemption.Status.CONSUMED


def _unique(ids) -> list:
    return list(dict.fromkeys(ids))


def _lock_sessions(ids) -> dict:
    """The sessions ``ids``, their vouchers locked first and then themselves (``NotFound`` if one is missing)."""
    wanted = _unique(ids)
    owners = set(
        Redemption.objects.filter(pk__in=wanted).values_list("grant_id", flat=True)
    )
    list(Grant.objects.select_for_update().filter(pk__in=owners).order_by("id"))
    sessions = {
        session.id: session
        for session in Redemption.objects.select_for_update()
        .filter(pk__in=wanted)
        .order_by("id")
    }
    if len(sessions) != len(wanted):
        raise NotFound(str(SESSION_NOT_FOUND), code="service.session_not_found")
    return sessions


def _session_rows(ids) -> list[dict]:
    """``SessionOut`` of each session, in the order given, with its voucher's balance read now."""
    wanted = _unique(ids)
    now = timezone.now()
    sessions = {
        session.id: session for session in Redemption.objects.filter(pk__in=wanted)
    }
    owners = {
        grant.id: grant
        for grant in grants(now).filter(
            pk__in={session.grant_id for session in sessions.values()}
        )
    }
    rows = []
    for session_id in wanted:
        session = sessions[session_id]
        grant = owners[session.grant_id]
        state = balance(grant, now)
        rows.append(
            {
                "id": session.id,
                "grant_id": grant.id,
                "package_id": grant.package_id,
                "package_name": grant.package.name,
                "customer_id": grant.customer_id,
                "service_id": session.service_id,
                "status": session.status,
                "order_line_id": session.order_line_id,
                "hold_until": session.hold_until,
                "sale_id": session.sale_id,
                "remaining": state.remaining,
                "voucher_expired": state.is_expired,
            }
        )
    return rows


def _owner_name(session: Redemption) -> str:
    return Grant.objects.select_related("package").get(pk=session.grant_id).package.name


@operation(
    "service.session.hold",
    kind="command",
    permission="service.redeem_package",
    input=HoldIn,
    output=SessionOut,
    ai={
        "description": "Sales' step when a line of an open check is paid with a customer's voucher: reserve one session "
        "of that voucher for that line for one day (it counts as used). To pay a line with a voucher, use "
        "sale.order.apply_voucher, which calls this.",
        "risk": "normal",
    },
)
def hold_session(ctx: OperationContext, data: HoldIn) -> dict:
    service = find_service(data.service_id, None)
    lock_grant(data.grant_id)
    now = timezone.now()
    # A hold of this very line whose day passed frees the line first (the hourly task may not have run).
    Redemption.objects.filter(
        order_line_id=data.order_line_id, status=HELD, hold_until__lte=now
    ).update(
        status=Redemption.Status.EXPIRED, ended_at=F("hold_until"), ended_by="system"
    )
    if Redemption.objects.filter(
        order_line_id=data.order_line_id, status__in=Redemption.LIVE
    ).exists():
        raise Conflict(str(LINE_ALREADY_HELD), code="service.line_already_held")
    grant = find_grant(data.grant_id)
    refusal = redeem_refusal(grant, balance(grant, now), service)
    if refusal:
        code, message = REDEEM_REFUSALS[refusal]
        raise Conflict(str(message), code=code)
    try:
        with transaction.atomic():
            session = Redemption.objects.create(
                grant=grant,
                service=service,
                status=HELD,
                order_line_id=data.order_line_id,
                hold_until=now + HOLD_DURATION,
                redeemed_at=now,
                actor=_actor(ctx),
            )
    except IntegrityError:
        # The same line held at once with another voucher: the database keeps one.
        raise Conflict(str(LINE_ALREADY_HELD), code="service.line_already_held") from None
    record_event(
        ctx, events.SESSION_RESERVED, {"id": str(session.id), "grant_id": str(grant.id)}
    )
    return _session_rows([session.id])[0]


@operation(
    "service.session.release",
    kind="command",
    permission="service.redeem_package",
    input=SessionRefIn,
    output=SessionOut,
    ai={
        "description": "Sales' step when a line paid with a voucher is undone, removed or voided, or its check voided: the "
        "session held for it goes back to the voucher at once. Releasing one already released or expired changes "
        "nothing; a session already charged is refused (giving it back is a refund).",
        "risk": "normal",
    },
)
def release_session(ctx: OperationContext, data: SessionRefIn) -> dict:
    session = _lock_sessions([data.id])[data.id]
    if session.status in (CONSUMED, Redemption.Status.RETURNED):
        raise Conflict(str(SESSION_SETTLED), code="service.session_settled")
    if session.status == HELD:
        Redemption.objects.filter(pk=session.pk).update(
            status=Redemption.Status.RELEASED,
            ended_at=timezone.now(),
            ended_by=_actor(ctx),
        )
        record_event(
            ctx,
            events.SESSION_RELEASED,
            {"id": str(session.id), "grant_id": str(session.grant_id)},
        )
    return _session_rows([session.id])[0]


def _owner_matches(session: Redemption, customer_id) -> bool:
    """The sale's customer owns the voucher: its card, or the card it was merged into."""
    if customer_id is None:
        return False
    owner = Grant.objects.select_related("customer").get(pk=session.grant_id).customer
    return customer_id in (owner.id, owner.merged_into_id)


@operation(
    "service.session.settle",
    kind="command",
    permission="service.redeem_package",
    input=SettleIn,
    output=SessionsOut,
    ai={
        "description": "Sales' step when a sale is charged: the sessions held for its lines paid with vouchers are "
        "delivered for good and linked to the sale. Refused, delivering none, if one is no longer held (its day "
        "passed, it was released) or the sale's customer does not own the voucher. Repeating it for the same sale "
        "changes nothing.",
        "risk": "high",
    },
)
def settle_sessions(ctx: OperationContext, data: SettleIn) -> dict:
    sessions = _lock_sessions(data.ids)
    now = timezone.now()
    pending = []
    for session_id in _unique(data.ids):
        session = sessions[session_id]
        if session.status == CONSUMED and session.sale_id == data.sale_id:
            continue
        if session.status != HELD or session.hold_until <= now:
            raise Conflict(
                str(HOLD_LOST) % {"name": _owner_name(session)}, code="service.hold_lost"
            )
        if not _owner_matches(session, data.customer_id):
            raise Conflict(
                str(HOLD_CUSTOMER_MISMATCH) % {"name": _owner_name(session)},
                code="service.hold_customer_mismatch",
            )
        pending.append(session)
    for session in pending:
        Redemption.objects.filter(pk=session.pk).update(
            status=CONSUMED, settled_at=now, sale_id=data.sale_id
        )
        record_event(
            ctx,
            events.SESSION_SETTLED,
            {
                "id": str(session.id),
                "grant_id": str(session.grant_id),
                "sale_id": str(data.sale_id),
            },
        )
    return {"rows": _session_rows(data.ids)}


@operation(
    "service.session.expire",
    kind="command",
    permission=SYSTEM,
    input=NoIn,
    output=ExpiredOut,
    ai={
        "description": "Platform task, every hour: the sessions held at the till whose day passed without the sale being "
        "charged are marked expired (the balance already stopped counting them at the deadline).",
        "risk": "normal",
    },
)
def expire_holds(ctx: OperationContext, data: NoIn) -> dict:
    # Locked in id order, as every other step of a session takes them; one notice per session, saying which
    # session of which voucher (hub#2681), and none when nothing lapsed.
    lapsed = list(
        Redemption.objects.select_for_update()
        .filter(status=HELD, hold_until__lte=timezone.now())
        .order_by("id")
        .values_list("id", "grant_id")
    )
    if lapsed:
        Redemption.objects.filter(id__in=[session_id for session_id, _ in lapsed]).update(
            status=Redemption.Status.EXPIRED, ended_at=F("hold_until"), ended_by="system"
        )
    for session_id, grant_id in lapsed:
        record_event(
            ctx, events.SESSION_EXPIRED, {"id": str(session_id), "grant_id": str(grant_id)}
        )
    return {"expired": len(lapsed)}


@operation(
    "service.session.return",
    kind="command",
    permission="service.return_session",
    input=ReturnIn,
    output=SessionsOut,
    ai={
        "description": "Sales' step when a sale is voided or refunded: the sessions spent in it (or in the lines that come "
        "back) return to their vouchers, even an expired one, with the document and the reason. The same document "
        "again gives nothing back twice; a session given back by another document is refused.",
        "risk": "high",
    },
)
def return_sessions(ctx: OperationContext, data: ReturnIn) -> dict:
    sessions = _lock_sessions(data.ids)
    pending = []
    for session_id in _unique(data.ids):
        session = sessions[session_id]
        if session.status == Redemption.Status.RETURNED:
            if session.return_reference != data.reference:
                raise Conflict(
                    str(SESSION_ALREADY_RETURNED),
                    code="service.session_already_returned",
                )
            continue
        if session.status != CONSUMED:
            raise Conflict(
                str(SESSION_NOT_SETTLED), code="service.session_not_settled"
            )
        pending.append(session)
    now = timezone.now()
    for session in pending:
        Redemption.objects.filter(pk=session.pk).update(
            status=Redemption.Status.RETURNED,
            ended_at=now,
            ended_by=_actor(ctx),
            return_reference=data.reference,
            return_reason=data.reason,
        )
        record_event(
            ctx,
            events.SESSION_RETURNED,
            {
                "id": str(session.id),
                "grant_id": str(session.grant_id),
                "reference": str(data.reference),
            },
        )
    return {"rows": _session_rows(data.ids)}
