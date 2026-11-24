"""A card back from a separate copy (CUSTOMER-F33): a deleted one restored, or one the business no longer has made
again, with what hung from it in the copy."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import INTERNAL, operation
from live.outbox import record_event

from apps.customer import events
from apps.customer.models import Customer, CustomerGroup, CustomerTag, CustomField
from apps.customer.queries.cards import load_detail
from apps.customer.queries.reads import (
    CUSTOMER_UNAVAILABLE,
    CUSTOMER_UNAVAILABLE_CODE,
    find_customer,
    lost_since_copy,
    named,
)
from apps.customer.schemas.cards import CustomerIn, FieldValueIn
from apps.customer.schemas.custom_fields import FieldIn
from apps.customer.schemas.recovery import (
    CustomerRecoveredOut,
    CustomerRecoverIn,
    CustomerRestoreIn,
    FieldValueOfCopyIn,
    GroupOfCopyIn,
    TagOfCopyIn,
)
from apps.customer.services.cards import create_customer
from apps.customer.services.field_values import _apply_field_values, _field_problem, _validated_field_values
from apps.customer.services.memberships import set_groups, set_tags
from base.recovery import LeftOut

FIELD_INACTIVE_LEFT = _('came back without its value of the field "%(field)s": deactivated in Customers')
FIELD_OPTION_LEFT = _('came back without its value of the field "%(field)s": no longer one of its options')
FIELD_TYPE_LEFT = _('came back without its value of the field "%(field)s": no longer of its type')


# Not an assistant tool, and declared by no app: only the system holds its permission, as the purchase commands. Its
# one door is the recovery from a separate copy (BASE-F114): no screen of the business undoes a deletion.
@operation(
    "customer.customer.restore",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.restore",
    input=CustomerRestoreIn,
    output=CustomerRecoveredOut,
    ai=INTERNAL,
)
def restore_customer(ctx: OperationContext, data: CustomerRestoreIn) -> dict:
    """CUSTOMER-F33: a deleted card back in every list, the same card with all that hangs from it (deleting keeps it,
    CUSTOMER-F07). Merged into another or erased it never comes back: its history lives on in the other card, or its
    personal data is gone. Repeating it on a card already back answers well and announces again, as deleting does.

    hub#1356: what hung from it in the separate copy it comes back from and the business deleted since (``data``, each
    by its id there) hangs from it again, as from a card made again from the copy (``_hang_from_copy``); what the
    business still has stays as it is, the card in it or not. A value that cannot come back does not keep the card
    deleted: the output says it came back without it, and why (``left_out``)."""
    customer = find_customer(ctx, data.id, data.customer, lock=True, live=False)
    if customer.merged_into_id is not None or customer.erased_at is not None:
        raise NotFound(CUSTOMER_UNAVAILABLE, code=CUSTOMER_UNAVAILABLE_CODE)
    if customer.deleted_at is not None:
        customer.deleted_at = None
        customer.is_active = True
        customer.save(update_fields=["deleted_at", "is_active", "updated_at"])
    record_event(ctx, events.CUSTOMER_RESTORED, {"id": str(customer.id)})
    left_out = _hang_from_copy(
        ctx,
        customer,
        groups=lost_since_copy(CustomerGroup, data.groups),
        tags=lost_since_copy(CustomerTag, data.tags),
        field_values=lost_since_copy(CustomField, data.field_values),
    )
    return load_detail(customer) | {"left_out": left_out}


# Not an assistant tool, and declared by no app, as the restore: its one door is the recovery from a separate copy
# (BASE-F114), for a card the business no longer has at all.
@operation(
    "customer.customer.recover",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.restore",
    input=CustomerRecoverIn,
    output=CustomerRecoveredOut,
    ai=INTERNAL,
)
def recover_customer(ctx: OperationContext, data: CustomerRecoverIn) -> dict:
    """hub#1285: a card of a separate copy the business no longer has, made again by ``customer.customer.create`` with
    what hung from it there (``_hang_from_copy``), all or nothing; the output says the values it came back without,
    and why (``left_out``)."""
    made = create_customer(ctx, CustomerIn.model_validate(data.model_dump(include=set(CustomerIn.model_fields))))
    customer = Customer.objects.get(pk=made.id)
    left_out = _hang_from_copy(ctx, customer, groups=data.groups, tags=data.tags, field_values=data.field_values)
    return load_detail(customer) | {"left_out": left_out}


def _hang_from_copy(
    ctx: OperationContext,
    customer: Customer,
    *,
    groups: list[GroupOfCopyIn],
    tags: list[TagOfCopyIn],
    field_values: list[FieldValueOfCopyIn],
) -> list[LeftOut]:
    """What hung from ``customer`` in a separate copy hung from it again, each by the operation its screen uses: the
    card put in its groups and tags besides those it is in (``set_groups``, ``set_tags``), each the business's own of
    that name (``queries.reads.named``, the active one first) or, if it has none, made again as the copy had it by the
    Groups or Tags screen's create (and deactivated if it was); its values of the custom fields as the card's screen
    checks them (CUSTOMER-F04), each field the business's own of that name or one made again by the Fields screen's
    create.
    Neither a value of a field the business deactivated (it shows on no card) nor one its field no longer takes comes
    back: the card comes back without it, and each is returned with why. One of a field the card holds a value of
    already does not either, and is nothing left out: the card keeps its own. A required field it has no value of
    does not keep it out, as the till makes a card without one (CUSTOMER-F01)."""
    # The group, tag and field operations register after this module's, in the order the registry keeps:
    # they are imported when a copy is hung, not when this module loads.
    from apps.customer.services.fields import create_field

    for relation, items in (("groups", groups), ("tags", tags)):
        if items:
            _join_named(ctx, customer, relation, items)
    held = set(customer.field_values.values_list("field_id", flat=True))
    values = []
    left_out = []
    for value in field_values:
        field = named(CustomField, value.name) or create_field(
            ctx, FieldIn.model_validate(value.model_dump(exclude={"id", "value"}))
        )
        if field.id in held:
            continue
        why = _why_left_out(field, value.value)
        if why is None:
            values.append(FieldValueIn(field_id=field.id, value=value.value))
        else:
            left_out.append(why)
    if values:
        _apply_field_values(customer, _validated_field_values(customer, values, required=False))
    return left_out


def _why_left_out(field: CustomField, value: str) -> LeftOut | None:
    """Why a card's ``value`` in a separate copy does not come back to ``field``: deactivated, or no longer one of its
    options or of its type, said by the field's name and never by the value, which is the customer's own; ``None``
    when it comes back."""
    if not field.is_active:
        return LeftOut(code="customer.field_inactive", message=FIELD_INACTIVE_LEFT % {"field": field.name})
    problem = _field_problem(field, value)
    if problem is None:
        return None
    code = problem[0]
    said = FIELD_OPTION_LEFT if code == "customer.field_invalid_option" else FIELD_TYPE_LEFT
    return LeftOut(code=code, message=said % {"field": field.name})


def _join_named(ctx: OperationContext, customer: Customer, relation: str, items: list) -> None:
    """``customer`` put by its screen's operation in the groups or tags (``relation``) named as ``items`` of the copy,
    besides those it is in (see ``_hang_from_copy``)."""
    # Imported here, as in _hang_from_copy: the group and tag operations register after this module's.
    from apps.customer.services.groups import create_group, update_group
    from apps.customer.services.tags import create_tag, update_tag

    model, create, update, put, ids_field = {
        "groups": (CustomerGroup, create_group, update_group, set_groups, "group_ids"),
        "tags": (CustomerTag, create_tag, update_tag, set_tags, "tag_ids"),
    }[relation]
    wanted = set(getattr(customer, relation).values_list("id", flat=True))
    for item in items:
        found = named(model, item.name)
        if found is None:
            found = create(ctx, create.input.model_validate(item.model_dump(exclude={"id", "is_active"})))
            if not item.is_active:
                update(ctx, update.input(id=found.id, is_active=False))
        wanted.add(found.id)
    put(ctx, put.input(id=customer.id, **{ids_field: sorted(wanted)}))
