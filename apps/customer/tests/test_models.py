"""Models of the customer app: UUIDv7 keys, defaults, search text, uniqueness and what cascades."""

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

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

pytestmark = pytest.mark.django_db

SALE = "0199a6c0-0000-7000-8000-000000000001"
ORDER = "0199a6c0-0000-7000-8000-000000000003"


def make_customer(name="Ana García", **fields):
    return Customer.objects.create(name=name, **fields)


def unique_violation(constraint, create):
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        create()
    return constraint in str(excinfo.value)


# Customer


def test_keys_are_uuid7():
    customer = make_customer()
    group = CustomerGroup.objects.create(name="VIP")
    assert (customer.pk.version, group.pk.version) == (7, 7)


def test_a_walk_in_needs_only_a_name_and_lands_with_the_defaults():
    customer = make_customer("Ana")
    customer.refresh_from_db()
    texts = (
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
    assert {field: getattr(customer, field) for field in texts} == dict.fromkeys(
        texts, ""
    )
    assert (customer.birthday, customer.anniversary) == (None, None)
    assert (customer.lifecycle_stage, customer.source, customer.preferred_channel) == (
        "lead",
        "walk_in",
        "none",
    )
    assert customer.is_active is True
    assert (
        customer.total_purchases,
        customer.total_spent,
        customer.last_purchase_at,
    ) == (0, 0, None)
    assert (customer.deleted_at, customer.erased_at, customer.merged_into) == (
        None,
        None,
        None,
    )
    assert customer.created_at is not None and customer.updated_at is not None


def test_choices():
    assert Customer.Stage.values == [
        "lead",
        "prospect",
        "first_purchase",
        "active",
        "at_risk",
        "dormant",
        "churned",
        "vip",
    ]
    assert Customer.Source.values == [
        "walk_in",
        "website",
        "phone",
        "referral",
        "social",
        "whatsapp",
        "import",
        "other",
    ]
    assert Customer.PreferredChannel.values == [
        "none",
        "email",
        "sms",
        "whatsapp",
        "phone",
    ]


def test_the_search_text_is_kept_on_every_save():
    customer = make_customer(
        "Ana García", email="ANA@example.com", phone="+34600111222", tax_id="12345678Z"
    )
    customer.refresh_from_db()
    assert customer.search_text == "ana garcia ana@example.com +34600111222 12345678z"

    customer.company_name = "Peluquería Sol"
    customer.save(update_fields=["company_name"])  # search_text is saved with it
    customer.refresh_from_db()
    assert customer.search_text.endswith("peluqueria sol")


def test_live_leaves_out_the_deleted_merged_and_erased_cards():
    alive = make_customer("Alive")
    inactive = make_customer("Inactive", is_active=False)
    make_customer("Deleted", deleted_at=timezone.now())
    assert set(Customer.objects.live()) == {alive, inactive}


def test_a_merged_card_points_at_the_one_that_absorbed_it():
    survivor = make_customer("Ana")
    absorbed = make_customer("ana", merged_into=survivor, deleted_at=timezone.now())
    assert list(survivor.absorbed.all()) == [absorbed]


def test_customers_are_ordered_by_name_then_id():
    second = make_customer("Bea")
    first = make_customer("Ana")
    assert list(Customer.objects.all()) == [first, second]


# Groups, tags and custom fields


def test_a_group_name_is_unique_among_the_active_ones_whatever_its_case():
    CustomerGroup.objects.create(name="VIP")
    assert unique_violation(
        "customer_group_name_unique", lambda: CustomerGroup.objects.create(name="vip")
    )


def test_an_inactive_group_frees_its_name():
    # As in the product (customers#94): an inactive group is in no picker, so it holds no name.
    CustomerGroup.objects.create(name="VIP", is_active=False)
    CustomerGroup.objects.create(name="vip")
    assert CustomerGroup.objects.count() == 2


def test_a_tag_name_is_unique_among_the_active_ones_whatever_its_case():
    CustomerTag.objects.create(name="Moroso")
    assert unique_violation(
        "customer_tag_name_unique", lambda: CustomerTag.objects.create(name="MOROSO")
    )
    CustomerTag.objects.create(name="moroso", is_active=False)


def test_a_field_name_is_unique_among_the_active_ones_whatever_its_case():
    CustomField.objects.create(name="Alergias")
    assert unique_violation(
        "customer_field_name_unique",
        lambda: CustomField.objects.create(name="alergias"),
    )
    CustomField.objects.create(name="ALERGIAS", is_active=False)


def test_group_and_tag_defaults():
    group = CustomerGroup.objects.create(name="VIP")
    tag = CustomerTag.objects.create(name="Moroso")
    assert (group.description, group.color, group.sort_order, group.is_active) == (
        "",
        "primary",
        0,
        True,
    )
    assert (tag.color, tag.is_active) == ("primary", True)


def test_deleting_a_group_or_a_tag_takes_it_off_every_card():
    customer = make_customer()
    group = CustomerGroup.objects.create(name="VIP")
    tag = CustomerTag.objects.create(name="Moroso")
    customer.groups.add(group)
    customer.tags.add(tag)
    group.delete()
    tag.delete()
    assert (customer.groups.count(), customer.tags.count()) == (0, 0)


def test_field_types_and_defaults():
    assert CustomField.FieldType.values == [
        "text",
        "number",
        "date",
        "boolean",
        "select",
        "textarea",
    ]
    field = CustomField.objects.create(name="Alergias")
    defaults = (
        field.field_type,
        field.options,
        field.is_required,
        field.sort_order,
        field.is_active,
    )
    assert defaults == ("text", [], False, 0, True)


def test_one_value_per_card_and_field():
    customer = make_customer()
    field = CustomField.objects.create(name="Alergias")
    CustomFieldValue.objects.create(customer=customer, field=field, value="Látex")
    assert unique_violation(
        "customer_field_value_unique",
        lambda: CustomFieldValue.objects.create(
            customer=customer, field=field, value="Polen"
        ),
    )


def test_deleting_a_field_deletes_its_values():
    customer = make_customer()
    field = CustomField.objects.create(name="Alergias")
    CustomFieldValue.objects.create(customer=customer, field=field, value="Látex")
    field.delete()
    assert not CustomFieldValue.objects.exists()


# Activity, purchases, consent and orders


def test_activity_is_newest_first():
    customer = make_customer()
    now = timezone.now()
    old = Activity.objects.create(
        customer=customer,
        kind="note_added",
        text="old",
        created_at=now - timedelta(minutes=1),
    )
    new = Activity.objects.create(
        customer=customer, kind="note_added", text="new", created_at=now
    )
    assert list(customer.activity.all()) == [new, old]
    assert Activity.Kind.values == [
        "note_added",
        "purchase_recorded",
        "purchase_voided",
        "purchase_refunded",
        "consent_granted",
        "consent_withdrawn",
        "merged",
        "erased",
        "health_consent_granted",
        "health_consent_withdrawn",
        "health_updated",
    ]
    assert (new.title, new.data, new.related_id, new.related_type, new.actor) == (
        "",
        {},
        "",
        "",
        "",
    )


def test_another_app_may_write_an_activity_kind_of_its_own():
    # customer.activity.add is the door other apps write through: their kind and title are theirs.
    entry = Activity.objects.create(
        customer=make_customer(), kind="appointment.visit", title="Visit"
    )
    entry.refresh_from_db()
    assert (entry.kind, entry.title) == ("appointment.visit", "Visit")


def test_a_sale_is_recorded_once():
    customer = make_customer()
    Purchase.objects.create(
        customer=customer, sale_id=SALE, amount=1250, currency="EUR"
    )
    assert unique_violation(
        "customer_purchase_sale_unique",
        lambda: Purchase.objects.create(customer=customer, sale_id=SALE, amount=1250),
    )
    assert Purchase.Status.values == ["confirmed", "voided", "refunded"]


def test_purchases_without_a_sale_do_not_collide():
    # A manual entry (no sale) is a row of its own, never deduplicated.
    customer = make_customer()
    Purchase.objects.create(customer=customer, amount=100)
    Purchase.objects.create(customer=customer, amount=100)
    assert customer.purchases.count() == 2


def test_a_purchase_defaults_to_confirmed_now():
    purchase = Purchase.objects.create(
        customer=make_customer(), sale_id=SALE, amount=300
    )
    assert (
        purchase.status,
        purchase.currency,
        purchase.voided_at,
        purchase.void_reason,
    ) == ("confirmed", "", None, "")
    assert purchase.recorded_at is not None


def test_consent_choices_and_order():
    customer = make_customer()
    now = timezone.now()
    first = Consent.objects.create(
        customer=customer,
        channel="email",
        state="granted",
        occurred_at=now - timedelta(days=1),
    )
    last = Consent.objects.create(
        customer=customer, channel="email", state="withdrawn", occurred_at=now
    )
    assert list(customer.consents.all()) == [last, first]
    assert (first.purpose, first.source) == ("marketing", "counter")
    assert Consent.Channel.values == ["email", "sms", "whatsapp", "phone", "postal"]
    assert Consent.State.values == ["granted", "withdrawn"]
    assert Consent.Source.values == [
        "counter",
        "web_form",
        "phone",
        "email",
        "import",
        "receipt",
    ]


def test_an_order_has_at_most_one_customer():
    OrderLink.objects.create(order_id=ORDER, customer=make_customer("Ana"))
    assert unique_violation(
        "customer_order_link_unique",
        lambda: OrderLink.objects.create(order_id=ORDER, customer=make_customer("Bea")),
    )


# HealthRecord (CUSTOMER-F32)


@pytest.mark.django_db
def test_a_card_has_at_most_one_health_record_and_it_never_names_its_data():
    ana = Customer.objects.create(name="Ana")
    record = HealthRecord.objects.create(customer=ana, allergies="PPD")
    assert (record.sensitivity_test_on, record.sensitivity_test_result) == (None, "")
    # Its text in the admin and in logs says whose it is, never what it holds.
    assert "PPD" not in str(record)
    with pytest.raises(IntegrityError), transaction.atomic():
        HealthRecord.objects.create(customer=ana, allergies="Latex")


def test_a_health_permission_has_no_channel():
    assert Consent._meta.get_field("channel").blank is True
