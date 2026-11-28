"""What of Customers travels in an export of the business (BASE-F35) besides the customers themselves: its active
groups, tags and custom fields, by their name, read with Customers' own lists and written with its own creates; and, in
a backup only, what each card keeps in those fields, by the card (its name, phone and email) and the field's name,
written with the card's own change. A value whose card or field the business does not have is told and left out."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import OperationError
from pydantic import ValidationError

from base.blueprint.calls import Dataset, Loaded, by_name, call, count_of, ids_of, natural_key, pages, reason, remover
from base.blueprint.calls import rows_of, text_of
from base.blueprint.datasets import customer_identity

GROUP_FIELDS = ("name", "description", "color", "sort_order")
TAG_FIELDS = ("name", "color")
FIELD_FIELDS = ("name", "field_type", "options", "is_required", "sort_order")
ACTIVE = {"is_active": True}
VALUES = "customer.field_value.list"
VALUE_FIELDS = ("customer", "phone", "email", "field", "value")
CARD_MISSING = _("its card is not there")
FIELD_MISSING = _("the custom field «%(field)s» is not there")


def _catalogue(entity: str, label, fields: tuple[str, ...], model: str) -> Dataset:
    listed = f"customer.{entity}.list"
    return Dataset(
        key=f"customer.{entity}",
        label=label,
        rows=rows_of(listed, fields, **ACTIVE),
        ids=ids_of(listed, **ACTIVE),
        count=count_of(listed, **ACTIVE),
        load=by_name(listed, f"customer.{entity}.create", fields),
        remove=remover(f"customer.{entity}.delete"),
        models=(model,),
    )


def _card(row: dict) -> str:
    return customer_identity(text_of(row, "customer"), text_of(row, "phone"), text_of(row, "email"))


def _value_key(row: dict) -> str:
    return f"{_card(row)}\x00{natural_key(text_of(row, 'field'))}"


def _set_values(ctx: OperationContext, loaded: Loaded, card, fields: dict, values: list[dict]) -> None:
    """The values of one card, in one change of it: one it refuses leaves all of them out, and is told once."""
    label = text_of(values[0], "customer")
    sent = []
    for row in values:
        field = fields.get(natural_key(text_of(row, "field")))
        if card is None or field is None:
            missing = CARD_MISSING if card is None else FIELD_MISSING
            loaded.refuse(label, str(missing) % {"field": text_of(row, "field")})
        else:
            sent.append({"field_id": field, "value": text_of(row, "value")})
    if not sent:
        return
    try:
        call(ctx, "customer.customer.update", id=card, field_values=sent)
    except (OperationError, ValidationError) as exc:
        loaded.failed += len(sent) - 1
        loaded.refuse(label, reason(exc))
        return
    loaded.created += [f"{card}:{value['field_id']}" for value in sent]


def _value_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_value_key(row) for row in rows_of(VALUES, VALUE_FIELDS)(ctx)}
    cards = {customer_identity(row.name, row.phone or "", row.email or ""): row.id for row in pages(ctx, "customer.customer.list")}
    fields = {natural_key(row.name): row.id for row in pages(ctx, "customer.field.list", **ACTIVE)}
    by_card: dict[str, list[dict]] = {}
    for row in rows:
        if _value_key(row) in existing:
            loaded.already += 1
        else:
            by_card.setdefault(_card(row), []).append(row)
    for card, values in by_card.items():
        _set_values(ctx, loaded, cards.get(card), fields, values)


DATASETS = [
    _catalogue("group", _("Customer groups"), GROUP_FIELDS, "CustomerGroup"),
    _catalogue("tag", _("Customer tags"), TAG_FIELDS, "CustomerTag"),
    _catalogue("field", _("Custom fields"), FIELD_FIELDS, "CustomField"),
    Dataset(
        key="customer.field_value",
        label=_("Custom field values"),
        rows=rows_of(VALUES, VALUE_FIELDS),
        count=count_of(VALUES),
        load=_value_load,
        personal=True,
        models=("CustomFieldValue",),
    ),
]
