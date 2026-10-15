"""Write operations of the customer app: one transaction each, with its event in the outbox.

The cases come from the product's batteries: ``create_walk_in.pg``, ``phone_e164.hub``,
``delete_guarded.pg``, ``merge.pg``, ``anonymize.pg``, ``activity_titles_are_keys.pg``,
``note_add_projects_activity.pg``, ``consent_ledger.pg``, ``orders_link.pg``,
``purchase_ledger.pg``, ``group_name_unique.pg``, ``tag_field_name_unique.pg``,
``groups_customer_count.pg`` and ``wasm_handlers.hub`` (bulk create, set groups).
"""

import json
import threading
import time
import uuid
from datetime import UTC, date, datetime, timedelta

import psycopg
import pytest
from django.db import connection, transaction
from django.utils import timezone
from live.context import system_context
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.customer import events
from apps.customer.models import (
    Activity,
    Consent,
    Customer,
    CustomerGroup,
    CustomerTag,
    CustomField,
    CustomFieldValue,
    OrderLink,
    Purchase,
)
from apps.customer.schemas import (
    ActivityIn,
    ActivityRow,
    ConsentGrantIn,
    ConsentRow,
    ConsentWithdrawIn,
    CustomerDetailOut,
    CustomerIn,
    CustomerPatchIn,
    DeletedOut,
    EraseIn,
    ErasedOut,
    FieldIn,
    FieldPatchIn,
    FieldRow,
    GroupIn,
    GroupPatchIn,
    GroupRefIn,
    GroupRow,
    ImportIn,
    ImportOut,
    MergeIn,
    NoteIn,
    OrderCustomerOut,
    OrderLinkIn,
    PurchaseRecordIn,
    PurchaseRefundIn,
    PurchaseRecordOut,
    PurchaseVoidIn,
    PurchaseVoidOut,
    SetGroupsIn,
    SetTagsIn,
    TagIn,
    TagPatchIn,
    TagRefIn,
    TagRow,
)
from apps.customer.schemas import (
    CustomerRefIn as RefIn,
)
from apps.customer.schemas import (
    FieldRefIn as FieldRef,
)

from .conftest import A, B, run

WAIT = 1.0
QUIET = 0.3
NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)


def outbox():
    return list(OutboxEvent.objects.values_list("name", "payload"))


def clear_outbox():
    OutboxEvent.objects.all().delete()


def card(name="Ana García", **fields):
    return Customer.objects.create(name=name, **fields)


def system(name, data):
    return get(name)(system_context(A), data)


def invalid(error):
    return (
        error.status,
        error.code,
        {field: str(message) for field, message in (error.fields or {}).items()},
    )


# Declarations


@pytest.mark.parametrize(
    ("name", "permission", "input", "output"),
    [
        ("customer.customer.create", "customer.manage", CustomerIn, CustomerDetailOut),
        (
            "customer.customer.update",
            "customer.manage",
            CustomerPatchIn,
            CustomerDetailOut,
        ),
        ("customer.customer.import", "customer.manage", ImportIn, ImportOut),
        (
            "customer.customer.set_groups",
            "customer.manage",
            SetGroupsIn,
            CustomerDetailOut,
        ),
        ("customer.customer.set_tags", "customer.manage", SetTagsIn, CustomerDetailOut),
        ("customer.customer.delete", "customer.delete", RefIn, DeletedOut),
        ("customer.customer.merge", "customer.merge", MergeIn, CustomerDetailOut),
        ("customer.customer.erase", "customer.erase", EraseIn, ErasedOut),
        ("customer.note.add", "customer.manage", NoteIn, ActivityRow),
        ("customer.activity.add", "customer.record_activity", ActivityIn, ActivityRow),
        ("customer.consent.grant", "customer.manage", ConsentGrantIn, ConsentRow),
        ("customer.consent.withdraw", "customer.manage", ConsentWithdrawIn, ConsentRow),
        ("customer.order.link", "customer.manage", OrderLinkIn, OrderCustomerOut),
        ("customer.group.create", "customer.configure", GroupIn, GroupRow),
        ("customer.group.update", "customer.configure", GroupPatchIn, GroupRow),
        ("customer.group.delete", "customer.delete", GroupRefIn, DeletedOut),
        ("customer.tag.create", "customer.configure", TagIn, TagRow),
        ("customer.tag.update", "customer.configure", TagPatchIn, TagRow),
        ("customer.tag.delete", "customer.delete", TagRefIn, DeletedOut),
        ("customer.field.create", "customer.configure", FieldIn, FieldRow),
        ("customer.field.update", "customer.configure", FieldPatchIn, FieldRow),
        ("customer.field.delete", "customer.configure", FieldRef, DeletedOut),
        (
            "customer.purchase.record",
            "customer.record_purchase",
            PurchaseRecordIn,
            PurchaseRecordOut,
        ),
        (
            "customer.purchase.void",
            "customer.record_purchase",
            PurchaseVoidIn,
            PurchaseVoidOut,
        ),
    ],
)
def test_declarations(name, permission, input, output):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output) == (
        "command",
        permission,
        input,
        output,
    )


# customer.customer.create (CUSTOMER-F01, F18, F26; create_walk_in.pg, phone_e164.hub)


@pytest.mark.django_db
def test_a_walk_in_is_created_from_a_name_and_announced():
    detail = run("customer.customer.create", CustomerIn(name="Ana"), "hub_employee")
    customer = Customer.objects.get()
    assert (
        detail.id,
        detail.name,
        detail.lifecycle_stage,
        detail.source,
        detail.preferred_channel,
    ) == (
        customer.id,
        "Ana",
        "lead",
        "walk_in",
        "none",
    )
    assert (detail.marketing_consent, detail.consent) == (False, [])
    assert outbox() == [(events.CUSTOMER_CREATED, {"id": str(customer.id)})]


@pytest.mark.django_db
def test_the_full_card_keeps_every_value_and_the_phone_in_e164():
    detail = run(
        "customer.customer.create",
        CustomerIn(
            name="Ana",
            phone="600 111 222",
            email="ana@example.com",
            company_name="ACME",
            country="es",
            birthday="1990-05-04",
            lifecycle_stage="vip",
            source="whatsapp",
            preferred_channel="whatsapp",
            avatar="https://example.com/a.png",
        ),
    )
    assert (detail.phone, detail.company_name, detail.country, detail.birthday) == (
        "+34600111222",
        "ACME",
        "ES",
        date(1990, 5, 4),
    )
    assert (
        detail.lifecycle_stage,
        detail.source,
        detail.preferred_channel,
        detail.avatar,
    ) == (
        "vip",
        "whatsapp",
        "whatsapp",
        "https://example.com/a.png",
    )


@pytest.mark.django_db
def test_a_phone_that_is_no_number_of_its_country_creates_nothing():
    with pytest.raises(InvalidPayload) as excinfo:
        run("customer.customer.create", CustomerIn(name="Ana", phone="600111"))
    status, code, fields = invalid(excinfo.value)
    assert (status, code, list(fields)) == (422, "customer.phone_invalid", ["phone"])
    assert fields["phone"].startswith("This is not a valid phone number of its country")
    assert not Customer.objects.exists() and outbox() == []


# customer.customer.update (CUSTOMER-F04)


@pytest.mark.django_db
def test_update_changes_only_what_was_sent_and_announces_it():
    ana = card("Ana", notes="keep me", email="old@example.com")
    detail = run(
        "customer.customer.update",
        CustomerPatchIn(id=ana.id, email="new@example.com", phone="+44 (0)7911 123456"),
    )
    assert (detail.email, detail.phone, detail.notes) == (
        "new@example.com",
        "+447911123456",
        "keep me",
    )
    assert outbox() == [(events.CUSTOMER_UPDATED, {"id": str(ana.id)})]


