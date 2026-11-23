"""Customer groups created, changed and deleted (CUSTOMER-F27)."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.operations import AI, operation
from live.outbox import record_event

from apps.customer import events
from apps.customer.models import CustomerGroup
from apps.customer.queries import find_group
from apps.customer.schemas.fields import DeletedOut, GroupRefIn
from apps.customer.schemas.groups import GroupIn, GroupPatchIn, GroupRow
from apps.customer.services.writes import _patched, _save_named, _with_count

GROUP_NAME_TAKEN = _("There is already a group with that name. Choose another name.")


@operation(
    "customer.group.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.configure",
    input=GroupIn,
    output=GroupRow,
    ai=AI(
        "Creates a customer group (name unique among the active groups, description, color, order).",
        asks={
            "en": ("create a VIP customer group", "make a new group for corporate clients"),
            "es": ("crea un grupo de clientes VIP", "quiero un grupo nuevo para las empresas"),
        },
    ),
)
def create_group(ctx: OperationContext, data: GroupIn) -> dict:
    group = CustomerGroup(**data.model_dump())
    _save_named(group, GROUP_NAME_TAKEN, "customer.group_name_taken")
    record_event(ctx, events.GROUP_CREATED, {"id": str(group.id)})
    return _with_count(group)


@operation(
    "customer.group.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.configure",
    input=GroupPatchIn,
    output=GroupRow,
    ai=AI(
        "Updates a customer group, by its id or current name: name, description, color, order, and whether it is "
        "active.",
        asks={
            "en": ("rename the VIP group to Gold", "make the Corporate group red"),
            "es": ("cambia el nombre del grupo VIP a Oro", "ponle color rojo al grupo Empresas"),
        },
    ),
)
def update_group(ctx: OperationContext, data: GroupPatchIn) -> dict:
    group = find_group(data.id, data.group, lock=True)
    if _patched(group, data, {"id", "group"}):
        _save_named(group, GROUP_NAME_TAKEN, "customer.group_name_taken")
        record_event(ctx, events.GROUP_UPDATED, {"id": str(group.id)})
    return _with_count(group)


@operation(
    "customer.group.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.delete",
    input=GroupRefIn,
    output=DeletedOut,
    ai=AI(
        "Deletes a customer group, by its id or name; the customers in it lose it.",
        risk="high",
        asks={
            "en": ("delete the summer group", "get rid of the Corporate group"),
            "es": ("borra el grupo de verano", "ya no quiero el grupo Empresas, quítalo"),
        },
    ),
)
def delete_group(ctx: OperationContext, data: GroupRefIn) -> dict:
    group = find_group(data.id, data.group, lock=True)
    group_id = group.id
    group.delete()
    record_event(ctx, events.GROUP_DELETED, {"id": str(group_id)})
    return {"id": group_id}
