"""The custom fields of the business (CUSTOMER-F29)."""

import pytest
from live.errors import Conflict, InvalidPayload

from apps.customer import events
from apps.customer.models import CustomField, CustomFieldValue
from apps.customer.schemas.custom_fields import FieldIn, FieldPatchIn
from apps.customer.schemas.fields import FieldRefIn as FieldRef

from .conftest import HUB_DB, card, invalid, outbox, run

pytestmark = HUB_DB


def test_field_crud_and_its_rules():
    field = run(
        "customer.field.create",
        FieldIn(
            name="Hair",
            field_type="select",
            options=["Short", "Long"],
            is_required=True,
        ),
    )
    assert (
        field.name,
        field.field_type,
        field.options,
        field.is_required,
        field.is_active,
    ) == ("Hair", "select", ["Short", "Long"], True, True)
    with pytest.raises(Conflict) as excinfo:
        run("customer.field.create", FieldIn(name="hair"))
    assert excinfo.value.code == "customer.field_name_taken"
    assert run(
        "customer.field.update",
        FieldPatchIn(id=field.id, options=["Short", "Long", "Bob"]),
    ).options == ["Short", "Long", "Bob"]
    # A type change before any card has a value is fine; after, it is refused.
    assert (
        run(
            "customer.field.update", FieldPatchIn(id=field.id, field_type="text")
        ).options
        == []
    )
    CustomFieldValue.objects.create(
        customer=card("Ana"), field=CustomField.objects.get(), value="Short"
    )
    with pytest.raises(Conflict) as excinfo:
        run("customer.field.update", FieldPatchIn(id=field.id, field_type="number"))
    assert invalid(excinfo.value) == (
        409,
        "customer.field_has_values",
        {
            "field_type": "This field already has values on some cards: its type cannot change."
        },
    )
    run("customer.field.delete", FieldRef(id=field.id))
    assert not CustomFieldValue.objects.exists()
    assert [name for name, _ in outbox()] == [
        events.FIELD_CREATED,
        events.FIELD_UPDATED,
        events.FIELD_UPDATED,
        events.FIELD_DELETED,
    ]


def test_turning_a_field_into_a_select_needs_its_options():
    field = CustomField.objects.create(name="Hair")
    with pytest.raises(InvalidPayload) as excinfo:
        run("customer.field.update", FieldPatchIn(id=field.id, field_type="select"))
    assert invalid(excinfo.value) == (
        422,
        "invalid_payload",
        {"options": "Add at least one option."},
    )