@pytest.mark.django_db
def test_update_by_the_customers_name_and_null_leaves_a_field_but_clears_a_date():
    ana = card("Ana", birthday=date(1990, 1, 1), city="Madrid")
    detail = run(
        "customer.customer.update",
        CustomerPatchIn(customer="ana", city=None, birthday=None, is_active=False),
    )
    assert (detail.city, detail.birthday, detail.is_active) == ("Madrid", None, False)
    ana.refresh_from_db()
    assert ana.birthday is None


@pytest.mark.django_db
def test_an_update_that_changes_nothing_announces_nothing():
    ana = card("Ana", phone="+34600111222")
    run(
        "customer.customer.update",
        CustomerPatchIn(id=ana.id, name="Ana", phone="600 111 222"),
    )
    assert outbox() == []


@pytest.mark.django_db
def test_an_update_with_a_bad_phone_changes_nothing():
    ana = card("Ana")
    with pytest.raises(InvalidPayload):
        run(
            "customer.customer.update",
            CustomerPatchIn(id=ana.id, name="Bea", phone="600 111 222 ext 12"),
        )
    ana.refresh_from_db()
    assert ana.name == "Ana" and outbox() == []


@pytest.mark.django_db
def test_a_card_that_is_gone_cannot_be_updated():
    gone = card("Gone", deleted_at=NOW)
    with pytest.raises(NotFound):
        run("customer.customer.update", CustomerPatchIn(id=gone.id, name="Back"))


# Custom field values on the update (customers#13)


@pytest.fixture
def fields(db):
    return {
        "allergies": CustomField.objects.create(name="Allergies", is_required=True),
        "visits": CustomField.objects.create(name="Visits", field_type="number"),
        "since": CustomField.objects.create(name="Since", field_type="date"),
        "vegan": CustomField.objects.create(name="Vegan", field_type="boolean"),
        "hair": CustomField.objects.create(
            name="Hair", field_type="select", options=["Short", "Long"]
        ),
        "old": CustomField.objects.create(name="Old", is_active=False),
    }


def values(customer):
    return dict(
        CustomFieldValue.objects.filter(customer=customer).values_list(
            "field__name", "value"
        )
    )


def field_values(fields, **sent):
    return [
        {"field_id": fields[name].id, "value": value} for name, value in sent.items()
    ]


@pytest.mark.django_db
def test_the_sheet_and_its_fields_are_saved_in_one_write(fields):
    ana = card("Ana")
    detail = run(
        "customer.customer.update",
        CustomerPatchIn(
            id=ana.id,
            notes="VIP",
            field_values=field_values(
                fields,
                allergies="Latex",
                visits="3.5",
                since="2024-02-29",
                vegan="true",
                hair="Long",
            ),
        ),
    )
    assert values(ana) == {
        "Allergies": "Latex",
        "Visits": "3.5",
        "Since": "2024-02-29",
        "Vegan": "true",
        "Hair": "Long",
    }
    assert {field.name: field.value for field in detail.custom_fields}["Hair"] == "Long"
    assert outbox() == [(events.CUSTOMER_UPDATED, {"id": str(ana.id)})]


@pytest.mark.django_db
def test_an_empty_value_clears_a_field_and_the_old_one_and_zero_still_read_as_booleans(
    fields,
):
    ana = card("Ana")
    CustomFieldValue.objects.create(
        customer=ana, field=fields["allergies"], value="Latex"
    )
    CustomFieldValue.objects.create(customer=ana, field=fields["visits"], value="3")
    run(
        "customer.customer.update",
        CustomerPatchIn(
            id=ana.id, field_values=field_values(fields, visits="", vegan="1")
        ),
    )
    assert values(ana) == {"Allergies": "Latex", "Vegan": "true"}


@pytest.mark.django_db
def test_a_required_field_is_satisfied_by_its_stored_value(fields):
    ana = card("Ana")
    CustomFieldValue.objects.create(
        customer=ana, field=fields["allergies"], value="Latex"
    )
    run(
        "customer.customer.update",
        CustomerPatchIn(id=ana.id, field_values=field_values(fields, hair="Short")),
    )
    assert values(ana)["Hair"] == "Short"


@pytest.mark.django_db
def test_a_required_field_left_empty_rejects_the_whole_save(fields):
    ana = card("Ana")
    with pytest.raises(InvalidPayload) as excinfo:
        run(
            "customer.customer.update",
            CustomerPatchIn(
                id=ana.id, name="Bea", field_values=field_values(fields, hair="Short")
            ),
        )
    status, code, errors = invalid(excinfo.value)
    assert (status, code, errors) == (
        422,
        "customer.field_required",
        {f"field_values.{fields['allergies'].id}": "This field is required."},
    )
    ana.refresh_from_db()
    assert (ana.name, values(ana)) == ("Ana", {})


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("name", "value", "code", "message"),
    [
        ("visits", "three", "customer.field_invalid_number", "Enter a number."),
        ("visits", "nan", "customer.field_invalid_number", "Enter a number."),
        ("since", "2026-02-31", "customer.field_invalid_date", "Enter a valid date."),
        ("since", "14/10/2026", "customer.field_invalid_date", "Enter a valid date."),
        ("vegan", "maybe", "customer.field_invalid_boolean", "Choose yes or no."),
        (
            "hair",
            "Purple",
            "customer.field_invalid_option",
            "Choose one of the options.",
        ),
    ],
)
def test_a_value_that_does_not_fit_its_type_rejects_the_save(
    fields, name, value, code, message
):
    ana = card("Ana")
    sent = field_values(fields, allergies="Latex", **{name: value})
    with pytest.raises(InvalidPayload) as excinfo:
        run("customer.customer.update", CustomerPatchIn(id=ana.id, field_values=sent))
    assert invalid(excinfo.value) == (
        422,
        code,
        {f"field_values.{fields[name].id}": message},
    )
    assert values(ana) == {}


@pytest.mark.django_db
def test_an_unknown_or_inactive_field_is_unavailable(fields):
    ana = card("Ana")
    for field_id in (fields["old"].id, uuid.uuid7()):
        with pytest.raises(InvalidPayload) as excinfo:
            run(
                "customer.customer.update",
                CustomerPatchIn(
                    id=ana.id, field_values=[{"field_id": field_id, "value": "x"}]
                ),
            )
        status, code, errors = invalid(excinfo.value)
        assert (status, code, errors[f"field_values.{field_id}"]) == (
            422,
            "customer.field_unavailable",
            "That field no longer exists.",
        )


@pytest.mark.django_db
def test_without_field_values_the_required_fields_are_not_checked(fields):
    # Creating a card and a plain edit never ask for the custom fields (CUSTOMER-F29).
    ana = card("Ana")
    assert (
        run("customer.customer.update", CustomerPatchIn(id=ana.id, city="Madrid")).city
        == "Madrid"
    )


# customer.customer.import (CUSTOMER-F08; wasm_handlers.hub bulk_create)


