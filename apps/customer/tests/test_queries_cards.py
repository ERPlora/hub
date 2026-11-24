"""The cards: the list with its search, filters and order (CUSTOMER-F02), one card whole (CUSTOMER-F03, F30), the
figures of every card (``stats.pg``) and the cards a phone number is (CUSTOMER-F10, ``by_phone.pg``)."""

from datetime import timedelta

import pytest
from live.errors import PermissionDenied

from apps.customer.models import Consent, CustomerGroup, CustomerTag, CustomField, CustomFieldValue
from apps.customer.schemas.cards import ByPhoneIn, CustomerListIn, CustomerStatsIn
from apps.customer.schemas.fields import CustomerRefIn

from .conftest import HUB_DB, NOW, card, run


pytestmark = HUB_DB


def listed(role="hub_admin", **params):
    return run("customer.customer.list", CustomerListIn(**params), role)


def names(page):
    return [row.name for row in page.rows]


# customer.customer.list (CUSTOMER-F02)


def test_an_empty_list():
    assert listed().model_dump() == {"rows": [], "total": 0, "limit": 50, "offset": 0}


def test_by_name_a_to_z_with_its_columns():
    bea = card(
        "Bea",
        email="bea@example.com",
        phone="+34600111222",
        total_spent=1250,
        total_purchases=2,
    )
    card("Ana")
    page = listed()
    assert names(page) == ["Ana", "Bea"]
    row = page.rows[1].model_dump()
    assert row == {
        "id": bea.id,
        "name": "Bea",
        "email": "bea@example.com",
        "phone": "+34600111222",
        "tax_id": "",
        "company_name": "",
        "lifecycle_stage": "lead",
        "source": "walk_in",
        "is_active": True,
        "total_purchases": 2,
        "total_spent": 1250,
        "last_purchase_at": None,
    }


def test_pages_are_stable_with_the_id_as_tie_break():
    cards = [card("Same") for _ in range(5)]
    pages = [listed(limit=2, offset=offset) for offset in (0, 2, 4)]
    assert [row.id for page in pages for row in page.rows] == sorted(
        c.id for c in cards
    )
    assert [page.total for page in pages] == [5, 5, 5]


def test_deleted_merged_and_erased_cards_are_left_out_but_inactive_ones_stay():
    card("Alive")
    card("Inactive", is_active=False)
    card("Deleted", deleted_at=NOW)
    card("Erased", deleted_at=NOW, erased_at=NOW)
    assert names(listed()) == ["Alive", "Inactive"]


def test_search_ignores_case_and_accents_across_name_email_phone_tax_id_and_company():
    card("María García")
    card("Bea", email="BEA@Example.com")
    card("Carla", tax_id="12345678Z")
    card("Dora", company_name="Peluquería Sol")
    assert names(listed(search="garcia")) == ["María García"]
    assert names(listed(search="bea@example")) == ["Bea"]
    assert names(listed(search="12345678z")) == ["Carla"]
    assert names(listed(search="PELUQUERIA")) == ["Dora"]


@pytest.mark.parametrize(
    "typed", ["600 111 222", "0034 600-111-222", "+34 600 111 222", "600.111.222"]
)
def test_a_phone_is_found_however_it_is_typed(typed):
    card("Ana", phone="+34600111222")
    card("Bea", phone="+34611222333")
    assert names(listed(search=typed)) == ["Ana"]


def test_a_british_number_with_its_bracketed_zero_finds_its_card():
    card("Liz", phone="+447911123456")
    assert names(listed(search="+44 (0)7911 123456")) == ["Liz"]


def test_filters():
    card(
        "Ana",
        lifecycle_stage="vip",
        source="whatsapp",
        total_spent=5000,
        total_purchases=3,
        email="ana@a.com",
    )
    card(
        "Bea",
        lifecycle_stage="lead",
        is_active=False,
        total_spent=100,
        total_purchases=1,
        phone="+34600111222",
    )
    card("Carla", company_name="ACME", tax_id="B123", last_purchase_at=NOW)
    assert names(listed(lifecycle_stage="vip")) == ["Ana"]
    assert names(listed(source="whatsapp")) == ["Ana"]
    assert names(listed(is_active=False)) == ["Bea"]
    assert names(listed(spent_min=1000)) == ["Ana"]
    assert names(listed(spent_max=1000)) == ["Bea", "Carla"]
    assert names(listed(purchases_min=2, purchases_max=3)) == ["Ana"]
    assert names(listed(name="arl")) == ["Carla"]
    assert names(listed(email="@A.COM")) == ["Ana"]
    assert names(listed(phone="600 111")) == ["Bea"]
    assert names(listed(tax_id="b12", company_name="acme")) == ["Carla"]
    assert names(
        listed(last_purchase_from=NOW.date(), last_purchase_to=NOW.date())
    ) == ["Carla"]
    assert names(listed(last_purchase_from=(NOW + timedelta(days=1)).date())) == []


def test_sort_by_any_column_with_empties_last():
    card("Ana", total_spent=300, last_purchase_at=NOW)
    card("Bea", total_spent=900)
    card("Carla", total_spent=100, last_purchase_at=NOW - timedelta(days=1))
    assert names(listed(sort="total_spent", descending=True)) == ["Bea", "Ana", "Carla"]
    assert names(listed(sort="last_purchase_at")) == ["Carla", "Ana", "Bea"]
    assert names(listed(sort="last_purchase_at", descending=True)) == [
        "Ana",
        "Carla",
        "Bea",
    ]


