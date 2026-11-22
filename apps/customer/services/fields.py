"""The custom fields of the cards created, changed and deleted (CUSTOMER-F29)."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import AI, operation
from live.outbox import record_event

from apps.customer import events
from apps.customer.models import CustomField, CustomFieldValue
from apps.customer.queries import find_field
from apps.customer.schemas import OPTIONS_MISSING, DeletedOut, FieldIn, FieldPatchIn, FieldRefIn, FieldRow
from apps.customer.services.writes import _patched, _save_named

FIELD_HAS_VALUES = _(
    "This field already has values on some cards: its type cannot change."
)
FIELD_NAME_TAKEN = _("There is already a field with that name. Choose another name.")


@operation(
    "customer.field.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.configure",
    input=FieldIn,
    output=FieldRow,
    ai=AI(
        "Creates a custom field on every customer's card: name, type (text, number, date, boolean, select, "
        "textarea), options of a select, order and whether it is required when the card is saved in full.",
        asks={
            "en": ("add a custom field for shoe size", "I want a field for the pet's name on every card"),
            "es": (
                "añade un campo para la talla de camiseta",
                "quiero apuntar en cada ficha el nombre de su mascota",
            ),
        },
    ),
)
def create_field(ctx: OperationContext, data: FieldIn) -> CustomField:
    field = CustomField(**data.model_dump())
    _save_named(field, FIELD_NAME_TAKEN, "customer.field_name_taken")
    record_event(ctx, events.FIELD_CREATED, {"id": str(field.id)})
    return field


@operation(
    "customer.field.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.configure",
    input=FieldPatchIn,
    output=FieldRow,
    ai=AI(
        "Updates a custom field, by its id or current name; its type cannot change once cards have values, and a "
        "select keeps at least one option.",
        asks={
            "en": ("make the shoe size field required", "let the size field also take XL"),
            "es": (
                "haz obligatorio el campo talla",
                "pon XL entre los valores del campo talla",
                "cambia el nombre del campo mascota",
            ),
        },
    ),
)
def update_field(ctx: OperationContext, data: FieldPatchIn) -> CustomField:
    field = find_field(data.id, data.field, lock=True)
    new_type = data.field_type or field.field_type
    if (
        new_type != field.field_type
        and CustomFieldValue.objects.filter(field=field).exists()
    ):
        raise Conflict(
            FIELD_HAS_VALUES,
            code="customer.field_has_values",
            fields={"field_type": FIELD_HAS_VALUES},
        )
    options = data.options if data.options is not None else field.options
    if new_type != CustomField.FieldType.SELECT:
        options = []
    elif not options:
        raise InvalidPayload(OPTIONS_MISSING, fields={"options": OPTIONS_MISSING})
    changes = _patched(field, data, {"id", "field", "options"})
    if field.options != options:
        field.options = options
        changes["options"] = options
    if changes:
        _save_named(field, FIELD_NAME_TAKEN, "customer.field_name_taken")
        record_event(ctx, events.FIELD_UPDATED, {"id": str(field.id)})
    return field


@operation(
    "customer.field.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.configure",
    input=FieldRefIn,
    output=DeletedOut,
    ai=AI(
        "Deletes a custom field, by its id or name, and the values every card had in it.",
        risk="high",
        asks={
            "en": ("delete the shoe size field", "remove the pet field from the cards"),
            "es": ("borra el campo talla", "quita el campo de mascota de las fichas"),
        },
    ),
)
def delete_field(ctx: OperationContext, data: FieldRefIn) -> dict:
    field = find_field(data.id, data.field, lock=True)
    field_id = field.id
    field.delete()
    record_event(ctx, events.FIELD_DELETED, {"id": str(field_id)})
    return {"id": field_id}