@pytest.mark.django_db
def test_import_creates_the_good_rows_and_skips_the_bad_ones_with_their_reason():
    result = run(
        "customer.customer.import",
        ImportIn(
            rows=[
                {
                    "name": "Ana",
                    "phone": "600 111 222",
                    "email": "ana@example.com",
                    "country": "es",
                },
                {"name": "", "email": "nobody@example.com"},
                {"name": "Bea", "email": "bea@"},
                {"name": "Carla", "phone": "600111"},
                {"name": "Dora", "country": "Spain", "lifecycle_stage": "customer"},
                {
                    "name": "Eva",
                    "lifecycle_stage": "vip",
                    "source": "referral",
                    "birthday": "1990-05-04",
                },
                {"name": "Fran", "lifecycle_stage": "boss"},
            ]
        ),
        "hub_employee",
    )
    assert (result.created, result.skipped) == (3, 4)
    assert [
        (row.index, row.id is not None, sorted(row.errors), sorted(row.warnings))
        for row in result.rows
    ] == [
        (0, True, [], []),
        (1, False, ["name"], []),
        (2, False, ["email"], []),
        (3, False, ["phone"], []),
        (4, True, [], []),
        (5, True, [], []),
        (6, False, ["lifecycle_stage"], []),
    ]
    assert str(result.rows[3].errors["phone"]).startswith(
        "This is not a valid phone number"
    )
    ana, dora, eva = (
        Customer.objects.get(name=name) for name in ("Ana", "Dora", "Eva")
    )
    assert (ana.phone, ana.country, ana.source, ana.lifecycle_stage) == (
        "+34600111222",
        "ES",
        "import",
        "active",
    )
    # A country named in English or Spanish is read as its code, as the screen does (customers#72).
    assert (dora.country, dora.lifecycle_stage) == ("ES", "active")
    assert (eva.source, eva.lifecycle_stage, eva.birthday) == (
        "referral",
        "vip",
        date(1990, 5, 4),
    )
    # One notice per created card, as a creation by hand: WhatsApp links their conversations.
    assert outbox() == [
        (events.CUSTOMER_CREATED, {"id": str(row.id)}) for row in result.rows if row.id
    ]


@pytest.mark.django_db
def test_import_reads_a_country_by_its_code_or_its_name_and_warns_when_it_names_none():
    # The same reading as the screen, for an import through the API or the assistant: a code, a name
    # in Spanish or English (case and accents aside), the Spanish regions as Spain; else, a warning.
    result = run(
        "customer.customer.import",
        ImportIn(
            rows=[
                {"name": "A", "country": "fr"},
                {"name": "B", "country": "España"},
                {"name": "C", "country": "alemania"},
                {"name": "D", "country": "United Kingdom"},
                {"name": "E", "country": "IC"},
                {"name": "F", "country": "Narnia"},
                {"name": "G", "country": "XK"},
            ]
        ),
    )
    assert result.created == 7
    assert [sorted(row.warnings) for row in result.rows] == [[], [], [], [], [], ["country"], ["country"]]
    assert dict(Customer.objects.values_list("name", "country")) == {
        "A": "FR",
        "B": "ES",
        "C": "DE",
        "D": "GB",
        "E": "ES",
        "F": "",
        "G": "",
    }


@pytest.mark.django_db
def test_import_takes_back_the_apostrophe_the_export_puts_in_front_of_a_formula():
    run(
        "customer.customer.import",
        ImportIn(rows=[{"name": "'=Ana", "phone": "'+34600111222"}]),
    )
    ana = Customer.objects.get()
    assert (ana.name, ana.phone) == ("=Ana", "+34600111222")


# customer.customer.set_groups / set_tags (CUSTOMER-F06)


@pytest.mark.django_db
def test_set_groups_replaces_the_selection_by_id_or_by_name():
    vip, wholesale = (
        CustomerGroup.objects.create(name="VIP"),
        CustomerGroup.objects.create(name="Wholesale"),
    )
    ana = card("Ana")
    detail = run(
        "customer.customer.set_groups",
        SetGroupsIn(id=ana.id, group_ids=[vip.id], groups=["wholesale"]),
    )
    assert set(detail.group_ids) == {vip.id, wholesale.id}
    assert outbox() == [(events.CUSTOMER_GROUPS_CHANGED, {"id": str(ana.id)})]
    clear_outbox()
    detail = run(
        "customer.customer.set_groups", SetGroupsIn(customer="Ana", groups=["VIP"])
    )
    assert detail.group_ids == [vip.id]
    run(
        "customer.customer.set_groups", SetGroupsIn(customer="Ana", group_ids=[vip.id])
    )  # the same: no notice
    assert outbox() == [(events.CUSTOMER_GROUPS_CHANGED, {"id": str(ana.id)})]
    run("customer.customer.set_groups", SetGroupsIn(id=ana.id))
    assert list(ana.groups.all()) == []


@pytest.mark.django_db
def test_a_group_that_no_longer_exists_saves_nothing():
    vip = CustomerGroup.objects.create(name="VIP")
    ana = card("Ana")
    ana.groups.add(vip)
    for sent in ({"group_ids": [uuid.uuid7()]}, {"groups": ["Nope"]}):
        with pytest.raises(InvalidPayload) as excinfo:
            run("customer.customer.set_groups", SetGroupsIn(id=ana.id, **sent))
        assert excinfo.value.code == "customer.group_unavailable"
    assert list(ana.groups.all()) == [vip]


@pytest.mark.django_db
def test_set_tags():
    moroso = CustomerTag.objects.create(name="Moroso")
    ana = card("Ana")
    assert run(
        "customer.customer.set_tags", SetTagsIn(id=ana.id, tags=["moroso"])
    ).tag_ids == [moroso.id]
    assert outbox() == [(events.CUSTOMER_TAGS_CHANGED, {"id": str(ana.id)})]
    with pytest.raises(InvalidPayload) as excinfo:
        run("customer.customer.set_tags", SetTagsIn(id=ana.id, tag_ids=[uuid.uuid7()]))
    assert excinfo.value.code == "customer.tag_unavailable"


# customer.customer.delete (CUSTOMER-F07; delete_guarded.pg)


@pytest.mark.django_db
def test_delete_keeps_the_data_and_announces_it():
    ana = card("Ana", email="ana@example.com")
    Purchase.objects.create(customer=ana, sale_id=uuid.uuid7(), amount=500)
    OrderLink.objects.create(order_id=uuid.uuid7(), customer=ana)
    assert run("customer.customer.delete", RefIn(id=ana.id)) == DeletedOut(id=ana.id)
    ana.refresh_from_db()
    assert ana.deleted_at is not None and ana.is_active is False
    assert (ana.email, ana.purchases.count(), ana.orders.count()) == (
        "ana@example.com",
        1,
        1,
    )
    assert outbox() == [(events.CUSTOMER_DELETED, {"id": str(ana.id)})]


@pytest.mark.django_db
def test_deleting_an_unknown_card_fails_and_announces_nothing():
    with pytest.raises(NotFound) as excinfo:
        run("customer.customer.delete", RefIn(id=uuid.uuid7()))
    assert excinfo.value.code == "customer.customer_unavailable"
    assert outbox() == []


@pytest.mark.django_db
def test_deleting_a_card_that_is_already_gone_answers_well_and_announces_again():
    gone = card("Gone", deleted_at=NOW)
    run("customer.customer.delete", RefIn(id=gone.id))
    gone.refresh_from_db()
    assert gone.deleted_at == NOW
    assert outbox() == [(events.CUSTOMER_DELETED, {"id": str(gone.id)})]


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["hub_manager", "hub_employee"])
def test_only_owner_and_admin_delete(role):
    ana = card("Ana")
    with pytest.raises(PermissionDenied):
        run("customer.customer.delete", RefIn(id=ana.id), role)
    assert run("customer.customer.delete", RefIn(id=ana.id), "hub_owner").id == ana.id


# customer.customer.merge (CUSTOMER-F13; merge.pg)


@pytest.fixture
def duplicates(db):
    survivor = card(
        "Ana García",
        phone="+34600111222",
        notes="Prefers mornings",
        total_purchases=1,
        total_spent=500,
        last_purchase_at=NOW - timedelta(days=5),
        lifecycle_stage="first_purchase",
    )
    absorbed = card(
        "ana garcia",
        phone="+34611222333",
        email="ana@example.com",
        tax_id="12345678Z",
        city="Madrid",
        preferred_channel="whatsapp",
        notes="Allergic to latex",
        total_purchases=2,
        total_spent=1050,
        last_purchase_at=NOW,
        source="whatsapp",
    )
    return survivor, absorbed


