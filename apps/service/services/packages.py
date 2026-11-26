"""The vouchers of the catalog (SERVICE-F12, F13): created, changed and deleted, each with the services it covers."""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.service import events
from apps.service.models.catalog import Service
from apps.service.models.packages import Package, PackageItem
from apps.service.queries.catalog import find_service
from apps.service.queries.packages import find_package, load_package
from apps.service.queries.reads import held_rows
from apps.service.schemas.fields import DeletedOut, PackageRefIn
from apps.service.schemas.packages import SERVICE_REPEATED, PackageIn, PackageOut, PackagePatchIn
from apps.service.services.writes import _actor, _apply, _changes, _refuse, _save_unique, _tidy

PACKAGE_NAME_TAKEN = _("There is already a package with that name. Pick another name.")
LINE_SERVICE_MISSING = _("That service does not exist in this business.")
LINE_SERVICE_ARCHIVED = _("That service is archived: it cannot go into a voucher.")

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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.add_package",
    input=PackageIn,
    output=PackageOut,
    expose_api=True,
    ai={
        "description": "Create a voucher of the catalog: the services it covers (each once, with its sessions), its "
        "uses in all (none = unlimited), its validity in days from the purchase (none = never expires), its "
        "discount and its closed price.",
        "risk": "normal",
        "asks": {
            "en": ("create a voucher of five massages for 200 euros", "add a ten-session laser pack valid for a year"),
            "es": (
                "crea un bono de cinco masajes por 200 €",
                "da de alta un bono de diez sesiones de láser que caduque al año",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.change_package",
    input=PackagePatchIn,
    output=PackageOut,
    expose_api=True,
    ai={
        "description": "Change a voucher of the catalog (named by its id or its name): only the fields sent change; "
        "null removes its closed price, validity or uses limit. Its lines never change, and the vouchers already "
        "sold keep their terms.",
        "risk": "normal",
        "asks": {
            "en": ("raise the massage voucher to 220 euros", "make the laser pack valid for 18 months"),
            "es": ("sube el bono de masajes a 220 €", "cambia la validez del bono de láser a 400 días"),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.delete_package",
    input=PackageRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a voucher from the catalog: it can no longer be sold; the ones already sold are still "
        "spent, adjusted and voided as before.",
        "risk": "high",
        "asks": {
            "en": ("stop selling the massage voucher", "delete the manicure pack"),
            "es": ("deja de vender el bono de masajes", "elimina el bono de manicuras"),
        },
    },
)
def delete_package(ctx: OperationContext, data: PackageRefIn) -> dict:
    package = find_package(data.id, data.package, lock=True)
    _apply(package, {"is_deleted": True, "deleted_at": timezone.now()}, ctx)
    package.save()
    record_event(ctx, events.PACKAGE_DELETED, {"id": str(package.id)})
    return {"id": package.id}
