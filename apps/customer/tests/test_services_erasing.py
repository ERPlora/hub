"""Erasing a card's personal data, and that of the duplicates merged into it (CUSTOMER-F16)."""

import uuid

import pytest
from live.errors import NotFound, PermissionDenied

from apps.customer import events
from apps.customer.models import (
    Activity,
    Consent,
    CustomField,
    CustomFieldValue,
    CustomerGroup,
    CustomerTag,
    OrderLink,
    Purchase,
)
from apps.customer.schemas.erasing import EraseIn, ErasedOut
from apps.customer.schemas.merging import MergeIn

from .conftest import HUB_DB, NOW, card, clear_outbox, outbox, run

pytestmark = HUB_DB


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
        birthday="1990-05-04",
        anniversary="2015-06-01",
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
            "health",
            "memberships",
            "consent_addresses",
        ],
        "retained": ["purchases", "orders"],
    }
    assert outbox() == [(events.CUSTOMER_ERASED, {"id": str(ana.id)})]


def test_erasing_twice_changes_nothing_but_announces_again(erasable):
    run("customer.customer.erase", EraseIn(id=erasable.id))
    run("customer.customer.erase", EraseIn(id=erasable.id, reason="again"))
    assert list(erasable.activity.values_list("kind", "text")) == [("erased", "")]
    assert outbox() == [(events.CUSTOMER_ERASED, {"id": str(erasable.id)})] * 2


def test_a_deleted_or_merged_card_can_still_be_erased_by_its_id():
    survivor = card("Ana")
    absorbed = card(
        "ana", email="ana@example.com", deleted_at=NOW, merged_into=survivor
    )
    run("customer.customer.erase", EraseIn(id=absorbed.id))
    absorbed.refresh_from_db()
    assert (absorbed.email, absorbed.erased_at is not None) == ("", True)


def test_erasing_an_unknown_card_fails_and_only_the_owner_and_admin_erase(erasable):
    with pytest.raises(NotFound):
        run("customer.customer.erase", EraseIn(id=uuid.uuid7()))
    with pytest.raises(PermissionDenied):
        run("customer.customer.erase", EraseIn(id=erasable.id), "hub_manager")
    assert outbox() == []


# Erasing reaches the duplicates merged into the card (GDPR, CUSTOMER-F13 and F16)


def erased(customer):
    customer.refresh_from_db()
    return (customer.name, customer.email, customer.erased_at is not None)


def test_erasing_a_card_erases_the_duplicates_merged_into_it():
    survivor = card("Ana", email="ana@example.com")
    absorbed = card(
        "ana",
        email="other@example.com",
        phone="+34611222333",
        tax_id="12345678Z",
        notes="Allergic",
    )
    hair = CustomField.objects.create(name="Hair")
    CustomFieldValue.objects.create(customer=survivor, field=hair, value="Short")
    CustomFieldValue.objects.create(
        customer=absorbed, field=hair, value="Long"
    )  # clashes: stays behind
    run("customer.customer.merge", MergeIn(id=survivor.id, absorbed_id=absorbed.id))
    clear_outbox()

    run("customer.customer.erase", EraseIn(id=survivor.id, reason="GDPR request"))

    assert erased(absorbed) == ("Deleted customer", "", True)
    assert (
        absorbed.phone,
        absorbed.tax_id,
        absorbed.notes,
        absorbed.field_values.count(),
    ) == ("", "", "", 0)
    assert list(absorbed.activity.values_list("kind", "text")) == [
        ("erased", "GDPR request")
    ]
    assert outbox() == [
        (events.CUSTOMER_ERASED, {"id": str(survivor.id)}),
        (events.CUSTOMER_ERASED, {"id": str(absorbed.id)}),
    ]


def test_a_merge_keeps_the_chain_flat_and_erasing_reaches_every_card_of_it():
    first, second, third = (
        card("A"),
        card("B", email="b@example.com"),
        card("C", email="c@example.com"),
    )
    run("customer.customer.merge", MergeIn(id=second.id, absorbed_id=third.id))
    run("customer.customer.merge", MergeIn(id=first.id, absorbed_id=second.id))
    third.refresh_from_db()
    assert (
        third.merged_into_id == first.id
    )  # C was in B, and B went into A: C points at A
    clear_outbox()

    run("customer.customer.erase", EraseIn(id=first.id))

    assert erased(second)[1:] == erased(third)[1:] == ("", True)
    assert {payload["id"] for _, payload in outbox()} == {
        str(first.id),
        str(second.id),
        str(third.id),
    }


def test_erasing_follows_a_chain_that_is_not_flat():
    first = card("A")
    second = card("B", merged_into=first, deleted_at=NOW)
    third = card("C", email="c@example.com", merged_into=second, deleted_at=NOW)
    run("customer.customer.erase", EraseIn(id=first.id))
    assert erased(third) == ("Deleted customer", "", True)


def test_repeating_the_erasure_of_a_merged_card_announces_every_card_again_and_writes_nothing():
    survivor, absorbed = card("Ana"), card("ana", email="ana@example.com")
    run("customer.customer.merge", MergeIn(id=survivor.id, absorbed_id=absorbed.id))
    run("customer.customer.erase", EraseIn(id=survivor.id))
    clear_outbox()
    run("customer.customer.erase", EraseIn(id=survivor.id, reason="again"))
    assert len(outbox()) == 2
    assert list(absorbed.activity.values_list("text", flat=True)) == [""]