@pytest.mark.django_db
def test_the_survivor_keeps_its_data_fills_its_gaps_and_sums_the_figures(duplicates):
    survivor, absorbed = duplicates
    detail = run(
        "customer.customer.merge",
        MergeIn(id=survivor.id, absorbed_id=absorbed.id),
        "hub_manager",
    )
    assert (detail.name, detail.phone, detail.lifecycle_stage, detail.source) == (
        "Ana García",
        "+34600111222",
        "first_purchase",
        "walk_in",
    )
    assert (detail.email, detail.tax_id, detail.city, detail.preferred_channel) == (
        "ana@example.com",
        "12345678Z",
        "Madrid",
        "whatsapp",
    )
    assert detail.notes == "Prefers mornings\nAllergic to latex"
    assert (detail.total_purchases, detail.total_spent, detail.last_purchase_at) == (
        3,
        1550,
        NOW,
    )
    absorbed.refresh_from_db()
    assert (
        absorbed.deleted_at is not None
        and absorbed.is_active is False
        and absorbed.merged_into_id == survivor.id
    )
    assert (
        absorbed.total_purchases,
        absorbed.total_spent,
        absorbed.last_purchase_at,
    ) == (0, 0, None)
    # The duplicate keeps its own data: only CUSTOMER-F16 erases it.
    assert absorbed.email == "ana@example.com"
    assert outbox() == [
        (
            events.CUSTOMER_MERGED,
            {"id": str(survivor.id), "absorbed_id": str(absorbed.id)},
        )
    ]


@pytest.mark.django_db
def test_everything_that_hangs_from_the_duplicate_moves_to_the_survivor(duplicates):
    survivor, absorbed = duplicates
    vip, gold, moroso = (
        CustomerGroup.objects.create(name="VIP"),
        CustomerGroup.objects.create(name="Gold"),
        CustomerTag.objects.create(name="Moroso"),
    )
    survivor.groups.add(vip)
    absorbed.groups.add(vip, gold)
    absorbed.tags.add(moroso)
    allergies, hair = (
        CustomField.objects.create(name="Allergies"),
        CustomField.objects.create(name="Hair"),
    )
    CustomFieldValue.objects.create(customer=survivor, field=hair, value="Short")
    CustomFieldValue.objects.create(customer=absorbed, field=hair, value="Long")
    CustomFieldValue.objects.create(customer=absorbed, field=allergies, value="Latex")
    Activity.objects.create(customer=absorbed, kind="note_added", text="From WhatsApp")
    sale = uuid.uuid7()
    Purchase.objects.create(customer=absorbed, sale_id=sale, amount=1050)
    Consent.objects.create(
        customer=absorbed,
        channel="whatsapp",
        state="granted",
        contact_point="+34611222333",
    )
    order = uuid.uuid7()
    OrderLink.objects.create(order_id=order, customer=absorbed)

    run(
        "customer.customer.merge",
        MergeIn(customer="+34 600 111 222", absorbed="+34 611 222 333"),
    )

    assert set(survivor.groups.all()) == {vip, gold} and list(survivor.tags.all()) == [
        moroso
    ]
    assert list(absorbed.groups.all()) == [] and list(absorbed.tags.all()) == []
    assert values(survivor) == {"Hair": "Short", "Allergies": "Latex"}
    assert values(absorbed) == {
        "Hair": "Long"
    }  # the value that clashed stays with the duplicate
    assert Purchase.objects.get(sale_id=sale).customer_id == survivor.id
    assert Consent.objects.get().customer_id == survivor.id
    assert (
        Consent.objects.get().contact_point == "+34611222333"
    )  # consent follows its address
    assert OrderLink.objects.get(order_id=order).customer_id == survivor.id
    timeline = list(survivor.activity.values_list("kind", "related_id", "data"))
    assert timeline[0] == (
        "merged",
        str(absorbed.id),
        {"absorbed_id": str(absorbed.id)},
    )
    assert ("note_added", "", {}) in timeline


@pytest.mark.django_db
def test_a_merge_that_cannot_be_done_writes_nothing(duplicates):
    survivor, absorbed = duplicates
    gone = card("Gone", deleted_at=NOW)
    with pytest.raises(InvalidPayload) as excinfo:
        run("customer.customer.merge", MergeIn(id=survivor.id, absorbed_id=survivor.id))
    assert invalid(excinfo.value)[:2] == (422, "customer.same_customer")
    for absorbed_id in (gone.id, uuid.uuid7()):
        with pytest.raises(NotFound):
            run(
                "customer.customer.merge",
                MergeIn(id=survivor.id, absorbed_id=absorbed_id),
            )
    with pytest.raises(NotFound):
        run("customer.customer.merge", MergeIn(id=gone.id, absorbed_id=absorbed.id))
    absorbed.refresh_from_db()
    assert absorbed.deleted_at is None and outbox() == []


@pytest.mark.django_db
def test_the_employee_does_not_merge(duplicates):
    survivor, absorbed = duplicates
    with pytest.raises(PermissionDenied):
        run(
            "customer.customer.merge",
            MergeIn(id=survivor.id, absorbed_id=absorbed.id),
            "hub_employee",
        )


# customer.customer.erase (CUSTOMER-F16; anonymize.pg, activity_titles_are_keys.pg)


@pytest.fixture
def erasable(db):
    ana = card(
        "Ana García",
        email="ana@example.com",
        phone="+34600111222",
        tax_id="12345678Z",
        company_name="ACME",
        address="Calle Mayor 1",
        city="Madrid",
        postal_code="28001",
        country="ES",
        avatar="https://example.com/a.png",
        notes="Allergic",
        birthday=date(1990, 5, 4),
        anniversary=date(2015, 6, 1),
        preferred_channel="whatsapp",
        lifecycle_stage="vip",
        source="whatsapp",
        total_purchases=2,
        total_spent=1500,
        last_purchase_at=NOW,
    )
    ana.groups.add(CustomerGroup.objects.create(name="VIP"))
    ana.tags.add(CustomerTag.objects.create(name="Moroso"))
    CustomFieldValue.objects.create(
        customer=ana, field=CustomField.objects.create(name="Allergies"), value="Latex"
    )
    Activity.objects.create(customer=ana, kind="note_added", text="Pregnant")
    Consent.objects.create(
        customer=ana,
        channel="email",
        state="withdrawn",
        contact_point="ana@example.com",
        evidence="form 7",
        reason="spam",
    )
    Purchase.objects.create(customer=ana, sale_id=uuid.uuid7(), amount=1500)
    OrderLink.objects.create(order_id=uuid.uuid7(), customer=ana)
    return ana


@pytest.mark.django_db
def test_erase_replaces_the_personal_data_and_keeps_what_the_law_keeps(erasable):
    ana = erasable
    assert run(
        "customer.customer.erase",
        EraseIn(id=ana.id, reason="GDPR request #4"),
        actor="clara",
    ) == ErasedOut(id=ana.id)
    ana.refresh_from_db()
    personal = (
        "email",
        "phone",
        "tax_id",
        "company_name",
        "address",
        "city",
        "postal_code",
        "country",
        "avatar",
        "notes",
    )
    assert ana.name == "Deleted customer"
    assert {field: getattr(ana, field) for field in personal} == dict.fromkeys(
        personal, ""
    )
    assert (ana.birthday, ana.anniversary, ana.preferred_channel, ana.is_active) == (
        None,
        None,
        "none",
        False,
    )
    assert ana.deleted_at is not None and ana.erased_at is not None
    assert (
        ana.lifecycle_stage,
        ana.source,
        ana.total_purchases,
        ana.total_spent,
        ana.last_purchase_at,
    ) == ("vip", "whatsapp", 2, 1500, NOW)
    assert (ana.groups.count(), ana.tags.count(), ana.field_values.count()) == (0, 0, 0)
    assert (ana.purchases.count(), ana.orders.count()) == (1, 1)
    consent = ana.consents.get()
    assert (consent.contact_point, consent.evidence, consent.reason, consent.state) == (
        "",
        "",
        "",
        "withdrawn",
    )
    [audit] = ana.activity.all()
    assert (audit.kind, audit.text, audit.actor) == (
        "erased",
        "GDPR request #4",
        "clara",
    )
    assert audit.data == {
        "scope": [
            "customer",
            "activity",
            "field_values",
            "memberships",
            "consent_addresses",
        ],
        "retained": ["purchases", "orders"],
    }
    assert outbox() == [(events.CUSTOMER_ERASED, {"id": str(ana.id)})]


