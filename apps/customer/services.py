"""Write operations of the customer app: one operation = one transaction, with its event in the outbox.

Writes on a card lock its row first, so two writes on the same card never interleave. Every write of
a phone goes through ``apps.customer.phones`` (E.164 or a refusal); consent is only written by its two
commands; events carry ids only.
"""

import math
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

import pydantic
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.ninja import FIELD_MESSAGES
from live.operations import operation
from live.outbox import record_event

from apps.customer import events
from apps.customer.countries import country_from_text
from apps.customer.models import (
    Activity,
    Consent,
    Customer,
    CustomerGroup,
    CustomerTag,
    CustomField,
    CustomFieldValue,
    HealthRecord,
    OrderLink,
    Purchase,
)
from apps.customer.phones import InvalidPhone, to_e164
from apps.customer.queries import (
    CUSTOMER_UNAVAILABLE,
    CUSTOMER_UNAVAILABLE_CODE,
    FIELD_UNAVAILABLE,
    GROUP_UNAVAILABLE,
    TAG_UNAVAILABLE,
    business_country,
    find_customer,
    find_field,
    find_group,
    find_tag,
    HEALTH_PURPOSE,
    health_consent,
    load_detail,
    load_health,
)
from apps.customer.schemas import (
    OPTIONS_MISSING,
    ActivityIn,
    ActivityRow,
    ConsentGrantIn,
    ConsentRow,
    ConsentWithdrawIn,
    CustomerDetailOut,
    CustomerIn,
    CustomerPatchIn,
    CustomerRefIn,
    DeletedOut,
    EraseIn,
    ErasedOut,
    FieldIn,
    FieldPatchIn,
    FieldRefIn,
    FieldRow,
    FieldValueIn,
    GroupIn,
    GroupPatchIn,
    GroupRefIn,
    GroupRow,
    HealthGrantIn,
    HealthIn,
    HealthOut,
    HealthWithdrawIn,
    ImportIn,
    ImportOut,
    ImportRowIn,
    MergeIn,
    NoteIn,
    OrderCustomerOut,
    OrderLinkIn,
    PurchaseRecordIn,
    PurchaseRecordOut,
    PurchaseRefundIn,
    PurchaseRefundOut,
    PurchaseVoidIn,
    PurchaseVoidOut,
    SetGroupsIn,
    SetTagsIn,
    TagIn,
    TagPatchIn,
    TagRefIn,
    TagRow,
)

PHONE_INVALID = _(
    "This is not a valid phone number of its country: check the digits or write it with its "
    "international prefix (+44…)."
)
FIELD_REQUIRED = _("This field is required.")
FIELD_INVALID_NUMBER = _("Enter a number.")
FIELD_INVALID_DATE = _("Enter a valid date.")
FIELD_INVALID_BOOLEAN = _("Choose yes or no.")
FIELD_INVALID_OPTION = _("Choose one of the options.")
FIELD_HAS_VALUES = _(
    "This field already has values on some cards: its type cannot change."
)
GROUP_NAME_TAKEN = _("There is already a group with that name. Choose another name.")
TAG_NAME_TAKEN = _("There is already a tag with that name. Choose another name.")
FIELD_NAME_TAKEN = _("There is already a field with that name. Choose another name.")
SAME_CUSTOMER = _("Pick another card: a card cannot be merged into itself.")
DATE_IN_FUTURE = _("This date is in the future.")
COUNTRY_IMPORTED_EMPTY = _(
    "Country not recognised: imported without country, check it on the card."
)
HEALTH_CONSENT_REQUIRED = _("Record their permission first to keep health data.")
HEALTH_TEST_DATE_MISSING = _("Enter the date of the test.")
ALREADY_IMPORTED = _(
    "There is already a card with this name, phone and email: it is not created again."
)

#: The name an erased card keeps (CUSTOMER-F16): data, not a text of the interface.
ERASED_NAME = "Deleted customer"
#: What an erasure clears and what it keeps, written on its audit entry.
ERASE_SCOPE = [
    "customer",
    "activity",
    "field_values",
    "health",
    "memberships",
    "consent_addresses",
]
ERASE_RETAINED = ["purchases", "orders"]
#: The text fields of a card a merge fills from the duplicate when the survivor's is empty.
MERGE_FILLED = (
    "email",
    "phone",
    "tax_id",
    "company_name",
    "address",
    "city",
    "postal_code",
    "country",
    "avatar",
)
#: The fields a patch may clear by sending ``null``.
NULLABLE = frozenset({"birthday", "anniversary"})
#: Boolean values of a custom field: what is accepted and how it is kept.
BOOLEANS = {"true": "true", "1": "true", "false": "false", "0": "false"}
#: A consent may be dated a little ahead of the server's clock (a tablet's clock), not more.
CLOCK_SKEW = timedelta(minutes=5)
#: What the export put in front of a cell a spreadsheet would run (queries.FORMULA_STARTS).
EXPORT_GUARD = ("'=", "'+", "'-", "'@")


def _actor(ctx: OperationContext) -> str:
    """Who writes, as people read it: the user's name (or email), never their account id; the
    platform itself (``system_context``) by its own mark."""
    actor = ctx.actor
    if actor is None:
        return ""
    if not hasattr(actor, "get_username"):
        return str(actor)[:128]
    return (actor.get_full_name() or actor.email or actor.get_username())[:128]


def _e164(raw: str, ctx: OperationContext, field: str = "phone") -> str:
    try:
        return to_e164(raw, business_country(ctx))
    except InvalidPhone:
        raise InvalidPayload(
            PHONE_INVALID, code="customer.phone_invalid", fields={field: PHONE_INVALID}
        ) from None


def _changes(instance, sent: dict) -> dict:
    """The sent values that differ from ``instance``'s."""
    return {
        field: value
        for field, value in sent.items()
        if getattr(instance, field) != value
    }


def _save_named(instance, message, code: str) -> None:
    """Saves a group, tag or field; a name already taken among the active ones is a 409 under «name»."""
    try:
        with transaction.atomic():
            instance.save()
    except IntegrityError as exc:
        if "_name_unique" not in str(exc):
            raise
        raise Conflict(message, code=code, fields={"name": message}) from None


