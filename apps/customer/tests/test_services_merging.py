"""Merging a duplicate into the card that stays (CUSTOMER-F13)."""

import uuid
from datetime import timedelta

import pytest
from live.errors import InvalidPayload, NotFound, PermissionDenied

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
from apps.customer.schemas.merging import MergeIn

from .conftest import HUB_DB, NOW, card, invalid, outbox, run, values

pytestmark = HUB_DB


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


def test_the_employee_does_not_merge(duplicates):
    survivor, absorbed = duplicates
    with pytest.raises(PermissionDenied):
        run(
            "customer.customer.merge",
            MergeIn(id=survivor.id, absorbed_id=absorbed.id),
            "hub_employee",
        )