@pytest.mark.django_db
def test_erasing_twice_changes_nothing_but_announces_again(erasable):
    run("customer.customer.erase", EraseIn(id=erasable.id))
    run("customer.customer.erase", EraseIn(id=erasable.id, reason="again"))
    assert list(erasable.activity.values_list("kind", "text")) == [("erased", "")]
    assert outbox() == [(events.CUSTOMER_ERASED, {"id": str(erasable.id)})] * 2


@pytest.mark.django_db
def test_a_deleted_or_merged_card_can_still_be_erased_by_its_id():
    survivor = card("Ana")
    absorbed = card(
        "ana", email="ana@example.com", deleted_at=NOW, merged_into=survivor
    )
    run("customer.customer.erase", EraseIn(id=absorbed.id))
    absorbed.refresh_from_db()
    assert (absorbed.email, absorbed.erased_at is not None) == ("", True)


@pytest.mark.django_db
def test_erasing_an_unknown_card_fails_and_only_the_owner_and_admin_erase(erasable):
    with pytest.raises(NotFound):
        run("customer.customer.erase", EraseIn(id=uuid.uuid7()))
    with pytest.raises(PermissionDenied):
        run("customer.customer.erase", EraseIn(id=erasable.id), "hub_manager")
    assert outbox() == []


# customer.note.add and customer.activity.add (CUSTOMER-F05; note_add_projects_activity.pg)


@pytest.mark.django_db
def test_a_note_is_its_own_timeline_entry():
    ana = card("Ana")
    note = run(
        "customer.note.add",
        NoteIn(customer_id=ana.id, content="Prefers mornings", author_name="Clara"),
        "hub_employee",
        actor="clara",
    )
    entry = Activity.objects.get()
    assert (note.id, note.kind, note.text, note.actor, note.title) == (
        entry.id,
        "note_added",
        "Prefers mornings",
        "clara",
        "",
    )
    assert entry.data == {"author_name": "Clara"}
    assert outbox() == [
        (events.NOTE_ADDED, {"id": str(entry.id), "customer_id": str(ana.id)})
    ]


@pytest.mark.django_db
def test_a_note_on_a_card_that_is_gone_writes_nothing():
    with pytest.raises(NotFound):
        run(
            "customer.note.add",
            NoteIn(customer_id=card("Gone", deleted_at=NOW).id, content="x"),
        )
    assert not Activity.objects.exists() and outbox() == []


@pytest.mark.django_db
def test_another_app_writes_its_own_entry_in_the_timeline():
    ana = card("Ana")
    entry = run(
        "customer.activity.add",
        ActivityIn(
            customer="Ana",
            kind="appointment.visit",
            title="Visit",
            text="Cut and colour",
            data={"minutes": 90},
            related_id="apt-1",
            related_type="appointment",
        ),
        "hub_manager",
    )
    assert (entry.kind, entry.title, entry.data, entry.related_type) == (
        "appointment.visit",
        "Visit",
        {"minutes": 90},
        "appointment",
    )
    assert outbox() == [
        (events.ACTIVITY_RECORDED, {"id": str(entry.id), "customer_id": str(ana.id)})
    ]
    with pytest.raises(PermissionDenied):
        run(
            "customer.activity.add",
            ActivityIn(customer_id=ana.id, kind="x.y", title="t"),
            "hub_employee",
        )


# customer.consent.grant / withdraw (CUSTOMER-F14, F15; consent_ledger.pg)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("channel", "address"),
    [
        ("email", "ana@example.com"),
        ("whatsapp", "+34600111222"),
        ("sms", "+34600111222"),
        ("postal", "Calle Mayor 1, 28001 Madrid, ES"),
    ],
)
def test_a_grant_is_a_fact_for_the_cards_address_on_that_channel(channel, address):
    ana = card(
        "Ana",
        email="ana@example.com",
        phone="+34600111222",
        address="Calle Mayor 1",
        postal_code="28001",
        city="Madrid",
        country="ES",
    )
    fact = run(
        "customer.consent.grant",
        ConsentGrantIn(
            customer_id=ana.id,
            channel=channel,
            notice_text="I want offers.",
            notice_version="v1",
        ),
        "hub_employee",
        actor="clara",
    )
    assert (
        fact.state,
        fact.channel,
        fact.contact_point,
        fact.recorded_by,
        fact.purpose,
        fact.source,
    ) == (
        "granted",
        channel,
        address,
        "clara",
        "marketing",
        "counter",
    )
    assert fact.notice_text == "I want offers."
    entry = Activity.objects.get()
    assert (entry.kind, entry.text, entry.related_id) == (
        "consent_granted",
        "I want offers.",
        str(fact.id),
    )
    assert outbox() == [
        (
            events.CONSENT_GRANTED,
            {"id": str(fact.id), "customer_id": str(ana.id), "channel": channel},
        )
    ]


@pytest.mark.django_db
def test_grant_withdraw_and_grant_again_leave_three_facts_and_the_last_one_rules():
    ana = card("Ana", email="ana@example.com")
    yesterday = timezone.now() - timedelta(days=1)
    run(
        "customer.consent.grant",
        ConsentGrantIn(
            customer_id=ana.id,
            channel="email",
            notice_text="Yes",
            occurred_at=yesterday,
        ),
    )
    withdrawn = run(
        "customer.consent.withdraw",
        ConsentWithdrawIn(customer_id=ana.id, channel="email", reason="Too many"),
    )
    assert (withdrawn.state, withdrawn.reason, withdrawn.notice_text) == (
        "withdrawn",
        "Too many",
        "",
    )
    # The address is the card's at that moment, never one the caller sends (WORKBOOK F14).
    run("customer.customer.update", CustomerPatchIn(id=ana.id, email="new@example.com"))
    clear_outbox()
    run(
        "customer.consent.grant",
        ConsentGrantIn(customer_id=ana.id, channel="email", notice_text="Yes again"),
    )
    assert list(ana.consents.values_list("state", "contact_point")) == [
        ("granted", "new@example.com"),
        ("withdrawn", "ana@example.com"),
        ("granted", "ana@example.com"),
    ]
    assert [name for name, _ in outbox()] == [events.CONSENT_GRANTED]
    assert list(ana.activity.values_list("kind", flat=True)) == [
        "consent_granted",
        "consent_withdrawn",
        "consent_granted",
    ]


@pytest.mark.django_db
def test_a_consent_said_in_the_future_or_for_a_card_that_is_gone_is_refused():
    ana = card("Ana")
    with pytest.raises(InvalidPayload) as excinfo:
        run(
            "customer.consent.grant",
            ConsentGrantIn(
                customer_id=ana.id,
                channel="sms",
                notice_text="Yes",
                occurred_at=timezone.now() + timedelta(days=1),
            ),
        )
    assert invalid(excinfo.value) == (
        422,
        "customer.date_in_future",
        {"occurred_at": "This date is in the future."},
    )
    with pytest.raises(NotFound):
        run(
            "customer.consent.withdraw",
            ConsentWithdrawIn(
                customer_id=card("Gone", deleted_at=NOW).id, channel="sms"
            ),
        )
    assert not Consent.objects.exists()