def test_every_role_with_view_may_list_and_none_other():
    card("Ana")
    assert listed(role="hub_employee").total == 1
    with pytest.raises(PermissionDenied):
        listed(role="nobody")


# customer.customer.detail (CUSTOMER-F03, F30)


def test_the_detail_is_the_whole_card_with_its_groups_tags_fields_and_consent():
    ana = card(
        "Ana",
        email="ana@example.com",
        phone="+34600111222",
        address="Calle Mayor 1",
        city="Madrid",
        postal_code="28001",
        country="ES",
        avatar="https://example.com/ana.png",
        notes="Prefers mornings",
        preferred_channel="whatsapp",
    )
    vip = CustomerGroup.objects.create(name="VIP")
    tag = CustomerTag.objects.create(name="Moroso")
    ana.groups.add(vip)
    ana.tags.add(tag)
    allergies = CustomField.objects.create(
        name="Allergies", sort_order=2, is_required=True
    )
    CustomField.objects.create(
        name="Hair", field_type="select", options=["Short", "Long"], sort_order=1
    )
    CustomField.objects.create(name="Old", is_active=False)
    CustomFieldValue.objects.create(customer=ana, field=allergies, value="Latex")
    Consent.objects.create(
        customer=ana,
        channel="email",
        state="granted",
        contact_point="ana@example.com",
        occurred_at=NOW,
    )

    detail = run("customer.customer.detail", CustomerRefIn(id=ana.id), "hub_employee")

    assert (
        detail.name,
        detail.address,
        detail.country,
        detail.avatar,
        detail.notes,
    ) == (
        "Ana",
        "Calle Mayor 1",
        "ES",
        "https://example.com/ana.png",
        "Prefers mornings",
    )
    assert (detail.group_ids, detail.tag_ids) == ([vip.id], [tag.id])
    assert [
        (field.name, field.value, field.is_required) for field in detail.custom_fields
    ] == [
        ("Hair", "", False),
        ("Allergies", "Latex", True),
    ]
    assert detail.custom_fields[0].options == ["Short", "Long"]
    assert [(row.channel, row.state, row.contact_point) for row in detail.consent] == [
        ("email", "granted", "ana@example.com")
    ]
    assert (detail.marketing_consent, detail.consent_date) == (True, NOW)


def test_a_withdrawn_channel_is_no_marketing_consent():
    ana = card("Ana")
    Consent.objects.create(
        customer=ana,
        channel="sms",
        state="granted",
        occurred_at=NOW - timedelta(days=1),
    )
    Consent.objects.create(
        customer=ana, channel="sms", state="withdrawn", occurred_at=NOW
    )
    detail = run("customer.customer.detail", CustomerRefIn(id=ana.id))
    assert [(row.channel, row.state) for row in detail.consent] == [
        ("sms", "withdrawn")
    ]
    assert (detail.marketing_consent, detail.consent_date) == (False, None)


# customer.customer.stats (stats.pg)


def test_stats_count_the_live_cards_only():
    card("A", total_spent=5000)
    card("B", total_spent=12000, lifecycle_stage="vip")
    card("C", is_active=False)
    card("Gone", total_spent=999, lifecycle_stage="vip", deleted_at=NOW)
    stats = run("customer.customer.stats", CustomerStatsIn())
    assert stats.model_dump() == {
        "total": 3,
        "active": 2,
        "vip": 1,
        "total_revenue": 17000,
    }


def test_empty_stats():
    assert run("customer.customer.stats", CustomerStatsIn()).model_dump() == {
        "total": 0,
        "active": 0,
        "vip": 0,
        "total_revenue": 0,
    }


# customer.customer.by_phone (CUSTOMER-F10, by_phone.pg)


def found(phone):
    return sorted(
        row.name
        for row in run("customer.customer.by_phone", ByPhoneIn(phone=phone)).rows
    )


@pytest.mark.parametrize(
    "asked",
    [
        "34600111222",
        "+34600111222",
        "600 111 222",
        "0034 600-111-222",
        "(+34) 600.11.12.22",
    ],
)
def test_every_usual_way_of_typing_the_number_finds_the_card(asked):
    card("Ana", phone="+34600111222")
    assert found(asked) == ["Ana"]


def test_another_countrys_code_in_front_is_somebody_else():
    card("Ana", phone="+34600111333")
    card("Fran", phone="+33612345678")
    assert found("33600111333") == []
    assert found("33612345678") == ["Fran"]
    assert found("612345678") == []  # a Spanish reading of the French digits


def test_whatsapp_digits_of_a_foreign_number_find_its_card():
    card("Liz", phone="+447911123456")
    assert found("447911123456") == ["Liz"]
    assert found("+44 (0)7911 123456") == ["Liz"]


def test_containing_is_not_being():
    card("Ana", phone="+34600111222")
    assert found("111222") == []
    assert found("346001112229") == []
    assert found("34699999999") == []


def test_two_cards_with_the_number_both_answer_by_name_and_deleted_ones_never():
    card("Bea", phone="+34600111222")
    card("Ana", phone="+34600111222")
    card("Gone", phone="+34600111222", deleted_at=NOW)
    page = run("customer.customer.by_phone", ByPhoneIn(phone="600111222"))
    assert [row.name for row in page.rows] == ["Ana", "Bea"]
    assert set(page.rows[0].model_dump()) == {"id", "name", "email", "phone"}


@pytest.mark.parametrize("asked", ["", None, "+ -", "600111", "call me"])
def test_no_number_is_nobody_never_the_whole_list(asked):
    card("Ana", phone="+34600111222")
    card("Empty")
    assert found(asked) == []