# ── Custom field values (customers#13) ──────────────────────────────────────────────────────────


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
    customer: Customer, sent: list[FieldValueIn]
) -> dict[UUID, str]:
    """The values to keep per field, or ``InvalidPayload`` with every problem under its field.

    Only active fields count: an unknown or inactive one is unavailable. Every required field must
    end up with a value, the one sent or the one stored.
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
    for field in fields.values():
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


# ── Customers ───────────────────────────────────────────────────────────────────────────────────


def lock_rows(model, ids) -> list[UUID]:
    """Locks the cards, groups, tags or custom fields ``ids`` (deleted cards too) in id order; the ids of those
    still there.

    Every write on a card locks it before what hangs from it (its activity, purchases, consents, values,
    groups, tags, health data and orders), and then the groups, tags or fields it points at; the Hub admin's
    «Delete» (admin.py) locks them too before Django gathers what hangs from them and deletes it, as the
    business's own «Delete» of a group, a tag or a field does. Whichever comes second waits for the other:
    the deletion takes what the write added, or the write finds the row gone, instead of failing at its
    COMMIT. Several rows are taken in id order, as a merge takes its two cards.
    """
    rows = model.objects.select_for_update().filter(pk__in=ids).order_by("id")
    return list(rows.values_list("id", flat=True))


def lock_customers(ids) -> list[UUID]:
    """Locks the cards ``ids`` as an erasure and a merge take them: a card before the duplicates merged into it
    (each wave in id order); the ids of those still there.

    The Hub admin's «Delete selected» of a card and its duplicate, in plain id order, could hold the duplicate
    while an erasure of the card held the card and went for the duplicate: each waited for the other.
    """
    pending, locked = set(ids), []
    while pending:
        # The cards not merged into another pending one (all of them if they point at each other).
        wave = set(
            Customer.objects.filter(pk__in=pending)
            .exclude(merged_into_id__in=pending)
            .values_list("id", flat=True)
        ) or set(pending)
        locked += lock_rows(Customer, wave)
        pending -= wave
    return locked


@operation(
    "customer.customer.create",
    kind="command",
    permission="customer.manage",
    input=CustomerIn,
    output=CustomerDetailOut,
    ai={
        "description": "Creates a new customer; only the name is required. The phone is saved in international "
        "format (+34600111222), a number without prefix read in the business's country; one that is not a phone "
        "of its country is refused.",
        "risk": "normal",
    },
)
def create_customer(ctx: OperationContext, data: CustomerIn) -> dict:
    values = data.model_dump()
    values["phone"] = _e164(values["phone"], ctx)
    customer = Customer.objects.create(**values)
    record_event(ctx, events.CUSTOMER_CREATED, {"id": str(customer.id)})
    return load_detail(customer)


@operation(
    "customer.customer.update",
    kind="command",
    permission="customer.manage",
    input=CustomerPatchIn,
    output=CustomerDetailOut,
    ai={
        "description": "Updates a customer's card, by its id or its exact name, phone or email: only the fields "
        "sent change, and with field_values its custom fields too, in one write: required fields must end up "
        "filled and values must match their type, or nothing is saved.",
        "risk": "normal",
    },
)
def update_customer(ctx: OperationContext, data: CustomerPatchIn) -> dict:
    customer = find_customer(data.id, data.customer, lock=True)
    sent = {
        field: value
        for field, value in data.model_dump(
            exclude_unset=True, exclude={"id", "customer", "field_values"}
        ).items()
        if value is not None or field in NULLABLE
    }
    if "phone" in sent:
        sent["phone"] = _e164(sent["phone"], ctx)
    kept = (
        _validated_field_values(customer, data.field_values)
        if data.field_values is not None
        else {}
    )
    changes = _changes(customer, sent)
    for field, value in changes.items():
        setattr(customer, field, value)
    values_changed = _apply_field_values(customer, kept)
    if changes or values_changed:
        customer.save(update_fields=[*changes, "updated_at"])
        record_event(ctx, events.CUSTOMER_UPDATED, {"id": str(customer.id)})
    return load_detail(customer)


def _field_message(error: dict) -> str:
    """One pydantic error of a row as the 422 of the API words it (``live.ninja.FIELD_MESSAGES``)."""
    context = error.get("ctx") or {}
    if error.get("type") in ("value_error", "assertion_error"):
        return str(context.get("error") or error.get("msg"))
    template = FIELD_MESSAGES.get(error.get("type"))
    try:
        return (
            str(template % context) if template is not None else str(error.get("msg"))
        )
    except KeyError, TypeError, ValueError:
        return str(error.get("msg"))


def _import_row(
    row: ImportRowIn, ctx: OperationContext
) -> tuple[dict, dict[str, str], dict[str, str]]:
    """A CSV row as the values of a new card, or the reason it is skipped, and what to review."""
    raw = {
        field: value[1:] if value.startswith(EXPORT_GUARD) else value
        for field, value in row.model_dump().items()
    }
    warnings: dict[str, str] = {}
    # A code or a name in Spanish or English, as the screen reads it (countries.country_from_text).
    written = raw["country"].strip()
    country = country_from_text(written)
    if written and not country:
        warnings["country"] = str(COUNTRY_IMPORTED_EMPTY)
    stage = raw["lifecycle_stage"].strip().lower()
    candidate = {
        **raw,
        "country": country,
        # «customer» is how the product's older files called an active customer.
        "lifecycle_stage": "active" if stage in ("", "customer") else stage,
        "source": raw["source"].strip().lower() or Customer.Source.IMPORT,
        "preferred_channel": raw["preferred_channel"].strip().lower()
        or Customer.PreferredChannel.NONE,
        "birthday": raw["birthday"].strip() or None,
        "anniversary": raw["anniversary"].strip() or None,
    }
    try:
        values = CustomerIn.model_validate(candidate).model_dump()
    except pydantic.ValidationError as exc:
        errors: dict[str, str] = {}
        for error in exc.errors():
            errors.setdefault(
                str(error["loc"][0]) if error["loc"] else "name", _field_message(error)
            )
        return {}, errors, warnings
    try:
        values["phone"] = to_e164(values["phone"], business_country(ctx))
    except InvalidPhone:
        return {}, {"phone": str(PHONE_INVALID)}, warnings
    return values, {}, warnings


def _already_imported(values: dict) -> bool:
    """A live card with the same name, phone and email: the row was imported before (services#152).

    Only the three together: two people may share a phone or an email (CUSTOMER-F12).
    """
    return (
        Customer.objects.live()
        .filter(
            name__iexact=values["name"],
            phone=values["phone"],
            email__iexact=values["email"],
        )
        .exists()
    )


@operation(
    "customer.customer.import",
    kind="command",
    permission="customer.manage",
    input=ImportIn,
    output=ImportOut,
    ai={
        "description": "Creates customers in bulk from up to 50 rows of a CSV file: each row is checked on its own, "
        "the bad ones are skipped with their reason and the rest are created without consent.",
        "risk": "high",
    },
)
def import_customers(ctx: OperationContext, data: ImportIn) -> dict:
    rows = []
    for index, row in enumerate(data.rows):
        values, errors, warnings = _import_row(row, ctx)
        customer_id = None
        if not errors and _already_imported(values):
            errors = {"name": str(ALREADY_IMPORTED)}
        if not errors:
            customer = Customer.objects.create(**values)
            record_event(ctx, events.CUSTOMER_CREATED, {"id": str(customer.id)})
            customer_id = customer.id
        rows.append(
            {"index": index, "id": customer_id, "errors": errors, "warnings": warnings}
        )
    created = sum(1 for row in rows if row["id"] is not None)
    return {"created": created, "skipped": len(rows) - created, "rows": rows}


def _named_ids(
    model, ids: list[UUID], names: list[str], missing, code: str, field: str
) -> set[UUID]:
    """The ids of the groups or tags sent by id or by name, held until the COMMIT; one that does not exist
    (or that was deleted meanwhile) saves nothing."""
    wanted = set(ids)
    for name in names:
        match = (
            model.objects.filter(name__iexact=name)
            .order_by("-is_active", "id")
            .values_list("id", flat=True)
            .first()
        )
        if match is None:
            raise InvalidPayload(missing, code=code, fields={field: missing})
        wanted.add(match)
    if wanted - set(lock_rows(model, wanted)):
        raise InvalidPayload(missing, code=code, fields={field: missing})
    return wanted


def _set_members(
    ctx: OperationContext, customer: Customer, relation: str, ids: set[UUID], event: str
) -> dict:
    members = getattr(customer, relation)
    if set(members.values_list("id", flat=True)) != ids:
        members.set(ids)
        customer.save(update_fields=["updated_at"])
        record_event(ctx, event, {"id": str(customer.id)})
    return load_detail(customer)


@operation(
    "customer.customer.set_groups",
    kind="command",
    permission="customer.manage",
    input=SetGroupsIn,
    output=CustomerDetailOut,
    ai={
        "description": "Sets a customer's groups, by id or by name, replacing the previous selection; an empty "
        "selection takes them all off.",
        "risk": "normal",
    },
)
def set_groups(ctx: OperationContext, data: SetGroupsIn) -> dict:
    customer = find_customer(data.id, data.customer, lock=True)
    ids = _named_ids(
        CustomerGroup,
        data.group_ids,
        data.groups,
        GROUP_UNAVAILABLE,
        "customer.group_unavailable",
        "groups",
    )
    return _set_members(ctx, customer, "groups", ids, events.CUSTOMER_GROUPS_CHANGED)


@operation(
    "customer.customer.set_tags",
    kind="command",
    permission="customer.manage",
    input=SetTagsIn,
    output=CustomerDetailOut,
    ai={
        "description": "Sets a customer's tags, by id or by name, replacing the previous selection; an empty "
        "selection takes them all off.",
        "risk": "normal",
    },
)
def set_tags(ctx: OperationContext, data: SetTagsIn) -> dict:
    customer = find_customer(data.id, data.customer, lock=True)
    ids = _named_ids(
        CustomerTag,
        data.tag_ids,
        data.tags,
        TAG_UNAVAILABLE,
        "customer.tag_unavailable",
        "tags",
    )
    return _set_members(ctx, customer, "tags", ids, events.CUSTOMER_TAGS_CHANGED)


@operation(
    "customer.customer.delete",
    kind="command",
    permission="customer.delete",
    input=CustomerRefIn,
    output=DeletedOut,
    ai={
        "description": "Deletes a customer's card: it leaves every list, the till and the phone lookup, but keeps "
        "its data, purchases and orders (erasing personal data is customer.customer.erase). Repeating it on a "
        "card already gone answers well.",
        "risk": "high",
    },
)
def delete_customer(ctx: OperationContext, data: CustomerRefIn) -> dict:
    customer = find_customer(data.id, data.customer, lock=True, live=False)
    if customer.deleted_at is None:
        customer.deleted_at = timezone.now()
        customer.is_active = False
        customer.save(update_fields=["deleted_at", "is_active", "updated_at"])
    record_event(ctx, events.CUSTOMER_DELETED, {"id": str(customer.id)})
    return {"id": customer.id}


@operation(
    "customer.customer.merge",
    kind="command",
    permission="customer.merge",
    input=MergeIn,
    output=CustomerDetailOut,
    ai={
        "description": "Merges a duplicate card (absorbed) into the one that stays: the survivor keeps its data and "
        "fills only its empty fields, notes are appended and figures summed; activity, custom values, groups, tags, "
        "purchases, orders and consent move to it, and the duplicate is retired. Cannot be undone.",
        "risk": "high",
    },
)
def merge_customers(ctx: OperationContext, data: MergeIn) -> dict:
    survivor_id = find_customer(data.id, data.customer).id
    absorbed_id = find_customer(data.absorbed_id, data.absorbed).id
    if survivor_id == absorbed_id:
        raise InvalidPayload(
            SAME_CUSTOMER,
            code="customer.same_customer",
            fields={"absorbed_id": SAME_CUSTOMER},
        )
    # Both rows locked in one order, so two merges of the same pair never wait for each other.
    cards = (
        Customer.objects.live()
        .select_for_update()
        .filter(pk__in=[survivor_id, absorbed_id])
    )
    locked = {customer.id: customer for customer in cards.order_by("pk")}
    if len(locked) < 2:  # one of them went between the lookup and the lock
        raise NotFound(CUSTOMER_UNAVAILABLE, code=CUSTOMER_UNAVAILABLE_CODE)
    survivor, absorbed = locked[survivor_id], locked[absorbed_id]
    for field in MERGE_FILLED:
        if not getattr(survivor, field):
            setattr(survivor, field, getattr(absorbed, field))
    survivor.birthday = survivor.birthday or absorbed.birthday
    survivor.anniversary = survivor.anniversary or absorbed.anniversary
    if survivor.preferred_channel == Customer.PreferredChannel.NONE:
        survivor.preferred_channel = absorbed.preferred_channel
    survivor.notes = "\n".join(
        note for note in (survivor.notes, absorbed.notes) if note
    )
    survivor.total_purchases += absorbed.total_purchases
    survivor.total_spent += absorbed.total_spent
    survivor.last_purchase_at = max(
        (
            moment
            for moment in (survivor.last_purchase_at, absorbed.last_purchase_at)
            if moment
        ),
        default=None,
    )
    survivor.save()

    Activity.objects.filter(customer=absorbed).update(customer=survivor)
    Purchase.objects.filter(customer=absorbed).update(customer=survivor)
    Consent.objects.filter(customer=absorbed).update(customer=survivor)
    OrderLink.objects.filter(customer=absorbed).update(customer=survivor)
    survivor_fields = CustomFieldValue.objects.filter(customer=survivor).values_list(
        "field_id", flat=True
    )
    CustomFieldValue.objects.filter(customer=absorbed).exclude(
        field_id__in=list(survivor_fields)
    ).update(customer=survivor)
    # The duplicate's groups and tags are held before the survivor points at them (as setting them does).
    survivor.groups.add(*lock_rows(CustomerGroup, absorbed.groups.values("id")))
    survivor.tags.add(*lock_rows(CustomerTag, absorbed.tags.values("id")))
    absorbed.groups.clear()
    absorbed.tags.clear()
    _merge_health(survivor, absorbed)

    # The cards merged into the duplicate before now point at the survivor: the chain stays flat.
    Customer.objects.filter(merged_into=absorbed).update(merged_into=survivor)
    absorbed.deleted_at = timezone.now()
    absorbed.is_active = False
    absorbed.merged_into = survivor
    absorbed.total_purchases = absorbed.total_spent = 0
    absorbed.last_purchase_at = None
    absorbed.save()
    Activity.objects.create(
        customer=survivor,
        kind=Activity.Kind.MERGED,
        related_id=str(absorbed.id),
        related_type="customer",
        data={"absorbed_id": str(absorbed.id)},
        actor=_actor(ctx),
    )
    record_event(
        ctx,
        events.CUSTOMER_MERGED,
        {"id": str(survivor.id), "absorbed_id": str(absorbed.id)},
    )
    return load_detail(survivor)


def _merge_health(survivor: Customer, absorbed: Customer) -> None:
    """The survivor keeps its health data and fills its gaps with the duplicate's (CUSTOMER-F13, F32).

    Their consent facts already moved: if the last health decision of the person is not a grant, no
    health data stays.
    """
    duplicate = HealthRecord.objects.filter(customer=absorbed).first()
    own = HealthRecord.objects.filter(customer=survivor).first()
    if duplicate and own:
        own.allergies = own.allergies or duplicate.allergies
        if not own.sensitivity_test_on:
            own.sensitivity_test_on = duplicate.sensitivity_test_on
            own.sensitivity_test_result = duplicate.sensitivity_test_result
        own.save()
        duplicate.delete()
    elif duplicate:
        duplicate.customer = survivor
        duplicate.save(update_fields=["customer"])
    fact = health_consent(survivor)
    if fact is None or fact.state != Consent.State.GRANTED:
        HealthRecord.objects.filter(customer=survivor).delete()


@operation(
    "customer.customer.erase",
    kind="command",
    permission="customer.erase",
    input=EraseIn,
    output=ErasedOut,
    ai={
        "description": "GDPR erasure of a customer's personal data: the card keeps its id and figures, its contact, "
        "tax and address data, notes, activity, custom values and memberships are erased, and one audit entry "
        "(who, when, why) stays. Purchases and orders are kept. Irreversible; repeating it changes nothing.",
        "risk": "high",
    },
)
def erase_customer(ctx: OperationContext, data: EraseIn) -> dict:
    customer = find_customer(data.id, data.customer, lock=True, live=False)
    # The same person's duplicates merged into this card keep their own data (CUSTOMER-F13):
    # erasing the person erases them too, however deep the chain, all locked in this transaction.
    cards, pending = [customer], [customer.id]
    while pending:
        absorbed = list(
            Customer.objects.select_for_update()
            .filter(merged_into_id__in=pending)
            .exclude(pk__in=[card.id for card in cards])
            .order_by("pk")
        )
        cards += absorbed
        pending = [card.id for card in absorbed]
    for card in cards:
        _erase_card(ctx, card, data.reason)
    return {"id": customer.id}


def _erase_card(ctx: OperationContext, customer: Customer, reason: str) -> None:
    """Erases one locked card once (repeating it writes nothing) and announces it every time."""
    if customer.erased_at is None:
        now = timezone.now()
        for field in (*MERGE_FILLED, "notes"):
            setattr(customer, field, "")
        customer.name = ERASED_NAME
        customer.birthday = customer.anniversary = None
        customer.preferred_channel = Customer.PreferredChannel.NONE
        customer.is_active = False
        customer.deleted_at = customer.deleted_at or now
        customer.erased_at = now
        customer.save()
        customer.activity.all().delete()
        customer.field_values.all().delete()
        HealthRecord.objects.filter(customer=customer).delete()
        customer.groups.clear()
        customer.tags.clear()
        customer.consents.update(contact_point="", evidence="", reason="")
        Activity.objects.create(
            customer=customer,
            kind=Activity.Kind.ERASED,
            text=reason,
            related_id=str(customer.id),
            related_type="customer",
            data={"scope": ERASE_SCOPE, "retained": ERASE_RETAINED},
            actor=_actor(ctx),
        )
    record_event(ctx, events.CUSTOMER_ERASED, {"id": str(customer.id)})


# ── Notes and activity ──────────────────────────────────────────────────────────────────────────


@operation(
    "customer.note.add",
    kind="command",
    permission="customer.manage",
    input=NoteIn,
    output=ActivityRow,
    ai={
        "description": "Adds a note to a customer's card, by its id or exact name, phone or email; the note shows "
        "at the top of its activity with who wrote it and when.",
        "risk": "normal",
    },
)
def add_note(ctx: OperationContext, data: NoteIn) -> Activity:
    customer = find_customer(data.customer_id, data.customer, lock=True)
    entry = Activity.objects.create(
        customer=customer,
        kind=Activity.Kind.NOTE_ADDED,
        title=data.title,
        text=data.content,
        data={"author_name": data.author_name} if data.author_name else {},
        related_type="note",
        actor=_actor(ctx),
    )
    record_event(
        ctx, events.NOTE_ADDED, {"id": str(entry.id), "customer_id": str(customer.id)}
    )
    return entry


@operation(
    "customer.activity.add",
    kind="command",
    permission="customer.record_activity",
    input=ActivityIn,
    output=ActivityRow,
    ai={
        "description": "Records an entry of another app in a customer's activity history (a visit, a booking), "
        "with that app's own key, title and data.",
        "risk": "normal",
    },
)
def add_activity(ctx: OperationContext, data: ActivityIn) -> Activity:
    customer = find_customer(data.customer_id, data.customer, lock=True)
    entry = Activity.objects.create(
        customer=customer,
        kind=data.kind,
        title=data.title,
        text=data.text,
        data=data.data,
        related_id=data.related_id,
        related_type=data.related_type,
        actor=_actor(ctx),
    )
    record_event(
        ctx,
        events.ACTIVITY_RECORDED,
        {"id": str(entry.id), "customer_id": str(customer.id)},
    )
    return entry


# ── Consent (customers#10) ──────────────────────────────────────────────────────────────────────


def _contact_point(customer: Customer, channel: str) -> str:
    """The card's address for ``channel`` right now: its email, its phone or its postal address."""
    if channel == Consent.Channel.EMAIL:
        return customer.email
    if channel == Consent.Channel.POSTAL:
        town = f"{customer.postal_code} {customer.city}".strip()
        return ", ".join(
            part for part in (customer.address, town, customer.country) if part
        )
    return customer.phone


def _record_consent(ctx: OperationContext, data, state: str) -> Consent:
    customer = find_customer(data.customer_id, data.customer, lock=True)
    now = timezone.now()
    occurred_at = data.occurred_at or now
    if occurred_at > now + CLOCK_SKEW:
        raise InvalidPayload(
            DATE_IN_FUTURE,
            code="customer.date_in_future",
            fields={"occurred_at": DATE_IN_FUTURE},
        )
    granted = state == Consent.State.GRANTED
    fact = Consent.objects.create(
        customer=customer,
        purpose=data.purpose,
        channel=data.channel,
        state=state,
        # Always the card's own address: the proof names the real contact (WORKBOOK F14).
        contact_point=_contact_point(customer, data.channel),
        source=data.source,
        notice_text=data.notice_text if granted else "",
        notice_version=data.notice_version if granted else "",
        evidence=data.evidence,
        reason="" if granted else data.reason,
        recorded_by=_actor(ctx),
        occurred_at=occurred_at,
        created_at=now,
    )
    Activity.objects.create(
        customer=customer,
        kind=Activity.Kind.CONSENT_GRANTED
        if granted
        else Activity.Kind.CONSENT_WITHDRAWN,
        text=fact.notice_text if granted else fact.reason,
        related_id=str(fact.id),
        related_type="consent",
        data={
            "purpose": fact.purpose,
            "channel": fact.channel,
            "source": fact.source,
            "notice_version": fact.notice_version,
            "occurred_at": occurred_at.isoformat(),
        },
        actor=_actor(ctx),
    )
    event = events.CONSENT_GRANTED if granted else events.CONSENT_WITHDRAWN
    record_event(
        ctx,
        event,
        {"id": str(fact.id), "customer_id": str(customer.id), "channel": fact.channel},
    )
    return fact


@operation(
    "customer.consent.grant",
    kind="command",
    permission="customer.manage",
    input=ConsentGrantIn,
    output=ConsentRow,
    ai={
        "description": "Records that a customer GAVE consent for a purpose and channel, as a new fact with its "
        "evidence: the exact words shown and their version, where and when, the card's own address on that "
        "channel at that moment, and who wrote it down (from the session). Only after the customer said yes.",
        "risk": "normal",
    },
)
def grant_consent(ctx: OperationContext, data: ConsentGrantIn) -> Consent:
    return _record_consent(ctx, data, Consent.State.GRANTED)


@operation(
    "customer.consent.withdraw",
    kind="command",
    permission="customer.manage",
    input=ConsentWithdrawIn,
    output=ConsentRow,
    ai={
        "description": "Records that a customer WITHDREW consent for a purpose and channel, as a new fact in force "
        "at once, for the card's own address on that channel; the grant it revokes is kept. The reason is optional.",
        "risk": "normal",
    },
)
def withdraw_consent(ctx: OperationContext, data: ConsentWithdrawIn) -> Consent:
    return _record_consent(ctx, data, Consent.State.WITHDRAWN)


# ── Orders (CUSTOMER-F19) ───────────────────────────────────────────────────────────────────────


# ── Health data (CUSTOMER-F32) ──────────────────────────────────────────────────────────────────
# Special category data (GDPR art. 9): kept only while the card's last health decision is a grant,
# erased when it is withdrawn. No ``ai`` and no ``expose_api``: never for the assistant nor an API key.


def _health_fact(
    ctx: OperationContext, data, customer: Customer, state: str
) -> Consent:
    now = timezone.now()
    occurred_at = getattr(data, "occurred_at", None) or now
    if occurred_at > now + CLOCK_SKEW:
        raise InvalidPayload(
            DATE_IN_FUTURE,
            code="customer.date_in_future",
            fields={"occurred_at": DATE_IN_FUTURE},
        )
    granted = state == Consent.State.GRANTED
    fact = Consent.objects.create(
        customer=customer,
        purpose=HEALTH_PURPOSE,
        channel="",
        state=state,
        source=data.source,
        notice_text=data.notice_text if granted else "",
        notice_version=data.notice_version if granted else "",
        evidence=data.evidence if granted else "",
        reason="" if granted else data.reason,
        recorded_by=_actor(ctx),
        occurred_at=occurred_at,
        created_at=now,
    )
    Activity.objects.create(
        customer=customer,
        kind=Activity.Kind.HEALTH_CONSENT_GRANTED
        if granted
        else Activity.Kind.HEALTH_CONSENT_WITHDRAWN,
        text=fact.notice_text if granted else fact.reason,
        related_id=str(fact.id),
        related_type="consent",
        data={
            "purpose": HEALTH_PURPOSE,
            "source": fact.source,
            "notice_version": fact.notice_version,
            "occurred_at": occurred_at.isoformat(),
        },
        actor=_actor(ctx),
    )
    record_event(
        ctx,
        events.HEALTH_CONSENT_GRANTED if granted else events.HEALTH_CONSENT_WITHDRAWN,
        {"id": str(fact.id), "customer_id": str(customer.id)},
    )
    return fact


@operation(
    "customer.health.grant",
    kind="command",
    permission="customer.manage",
    input=HealthGrantIn,
    output=HealthOut,
)
def grant_health(ctx: OperationContext, data: HealthGrantIn) -> dict:
    customer = find_customer(data.customer_id, data.customer, lock=True)
    _health_fact(ctx, data, customer, Consent.State.GRANTED)
    return load_health(customer)


@operation(
    "customer.health.withdraw",
    kind="command",
    permission="customer.manage",
    input=HealthWithdrawIn,
    output=HealthOut,
)
def withdraw_health(ctx: OperationContext, data: HealthWithdrawIn) -> dict:
    customer = find_customer(data.customer_id, data.customer, lock=True)
    _health_fact(ctx, data, customer, Consent.State.WITHDRAWN)
    # Withdrawing the only ground to keep them erases them in the same step (GDPR arts. 7.3, 17.1.b).
    HealthRecord.objects.filter(customer=customer).delete()
    return load_health(customer)


@operation(
    "customer.health.update",
    kind="command",
    permission="customer.manage",
    input=HealthIn,
    output=HealthOut,
)
def update_health(ctx: OperationContext, data: HealthIn) -> dict:
    customer = find_customer(data.customer_id, data.customer, lock=True)
    fact = health_consent(customer)
    if fact is None or fact.state != Consent.State.GRANTED:
        raise Conflict(HEALTH_CONSENT_REQUIRED, code="customer.health_consent_required")
    if data.sensitivity_test_on and data.sensitivity_test_on > timezone.localdate():
        raise InvalidPayload(
            DATE_IN_FUTURE,
            code="customer.date_in_future",
            fields={"sensitivity_test_on": DATE_IN_FUTURE},
        )
    if data.sensitivity_test_result and not data.sensitivity_test_on:
        raise InvalidPayload(
            HEALTH_TEST_DATE_MISSING,
            code="customer.health_test_date_missing",
            fields={"sensitivity_test_on": HEALTH_TEST_DATE_MISSING},
        )
    values = {
        "allergies": data.allergies,
        "sensitivity_test_on": data.sensitivity_test_on,
        "sensitivity_test_result": data.sensitivity_test_result,
    }
    record = HealthRecord.objects.filter(customer=customer).first()
    if record is None:
        record = HealthRecord(customer=customer)
    elif not _changes(record, values):
        return load_health(customer)
    for field, value in values.items():
        setattr(record, field, value)
    record.updated_at = timezone.now()
    record.updated_by = _actor(ctx)
    record.save()
    # The timeline says it changed and who did it, never what: the data lives in its block only.
    Activity.objects.create(
        customer=customer,
        kind=Activity.Kind.HEALTH_UPDATED,
        related_id=str(record.id),
        related_type="health",
        actor=_actor(ctx),
    )
    record_event(
        ctx,
        events.HEALTH_UPDATED,
        {"id": str(record.id), "customer_id": str(customer.id)},
    )
    return load_health(customer)


@operation(
    "customer.order.link",
    kind="command",
    permission="customer.manage",
    input=OrderLinkIn,
    output=OrderCustomerOut,
    ai={
        "description": "Puts a customer on an open order (at most one per order; a new one replaces the old), or "
        "takes the customer off when none is given.",
        "risk": "normal",
    },
)
def link_order(ctx: OperationContext, data: OrderLinkIn) -> dict:
    unlinking = data.customer_id is None and not (data.customer or "").strip()
    # The card before the link, the order a merge takes them in (cards, then what hangs from them).
    customer = (
        None if unlinking else find_customer(data.customer_id, data.customer, lock=True)
    )
    link = OrderLink.objects.select_for_update().filter(order_id=data.order_id).first()
    if customer is None:
        if link is not None:
            link.delete()
            record_event(
                ctx,
                events.ORDER_UNLINKED,
                {"order_id": str(data.order_id), "customer_id": str(link.customer_id)},
            )
        return {"order_id": data.order_id, "customer_id": None}
    if link is None or link.customer_id != customer.id:
        OrderLink.objects.update_or_create(
            order_id=data.order_id,
            defaults={"customer": customer, "linked_at": timezone.now()},
        )
        record_event(
            ctx,
            events.ORDER_LINKED,
            {"order_id": str(data.order_id), "customer_id": str(customer.id)},
        )
    return {"order_id": data.order_id, "customer_id": customer.id}


# ── Purchases: the system's (CUSTOMER-F20, F21) ─────────────────────────────────────────────────

#: Where a purchase moves a card's stage, and where a void takes it back.
STAGE_AFTER_PURCHASE = {
    Customer.Stage.LEAD: Customer.Stage.FIRST_PURCHASE,
    Customer.Stage.PROSPECT: Customer.Stage.FIRST_PURCHASE,
    Customer.Stage.FIRST_PURCHASE: Customer.Stage.ACTIVE,
    Customer.Stage.AT_RISK: Customer.Stage.ACTIVE,
    Customer.Stage.DORMANT: Customer.Stage.ACTIVE,
}


def _stage_after_void(stage: str, purchases_left: int) -> str:
    if purchases_left <= 0 and stage in (
        Customer.Stage.FIRST_PURCHASE,
        Customer.Stage.ACTIVE,
    ):
        return Customer.Stage.LEAD
    if purchases_left == 1 and stage == Customer.Stage.ACTIVE:
        return Customer.Stage.FIRST_PURCHASE
    return stage


@operation(
    "customer.purchase.record",
    kind="command",
    # Declared by no app: only the system context (``*``) holds it, as the product's internal commands.
    permission="customer.record_purchase",
    input=PurchaseRecordIn,
    output=PurchaseRecordOut,
    ai={
        "description": "System only: records a paid sale in its customer's history once (the same sale twice counts "
        "once), adding it to the purchases, the spend and the last purchase and moving the stage forward.",
        "risk": "high",
    },
)
def record_purchase(ctx: OperationContext, data: PurchaseRecordIn) -> dict:
    nothing = {"sale_id": data.sale_id, "recorded": False}
    if data.customer_id is None:
        return nothing
    customer = (
        Customer.objects.live().select_for_update().filter(pk=data.customer_id).first()
    )
    if customer is None or (
        data.sale_id is not None
        and Purchase.objects.filter(sale_id=data.sale_id).exists()
    ):
        return nothing
    at = data.purchased_at or timezone.now()
    purchase = Purchase.objects.create(
        customer=customer,
        sale_id=data.sale_id,
        amount=data.total,
        currency=data.currency,
        recorded_at=at,
    )
    customer.total_purchases += 1
    customer.total_spent += data.total
    customer.last_purchase_at = max(
        moment for moment in (customer.last_purchase_at, at) if moment
    )
    customer.lifecycle_stage = STAGE_AFTER_PURCHASE.get(
        customer.lifecycle_stage, customer.lifecycle_stage
    )
    customer.save(
        update_fields=[
            "total_purchases",
            "total_spent",
            "last_purchase_at",
            "lifecycle_stage",
            "updated_at",
        ]
    )
    Activity.objects.create(
        customer=customer,
        kind=Activity.Kind.PURCHASE_RECORDED,
        related_id=str(data.sale_id or purchase.id),
        related_type="sale",
        data={"amount": data.total, "currency": data.currency},
        actor=_actor(ctx),
    )
    sale = str(data.sale_id) if data.sale_id else None
    record_event(
        ctx,
        events.PURCHASE_RECORDED,
        {"customer_id": str(customer.id), "sale_id": sale},
    )
    return {"sale_id": data.sale_id, "recorded": True}


@operation(
    "customer.purchase.void",
    kind="command",
    permission="customer.record_purchase",
    input=PurchaseVoidIn,
    output=PurchaseVoidOut,
    ai={
        "description": "System only: when a sale is voided, marks its purchase as voided (kept in the history), takes "
        "it off the purchases and the spend, recomputes the last purchase and steps the stage back. Once.",
        "risk": "high",
    },
)
def void_purchase(ctx: OperationContext, data: PurchaseVoidIn) -> dict:
    nothing = {"sale_id": data.sale_id, "voided": False}
    locked = _locked_purchase(data.sale_id)
    if locked is None:
        return nothing
    customer, purchase = locked
    purchase.status = Purchase.Status.VOIDED
    purchase.voided_at = timezone.now()
    purchase.void_reason = data.reason
    purchase.save(update_fields=["status", "voided_at", "void_reason"])
    customer.total_purchases = max(customer.total_purchases - 1, 0)
    customer.total_spent -= purchase.amount
    customer.last_purchase_at = customer.purchases.filter(
        status=Purchase.Status.CONFIRMED
    ).aggregate(last=Max("recorded_at"))["last"]
    customer.lifecycle_stage = _stage_after_void(
        customer.lifecycle_stage, customer.total_purchases
    )
    customer.save(
        update_fields=[
            "total_purchases",
            "total_spent",
            "last_purchase_at",
            "lifecycle_stage",
            "updated_at",
        ]
    )
    if customer.erased_at is None:  # an erased card's timeline keeps only its erasure
        Activity.objects.create(
            customer=customer,
            kind=Activity.Kind.PURCHASE_VOIDED,
            text=data.reason,
            related_id=str(data.sale_id),
            related_type="sale",
            data={"amount": purchase.amount, "currency": purchase.currency},
            actor=_actor(ctx),
        )
    record_event(
        ctx,
        events.PURCHASE_VOIDED,
        {"customer_id": str(customer.id), "sale_id": str(data.sale_id)},
    )
    return {"sale_id": data.sale_id, "voided": True}


#: How many times a void follows a purchase that a merge moved to another card meanwhile.
VOID_ATTEMPTS = 3


@operation(
    "customer.purchase.refund",
    kind="command",
    permission="customer.record_purchase",
    input=PurchaseRefundIn,
    output=PurchaseRefundOut,
    ai={
        "description": "System only: when a paid sale is refunded (all or part), records the refund as a line of "
        "its own in its customer's history and takes what came back off the spend; the purchases, the last "
        "purchase and the stage stay. Once per refund.",
        "risk": "high",
    },
)
def refund_purchase(ctx: OperationContext, data: PurchaseRefundIn) -> dict:
    nothing = {"sale_id": data.sale_id, "refund_id": data.refund_id, "refunded": False}
    # The card first, then its purchase (the order a merge locks them in); then the refund, checked
    # under that lock so a repeated delivery never counts twice.
    locked = _locked_purchase(data.sale_id)
    if locked is None or Purchase.objects.filter(refund_id=data.refund_id).exists():
        return nothing
    customer, purchase = locked
    Purchase.objects.create(
        customer=customer,
        sale_id=data.sale_id,
        refund_id=data.refund_id,
        amount=-data.total,
        currency=purchase.currency,
        status=Purchase.Status.REFUNDED,
        recorded_at=data.refunded_at or timezone.now(),
        void_reason=data.reason,
    )
    customer.total_spent -= data.total
    customer.save(update_fields=["total_spent", "updated_at"])
    if customer.erased_at is None:  # an erased card's timeline keeps only its erasure
        Activity.objects.create(
            customer=customer,
            kind=Activity.Kind.PURCHASE_REFUNDED,
            text=data.reason,
            related_id=str(data.refund_id),
            related_type="refund",
            data={"amount": data.total, "currency": purchase.currency},
            actor=_actor(ctx),
        )
    record_event(
        ctx,
        events.PURCHASE_REFUNDED,
        {
            "customer_id": str(customer.id),
            "sale_id": str(data.sale_id),
            "refund_id": str(data.refund_id),
        },
    )
    return {"sale_id": data.sale_id, "refund_id": data.refund_id, "refunded": True}


def _locked_purchase(sale_id: UUID) -> tuple[Customer, Purchase] | None:
    """The card and the paid purchase of ``sale_id``, both locked, the card first; ``None`` if none.

    A merge locks the cards and then moves their purchases: locking the purchase first and the card
    after would make the two wait for each other. So the purchase is read without a lock, its card
    is locked, and the purchase is read again, locked, checking it is still that card's and paid. A
    card the Hub admin deleted in between took its purchases with it: the purchase is looked for
    again, as one a merge moved.
    """
    for _attempt in range(VOID_ATTEMPTS):
        found = (
            Purchase.objects.filter(sale_id=sale_id, status=Purchase.Status.CONFIRMED)
            .values_list("customer_id", flat=True)
            .first()
        )
        if found is None:
            return None
        customer = Customer.objects.select_for_update().filter(pk=found).first()
        if customer is None:
            continue
        purchase = (
            Purchase.objects.select_for_update()
            .filter(
                sale_id=sale_id, customer=customer, status=Purchase.Status.CONFIRMED
            )
            .first()
        )
        if purchase is not None:
            return customer, purchase
    return None


# ── Groups, tags and custom fields ──────────────────────────────────────────────────────────────


def _patched(instance, data, exclude: set[str]) -> dict:
    sent = {
        field: value
        for field, value in data.model_dump(exclude_unset=True, exclude=exclude).items()
        if value is not None
    }
    changes = _changes(instance, sent)
    for field, value in changes.items():
        setattr(instance, field, value)
    return changes


def _with_count(instance):
    """A group or tag with how many live cards have it, as its list row shows it."""
    instance.customer_count = instance.customers.filter(deleted_at__isnull=True).count()
    return instance


@operation(
    "customer.group.create",
    kind="command",
    permission="customer.configure",
    input=GroupIn,
    output=GroupRow,
    ai={
        "description": "Creates a customer group (name unique among the active groups, description, color, order).",
        "risk": "normal",
    },
)
def create_group(ctx: OperationContext, data: GroupIn) -> dict:
    group = CustomerGroup(**data.model_dump())
    _save_named(group, GROUP_NAME_TAKEN, "customer.group_name_taken")
    record_event(ctx, events.GROUP_CREATED, {"id": str(group.id)})
    return _with_count(group)


@operation(
    "customer.group.update",
    kind="command",
    permission="customer.configure",
    input=GroupPatchIn,
    output=GroupRow,
    ai={
        "description": "Updates a customer group, by its id or current name: name, description, color, order, and whether it is active.",
        "risk": "normal",
    },
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
    permission="customer.delete",
    input=GroupRefIn,
    output=DeletedOut,
    ai={
        "description": "Deletes a customer group, by its id or name; the customers in it lose it.",
        "risk": "high",
    },
)
def delete_group(ctx: OperationContext, data: GroupRefIn) -> dict:
    group = find_group(data.id, data.group, lock=True)
    group_id = group.id
    group.delete()
    record_event(ctx, events.GROUP_DELETED, {"id": str(group_id)})
    return {"id": group_id}


@operation(
    "customer.tag.create",
    kind="command",
    permission="customer.configure",
    input=TagIn,
    output=TagRow,
    ai={
        "description": "Creates a customer tag (name unique among the active tags, and color).",
        "risk": "normal",
    },
)
def create_tag(ctx: OperationContext, data: TagIn) -> dict:
    tag = CustomerTag(**data.model_dump())
    _save_named(tag, TAG_NAME_TAKEN, "customer.tag_name_taken")
    record_event(ctx, events.TAG_CREATED, {"id": str(tag.id)})
    return _with_count(tag)


@operation(
    "customer.tag.update",
    kind="command",
    permission="customer.configure",
    input=TagPatchIn,
    output=TagRow,
    ai={
        "description": "Updates a customer tag, by its id or current name: name, color and whether it is active.",
        "risk": "normal",
    },
)
def update_tag(ctx: OperationContext, data: TagPatchIn) -> dict:
    tag = find_tag(data.id, data.tag, lock=True)
    if _patched(tag, data, {"id", "tag"}):
        _save_named(tag, TAG_NAME_TAKEN, "customer.tag_name_taken")
        record_event(ctx, events.TAG_UPDATED, {"id": str(tag.id)})
    return _with_count(tag)


@operation(
    "customer.tag.delete",
    kind="command",
    permission="customer.delete",
    input=TagRefIn,
    output=DeletedOut,
    ai={
        "description": "Deletes a customer tag, by its id or name; the customers that had it lose it.",
        "risk": "high",
    },
)
def delete_tag(ctx: OperationContext, data: TagRefIn) -> dict:
    tag = find_tag(data.id, data.tag, lock=True)
    tag_id = tag.id
    tag.delete()
    record_event(ctx, events.TAG_DELETED, {"id": str(tag_id)})
    return {"id": tag_id}


@operation(
    "customer.field.create",
    kind="command",
    permission="customer.configure",
    input=FieldIn,
    output=FieldRow,
    ai={
        "description": "Creates a custom field on every customer's card: name, type (text, number, date, boolean, "
        "select, textarea), options of a select, order and whether it is required when the card is saved in full.",
        "risk": "normal",
    },
)
def create_field(ctx: OperationContext, data: FieldIn) -> CustomField:
    field = CustomField(**data.model_dump())
    _save_named(field, FIELD_NAME_TAKEN, "customer.field_name_taken")
    record_event(ctx, events.FIELD_CREATED, {"id": str(field.id)})
    return field


@operation(
    "customer.field.update",
    kind="command",
    permission="customer.configure",
    input=FieldPatchIn,
    output=FieldRow,
    ai={
        "description": "Updates a custom field, by its id or current name; its type cannot change once cards have "
        "values, and a select keeps at least one option.",
        "risk": "normal",
    },
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
    permission="customer.configure",
    input=FieldRefIn,
    output=DeletedOut,
    ai={
        "description": "Deletes a custom field, by its id or name, and the values every card had in it.",
        "risk": "high",
    },
)
def delete_field(ctx: OperationContext, data: FieldRefIn) -> dict:
    field = find_field(data.id, data.field, lock=True)
    field_id = field.id
    field.delete()
    record_event(ctx, events.FIELD_DELETED, {"id": str(field_id)})
    return {"id": field_id}