# customer.order.link (CUSTOMER-F19; orders_link.pg)


@pytest.mark.django_db
def test_an_order_has_at_most_one_customer_and_a_relink_replaces_it():
    order = uuid.uuid7()
    ana, bea = card("Ana"), card("Bea")
    assert (
        run(
            "customer.order.link",
            OrderLinkIn(order_id=order, customer_id=ana.id),
            "hub_employee",
        ).customer_id
        == ana.id
    )
    run(
        "customer.order.link", OrderLinkIn(order_id=order, customer_id=ana.id)
    )  # the same pair: nothing rewritten
    assert (
        run(
            "customer.order.link", OrderLinkIn(order_id=order, customer="Bea")
        ).customer_id
        == bea.id
    )
    assert list(OrderLink.objects.values_list("order_id", "customer_id")) == [
        (order, bea.id)
    ]
    assert outbox() == [
        (events.ORDER_LINKED, {"order_id": str(order), "customer_id": str(ana.id)}),
        (events.ORDER_LINKED, {"order_id": str(order), "customer_id": str(bea.id)}),
    ]


@pytest.mark.django_db
def test_without_a_customer_the_link_goes():
    order = uuid.uuid7()
    ana = card("Ana")
    OrderLink.objects.create(order_id=order, customer=ana)
    assert run("customer.order.link", OrderLinkIn(order_id=order)).customer_id is None
    assert not OrderLink.objects.exists()
    run(
        "customer.order.link", OrderLinkIn(order_id=order)
    )  # nothing to remove: no notice
    assert outbox() == [
        (events.ORDER_UNLINKED, {"order_id": str(order), "customer_id": str(ana.id)})
    ]


@pytest.mark.django_db
def test_a_card_that_is_gone_is_not_linked():
    with pytest.raises(NotFound):
        run(
            "customer.order.link",
            OrderLinkIn(
                order_id=uuid.uuid7(), customer_id=card("Gone", deleted_at=NOW).id
            ),
        )


# Groups, tags and custom fields (CUSTOMER-F27..F29; group_name_unique.pg, tag_field_name_unique.pg)


@pytest.mark.django_db
def test_group_crud_with_its_notices():
    group = run(
        "customer.group.create",
        GroupIn(name=" VIP ", description="Best", sort_order=2),
        "hub_manager",
    )
    assert (
        group.name,
        group.description,
        group.color,
        group.sort_order,
        group.is_active,
        group.customer_count,
    ) == ("VIP", "Best", "primary", 2, True, 0)
    updated = run(
        "customer.group.update",
        GroupPatchIn(group="vip", name="Gold", is_active=False),
        "hub_manager",
    )
    assert (updated.name, updated.is_active, updated.description) == (
        "Gold",
        False,
        "Best",
    )
    ana = card("Ana")
    ana.groups.add(CustomerGroup.objects.get())
    assert run(
        "customer.group.delete", GroupRefIn(id=group.id), "hub_admin"
    ) == DeletedOut(id=group.id)
    assert ana.groups.count() == 0
    assert outbox() == [
        (events.GROUP_CREATED, {"id": str(group.id)}),
        (events.GROUP_UPDATED, {"id": str(group.id)}),
        (events.GROUP_DELETED, {"id": str(group.id)}),
    ]


@pytest.mark.django_db
def test_a_taken_group_name_is_refused_under_the_name_field():
    CustomerGroup.objects.create(name="VIP")
    for attempt in (lambda: run("customer.group.create", GroupIn(name=" vip ")),):
        with pytest.raises(Conflict) as excinfo:
            attempt()
        assert invalid(excinfo.value) == (
            409,
            "customer.group_name_taken",
            {"name": "There is already a group with that name. Choose another name."},
        )
    other = CustomerGroup.objects.create(name="Gold")
    with pytest.raises(Conflict):
        run("customer.group.update", GroupPatchIn(id=other.id, name="VIP"))
    # An inactive group frees its name, and taking it back while another holds it is refused.
    CustomerGroup.objects.filter(name="VIP").update(is_active=False)
    run("customer.group.update", GroupPatchIn(id=other.id, name="VIP"))
    with pytest.raises(Conflict):
        run(
            "customer.group.update",
            GroupPatchIn(
                id=CustomerGroup.objects.get(is_active=False).id, is_active=True
            ),
        )


@pytest.mark.django_db
def test_only_owner_and_admin_delete_groups_and_tags_but_the_manager_deletes_fields():
    group = CustomerGroup.objects.create(name="VIP")
    tag = CustomerTag.objects.create(name="Moroso")
    field = CustomField.objects.create(name="Allergies")
    with pytest.raises(PermissionDenied):
        run("customer.group.delete", GroupRefIn(id=group.id), "hub_manager")
    with pytest.raises(PermissionDenied):
        run("customer.tag.delete", TagRefIn(id=tag.id), "hub_manager")
    assert (
        run("customer.field.delete", FieldRef(field="allergies"), "hub_manager").id
        == field.id
    )
    with pytest.raises(NotFound) as excinfo:
        run("customer.group.delete", GroupRefIn(id=uuid.uuid7()))
    assert excinfo.value.code == "customer.group_unavailable"


@pytest.mark.django_db
def test_tag_crud_and_its_taken_name():
    tag = run("customer.tag.create", TagIn(name="Moroso", color="danger"))
    assert (tag.name, tag.color, tag.is_active) == ("Moroso", "danger", True)
    with pytest.raises(Conflict) as excinfo:
        run("customer.tag.create", TagIn(name="MOROSO"))
    assert excinfo.value.code == "customer.tag_name_taken"
    assert (
        run("customer.tag.update", TagPatchIn(tag="Moroso", color="warning")).color
        == "warning"
    )
    run("customer.tag.delete", TagRefIn(tag="moroso"))
    assert not CustomerTag.objects.exists()
    assert [name for name, _ in outbox()] == [
        events.TAG_CREATED,
        events.TAG_UPDATED,
        events.TAG_DELETED,
    ]


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_turning_a_field_into_a_select_needs_its_options():
    field = CustomField.objects.create(name="Hair")
    with pytest.raises(InvalidPayload) as excinfo:
        run("customer.field.update", FieldPatchIn(id=field.id, field_type="select"))
    assert invalid(excinfo.value) == (
        422,
        "invalid_payload",
        {"options": "Add at least one option."},
    )


@pytest.mark.django_db
def test_the_employee_does_not_configure():
    with pytest.raises(PermissionDenied):
        run("customer.group.create", GroupIn(name="VIP"), "hub_employee")


# customer.purchase.record / void (CUSTOMER-F20, F21; purchase_ledger.pg)


def totals(customer):
    customer.refresh_from_db()
    return (
        customer.total_purchases,
        customer.total_spent,
        customer.lifecycle_stage,
        customer.last_purchase_at,
    )


def record(customer, sale, total, at=NOW, **extra):
    return system(
        "customer.purchase.record",
        PurchaseRecordIn(
            customer_id=customer.id if customer else None,
            sale_id=sale,
            total=total,
            purchased_at=at,
            **extra,
        ),
    )


def void(sale, reason="mistake"):
    return system("customer.purchase.void", PurchaseVoidIn(sale_id=sale, reason=reason))


