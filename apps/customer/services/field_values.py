"""The values of a card's custom fields: each one checked against its field's type, then written (CUSTOMER-F04)."""

import math
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.errors import InvalidPayload

from apps.customer.models import Customer, CustomField, CustomFieldValue
from apps.customer.queries.reads import FIELD_UNAVAILABLE
from apps.customer.schemas.cards import FieldValueIn
from apps.customer.services.writes import lock_rows

FIELD_REQUIRED = _("This field is required.")
FIELD_INVALID_NUMBER = _("Enter a number.")
FIELD_INVALID_DATE = _("Enter a valid date.")
FIELD_INVALID_BOOLEAN = _("Choose yes or no.")
FIELD_INVALID_OPTION = _("Choose one of the options.")
#: Boolean values of a custom field: what is accepted and how it is kept.
BOOLEANS = {"true": "true", "1": "true", "false": "false", "0": "false"}


def _field_problem(field: CustomField, value: str) -> tuple[str, str, str] | None:
    """``None`` and the value as kept, or the error code and message of a value of the wrong shape."""
    if not value:
        return None
    if field.field_type == CustomField.FieldType.NUMBER:
        try:
            if not math.isfinite(Decimal(value)):
                raise InvalidOperation
        except InvalidOperation:
            return "customer.field_invalid_number", FIELD_INVALID_NUMBER
    elif field.field_type == CustomField.FieldType.DATE:
        try:
            if len(value) != 10:
                raise ValueError
            date.fromisoformat(value)
        except ValueError:
            return "customer.field_invalid_date", FIELD_INVALID_DATE
    elif (
        field.field_type == CustomField.FieldType.BOOLEAN
        and value.lower() not in BOOLEANS
    ):
        return "customer.field_invalid_boolean", FIELD_INVALID_BOOLEAN
    elif (
        field.field_type == CustomField.FieldType.SELECT and value not in field.options
    ):
        return "customer.field_invalid_option", FIELD_INVALID_OPTION
    return None


def _kept(field: CustomField, value: str) -> str:
    return (
        BOOLEANS[value.lower()]
        if value and field.field_type == CustomField.FieldType.BOOLEAN
        else value
    )


def _validated_field_values(
    customer: Customer, sent: list[FieldValueIn], *, required: bool = True
) -> dict[UUID, str]:
    """The values to keep per field, or ``InvalidPayload`` with every problem under its field.

    Only active fields count: an unknown or inactive one is unavailable. Every required field must
    end up with a value, the one sent or the one stored, unless ``required`` is false: a card made
    again from a separate copy is made as the till makes one, without them (``recover_customer``).
    """
    # The fields written are held until the COMMIT and read after: one deleted meanwhile is unavailable.
    lock_rows(CustomField, [item.field_id for item in sent])
    fields = {field.id: field for field in CustomField.objects.filter(is_active=True)}
    stored = dict(
        CustomFieldValue.objects.filter(customer=customer).values_list(
            "field_id", "value"
        )
    )
    problems: dict[str, tuple[str, str]] = {}
    kept: dict[UUID, str] = {}
    for item in sent:
        key = f"field_values.{item.field_id}"
        field = fields.get(item.field_id)
        if field is None:
            problems[key] = ("customer.field_unavailable", FIELD_UNAVAILABLE)
            continue
        problem = _field_problem(field, item.value)
        if problem:
            problems[key] = problem
            continue
        kept[field.id] = _kept(field, item.value)
    for field in fields.values() if required else ():
        if field.is_required and not kept.get(field.id, stored.get(field.id, "")):
            problems.setdefault(
                f"field_values.{field.id}", ("customer.field_required", FIELD_REQUIRED)
            )
    if problems:
        code, message = next(iter(problems.values()))
        raise InvalidPayload(
            message,
            code=code,
            fields={key: text for key, (_, text) in problems.items()},
        )
    return kept


def _apply_field_values(customer: Customer, kept: dict[UUID, str]) -> bool:
    """Writes the values (an empty one is no row); whether anything changed."""
    stored = dict(
        CustomFieldValue.objects.filter(customer=customer).values_list(
            "field_id", "value"
        )
    )
    changed = False
    for field_id, value in kept.items():
        if stored.get(field_id, "") == value:
            continue
        changed = True
        if value:
            CustomFieldValue.objects.update_or_create(
                customer=customer, field_id=field_id, defaults={"value": value}
            )
        else:
            CustomFieldValue.objects.filter(
                customer=customer, field_id=field_id
            ).delete()
    return changed