@pytest.mark.django_db
def test_a_sale_is_recorded_once_and_moves_the_stage():
    ana = card("Ana")
    first, second = uuid.uuid7(), uuid.uuid7()
    assert record(ana, first, 1250, currency="EUR").recorded is True
    assert totals(ana) == (1, 1250, "first_purchase", NOW)
    assert (
        record(ana, first, 1250, at=NOW + timedelta(minutes=5)).recorded is False
    )  # redelivered
    assert totals(ana) == (1, 1250, "first_purchase", NOW)
    later = NOW + timedelta(days=1)
    record(ana, second, 300, at=later)
    assert totals(ana) == (2, 1550, "active", later)
    purchase = Purchase.objects.get(sale_id=first)
    assert (purchase.amount, purchase.currency, purchase.status) == (
        1250,
        "EUR",
        "confirmed",
    )
    timeline = list(ana.activity.values_list("kind", "related_id", "data"))
    assert timeline[-1] == (
        "purchase_recorded",
        str(first),
        {"amount": 1250, "currency": "EUR"},
    )
    assert [name for name, _ in outbox()] == [events.PURCHASE_RECORDED] * 2
    assert outbox()[0][1] == {"customer_id": str(ana.id), "sale_id": str(first)}


@pytest.mark.django_db
def test_a_sale_without_customer_or_for_a_card_that_is_gone_records_nothing():
    assert record(None, uuid.uuid7(), 999).recorded is False
    gone = card("Gone", deleted_at=NOW)
    assert record(gone, uuid.uuid7(), 500).recorded is False
    assert totals(gone)[:2] == (0, 0)
    assert not Purchase.objects.exists() and outbox() == []


@pytest.mark.django_db
def test_a_manual_entry_has_no_sale_and_is_never_deduplicated():
    ana = card("Ana")
    record(ana, None, 100)
    record(ana, None, 100)
    assert totals(ana)[:2] == (2, 200)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("lead", "first_purchase"),
        ("prospect", "first_purchase"),
        ("first_purchase", "active"),
        ("at_risk", "active"),
        ("dormant", "active"),
        ("churned", "churned"),
        ("vip", "vip"),
        ("active", "active"),
    ],
)
def test_the_stage_moves_forward_with_a_purchase(before, after):
    ana = card("Ana", lifecycle_stage=before)
    record(ana, uuid.uuid7(), 100)
    assert totals(ana)[2] == after


@pytest.mark.django_db
def test_a_void_reverts_the_figures_once_and_keeps_the_history():
    ana = card("Ana")
    first, second = uuid.uuid7(), uuid.uuid7()
    record(ana, first, 1250)
    record(ana, second, 300, at=NOW + timedelta(days=1))
    clear_outbox()
    assert void(second).voided is True
    assert totals(ana) == (1, 1250, "first_purchase", NOW)
    assert Purchase.objects.get(sale_id=second).status == "voided"
    assert void(second, "again").voided is False
    assert void(uuid.uuid7()).voided is False
    void(first, "refund")
    assert totals(ana) == (0, 0, "lead", None)
    voids = list(
        ana.activity.filter(kind="purchase_voided").values_list("related_id", "text")
    )
    assert voids == [(str(first), "refund"), (str(second), "mistake")]
    assert outbox() == [
        (events.PURCHASE_VOIDED, {"customer_id": str(ana.id), "sale_id": str(second)}),
        (events.PURCHASE_VOIDED, {"customer_id": str(ana.id), "sale_id": str(first)}),
    ]


@pytest.mark.django_db
def test_a_void_never_demotes_a_vip():
    ana = card("Ana", lifecycle_stage="vip")
    sale = uuid.uuid7()
    record(ana, sale, 100)
    void(sale)
    assert totals(ana)[2] == "vip"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role", ["hub_owner", "hub_admin", "hub_manager", "hub_employee"]
)
def test_only_the_system_records_and_voids_purchases(role):
    ana = card("Ana")
    with pytest.raises(PermissionDenied):
        run(
            "customer.purchase.record",
            PurchaseRecordIn(customer_id=ana.id, sale_id=uuid.uuid7(), total=100),
            role,
        )
    with pytest.raises(PermissionDenied):
        run("customer.purchase.void", PurchaseVoidIn(sale_id=uuid.uuid7()), role)


@pytest.mark.django_db
def test_a_deleted_card_with_purchases_keeps_them_and_a_later_sale_does_not_add_up():
    ana = card("Ana")
    record(ana, uuid.uuid7(), 500)
    run("customer.customer.delete", RefIn(id=ana.id))
    assert record(ana, uuid.uuid7(), 700).recorded is False
    assert (ana.purchases.count(), totals(ana)[:2]) == (1, (1, 500))


# Notifications: after the COMMIT, on the channel of the command's scope only


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=WAIT, stop_after=None):
    return [
        (note.channel, json.loads(note.payload))
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
    ]


@pytest.mark.django_db(transaction=True)
def test_a_command_in_scope_b_notifies_the_channel_of_b_only(listen):
    on_a, on_b = listen(A), listen(B)
    run("customer.customer.create", CustomerIn(name="Ana"), scope=B)
    assert received(on_b, stop_after=1) == [
        (channel_for(B), {"events": [events.CUSTOMER_CREATED]})
    ]
    assert received(on_a, timeout=QUIET) == []


@pytest.mark.django_db(transaction=True)
def test_a_rejected_command_notifies_nobody(listen):
    on_a = listen(A)
    with pytest.raises(InvalidPayload):
        run("customer.customer.create", CustomerIn(name="Ana", phone="600111"))
    assert received(on_a, timeout=QUIET) == []


# Erasing reaches the duplicates merged into the card (GDPR, CUSTOMER-F13 and F16)


def erased(customer):
    customer.refresh_from_db()
    return (customer.name, customer.email, customer.erased_at is not None)


@pytest.mark.django_db
def test_erasing_a_card_erases_the_duplicates_merged_into_it():
    survivor = card("Ana", email="ana@example.com")
    absorbed = card("ana", email="other@example.com", phone="+34611222333", tax_id="12345678Z", notes="Allergic")
    hair = CustomField.objects.create(name="Hair")
    CustomFieldValue.objects.create(customer=survivor, field=hair, value="Short")
    CustomFieldValue.objects.create(customer=absorbed, field=hair, value="Long")  # clashes: stays behind
    run("customer.customer.merge", MergeIn(id=survivor.id, absorbed_id=absorbed.id))
    clear_outbox()

    run("customer.customer.erase", EraseIn(id=survivor.id, reason="GDPR request"))

    assert erased(absorbed) == ("Deleted customer", "", True)
    assert (absorbed.phone, absorbed.tax_id, absorbed.notes, absorbed.field_values.count()) == ("", "", "", 0)
    assert list(absorbed.activity.values_list("kind", "text")) == [("erased", "GDPR request")]
    assert outbox() == [
        (events.CUSTOMER_ERASED, {"id": str(survivor.id)}),
        (events.CUSTOMER_ERASED, {"id": str(absorbed.id)}),
    ]


@pytest.mark.django_db
def test_a_merge_keeps_the_chain_flat_and_erasing_reaches_every_card_of_it():
    first, second, third = card("A"), card("B", email="b@example.com"), card("C", email="c@example.com")
    run("customer.customer.merge", MergeIn(id=second.id, absorbed_id=third.id))
    run("customer.customer.merge", MergeIn(id=first.id, absorbed_id=second.id))
    third.refresh_from_db()
    assert third.merged_into_id == first.id  # C was in B, and B went into A: C points at A
    clear_outbox()

    run("customer.customer.erase", EraseIn(id=first.id))

    assert erased(second)[1:] == erased(third)[1:] == ("", True)
    assert {payload["id"] for _, payload in outbox()} == {str(first.id), str(second.id), str(third.id)}


@pytest.mark.django_db
def test_erasing_follows_a_chain_that_is_not_flat():
    first = card("A")
    second = card("B", merged_into=first, deleted_at=NOW)
    third = card("C", email="c@example.com", merged_into=second, deleted_at=NOW)
    run("customer.customer.erase", EraseIn(id=first.id))
    assert erased(third) == ("Deleted customer", "", True)


@pytest.mark.django_db
def test_repeating_the_erasure_of_a_merged_card_announces_every_card_again_and_writes_nothing():
    survivor, absorbed = card("Ana"), card("ana", email="ana@example.com")
    run("customer.customer.merge", MergeIn(id=survivor.id, absorbed_id=absorbed.id))
    run("customer.customer.erase", EraseIn(id=survivor.id))
    clear_outbox()
    run("customer.customer.erase", EraseIn(id=survivor.id, reason="again"))
    assert len(outbox()) == 2
    assert list(absorbed.activity.values_list("text", flat=True)) == [""]


# customer.purchase.refund (CUSTOMER-F22)


def refund(sale, refund_id, total, reason="returned", at=None):
    return system(
        "customer.purchase.refund",
        PurchaseRefundIn(sale_id=sale, refund_id=refund_id, total=total, reason=reason, refunded_at=at),
    )


@pytest.mark.django_db
def test_a_refund_lowers_the_spend_once_and_leaves_a_negative_line_in_the_history():
    ana = card("Ana")
    sale, first, second = uuid.uuid7(), uuid.uuid7(), uuid.uuid7()
    record(ana, sale, 2420, currency="EUR")
    clear_outbox()
    later = NOW + timedelta(hours=2)
    assert refund(sale, first, 1210, "one cup back", later).refunded is True
    # «Spent» goes down by what came back; «Purchases», the last purchase and the stage do not move.
    assert totals(ana) == (1, 1210, "first_purchase", NOW)
    line = Purchase.objects.get(refund_id=first)
    assert (line.sale_id, line.amount, line.currency, line.status, line.recorded_at, line.void_reason) == (
        sale,
        -1210,
        "EUR",
        "refunded",
        later,
        "one cup back",
    )
    assert refund(sale, first, 1210).refunded is False  # redelivered
    assert refund(sale, second, 1210).refunded is True  # a second refund of the same sale
    assert totals(ana)[:2] == (1, 0)
    entries = list(ana.activity.filter(kind="purchase_refunded").values_list("text", "data"))
    assert entries == [("returned", {"amount": 1210, "currency": "EUR"}), ("one cup back", {"amount": 1210, "currency": "EUR"})]
    assert outbox() == [
        (events.PURCHASE_REFUNDED, {"customer_id": str(ana.id), "sale_id": str(sale), "refund_id": str(first)}),
        (events.PURCHASE_REFUNDED, {"customer_id": str(ana.id), "sale_id": str(sale), "refund_id": str(second)}),
    ]


@pytest.mark.django_db
def test_a_refund_of_a_sale_not_recorded_or_voided_changes_nothing():
    assert refund(uuid.uuid7(), uuid.uuid7(), 100).refunded is False
    ana = card("Ana")
    sale = uuid.uuid7()
    record(ana, sale, 500)
    void(sale)
    clear_outbox()
    assert refund(sale, uuid.uuid7(), 500).refunded is False
    assert totals(ana)[:2] == (0, 0) and outbox() == []


@pytest.mark.django_db
def test_a_refund_of_an_erased_card_counts_but_adds_nothing_to_its_timeline():
    ana = card("Ana")
    sale = uuid.uuid7()
    record(ana, sale, 500)
    run("customer.customer.erase", EraseIn(id=ana.id))
    assert refund(sale, uuid.uuid7(), 200).refunded is True
    assert totals(ana)[:2] == (1, 300)
    assert list(ana.activity.values_list("kind", flat=True)) == ["erased"]


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["hub_owner", "hub_admin", "hub_manager", "hub_employee"])
def test_only_the_system_records_refunds(role):
    with pytest.raises(PermissionDenied):
        run(
            "customer.purchase.refund",
            PurchaseRefundIn(sale_id=uuid.uuid7(), refund_id=uuid.uuid7(), total=100),
            role,
        )


@pytest.mark.django_db
def test_voiding_a_sale_of_an_erased_card_adds_nothing_to_its_timeline():
    ana = card("Ana")
    sale = uuid.uuid7()
    record(ana, sale, 500)
    run("customer.customer.erase", EraseIn(id=ana.id))
    assert void(sale).voided is True
    assert totals(ana)[:2] == (0, 0)
    assert list(ana.activity.values_list("kind", flat=True)) == ["erased"]


# Writes lock their card: two transactions at once, in two threads

#: How long the other transaction keeps its locks: long enough for this one to reach them.
HOLD = 0.5


def race(hold, attempt, then=None):
    """Runs ``attempt`` here while another thread, in a transaction, holds what ``hold`` locked.

    The other thread runs ``hold``, lets ``attempt`` start, waits ``HOLD`` seconds, runs ``then``
    (if any) and commits. ``attempt``'s result (or its exception) is this function's.
    """
    locked = threading.Event()
    problems = []

    def holder():
        try:
            with transaction.atomic():
                hold()
                locked.set()
                time.sleep(HOLD)
                if then is not None:
                    then()
        except Exception as exc:  # reported below: a deadlock shows up here
            problems.append(exc)
        finally:
            locked.set()
            connection.close()

    thread = threading.Thread(target=holder)
    thread.start()
    try:
        assert locked.wait(5)
        return attempt()
    finally:
        thread.join(10)
        assert problems == []


def note_on(customer):
    return "customer.note.add", NoteIn(customer_id=customer.id, content="Prefers mornings")


def activity_on(customer):
    return "customer.activity.add", ActivityIn(customer_id=customer.id, kind="appointment.visit", title="Visit")


def consent_on(customer):
    return "customer.consent.grant", ConsentGrantIn(customer_id=customer.id, channel="email", notice_text="Yes")


def order_on(customer):
    return "customer.order.link", OrderLinkIn(order_id=uuid.uuid7(), customer_id=customer.id)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("write", "written"),
    [
        (note_on, lambda: Activity.objects.filter(kind="note_added")),
        (activity_on, lambda: Activity.objects.filter(kind="appointment.visit")),
        (consent_on, lambda: Consent.objects.all()),
        (order_on, lambda: OrderLink.objects.all()),
    ],
)
def test_a_write_on_a_card_being_deleted_waits_and_then_finds_it_gone(write, written):
    ana = card("Ana", email="ana@example.com")
    name, data = write(ana)
    with pytest.raises(NotFound):
        race(lambda: run("customer.customer.delete", RefIn(id=ana.id)), lambda: run(name, data))
    assert not written().exists()


@pytest.mark.django_db(transaction=True)
def test_a_note_on_a_card_being_merged_lands_on_the_card_that_stays():
    survivor, absorbed = card("Ana"), card("ana")
    with pytest.raises(NotFound):
        race(
            lambda: run("customer.customer.merge", MergeIn(id=survivor.id, absorbed_id=absorbed.id)),
            lambda: run("customer.note.add", NoteIn(customer_id=absorbed.id, content="Late note")),
        )
    assert not absorbed.activity.filter(kind="note_added").exists()


@pytest.mark.django_db(transaction=True)
def test_a_void_locks_the_card_before_its_purchase_so_it_never_deadlocks_with_a_merge():
    # A merge locks the cards and then their purchases; a void used to lock the purchase and then
    # the card. Both orders at once wait for each other until Postgres kills one of them.
    ana = card("Ana")
    sale = uuid.uuid7()
    record(ana, sale, 500)

    def lock_the_card():
        Customer.objects.select_for_update().get(pk=ana.pk)

    def then_its_purchases():
        list(Purchase.objects.select_for_update().filter(customer=ana))

    assert race(lock_the_card, lambda: void(sale), then=then_its_purchases).voided is True
    assert totals(ana)[:2] == (0, 0)
