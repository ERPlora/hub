"""Read operations of the customer app (CUSTOMER-F02, F03, F09, F10, F23, F30 and the catalogue lists).

The cases come from the product's batteries: ``stats.pg``, ``by_phone.pg``,
``groups_customer_count.pg``, ``purchase_ledger.pg`` (history), ``orders_link.pg`` and
``consent_ledger.pg`` (state and history).
"""

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import get

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
    ActivityListIn,
    ActivityPage,
    ByPhoneIn,
    ConsentHistoryIn,
    ConsentPage,
    ConsentStateIn,
    ConsentStateOut,
    CustomerDetailOut,
    CustomerExportIn,
    CustomerListIn,
    CustomerPage,
    CustomerRefIn,
    CustomerStatsIn,
    CustomerStatsOut,
    DivergencePage,
    DivergencesIn,
    ExportOut,
    FieldListIn,
    FieldPage,
    GroupListIn,
    GroupPage,
    OrderCustomerOut,
    OrderIn,
    OrderListIn,
    OrderPage,
    PhoneMatchOut,
    PurchaseListIn,
    PurchasePage,
    TagListIn,
    TagPage,
)

from .conftest import run

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)


def card(name="Ana García", **fields):
    return Customer.objects.create(name=name, **fields)


def listed(role="hub_admin", **params):
    return run("customer.customer.list", CustomerListIn(**params), role)


def names(page):
    return [row.name for row in page.rows]


# Declarations


@pytest.mark.parametrize(
    ("name", "permission", "input", "output", "expose_api"),
    [
        (
            "customer.customer.list",
            "customer.view",
            CustomerListIn,
            CustomerPage,
            False,
        ),
        (
            "customer.customer.detail",
            "customer.view",
            CustomerRefIn,
            CustomerDetailOut,
            False,
        ),
        (
            "customer.customer.stats",
            "customer.view",
            CustomerStatsIn,
            CustomerStatsOut,
            False,
        ),
        (
            "customer.customer.by_phone",
            "customer.view",
            ByPhoneIn,
            PhoneMatchOut,
            False,
        ),
        (
            "customer.customer.export",
            "customer.export",
            CustomerExportIn,
            ExportOut,
            False,
        ),
        ("customer.group.list", "customer.view", GroupListIn, GroupPage, False),
        ("customer.tag.list", "customer.view", TagListIn, TagPage, False),
        ("customer.field.list", "customer.view", FieldListIn, FieldPage, False),
        (
            "customer.activity.list",
            "customer.view",
            ActivityListIn,
            ActivityPage,
            False,
        ),
        (
            "customer.purchase.list",
            "customer.view",
            PurchaseListIn,
            PurchasePage,
            False,
        ),
        (
            "customer.purchase.divergences",
            "customer.view",
            DivergencesIn,
            DivergencePage,
            False,
        ),
        (
            "customer.consent.state",
            "customer.view",
            ConsentStateIn,
            ConsentStateOut,
            True,
        ),
        (
            "customer.consent.history",
            "customer.view",
            ConsentHistoryIn,
            ConsentPage,
            False,
        ),
        ("customer.order.customer", "customer.view", OrderIn, OrderCustomerOut, False),
        ("customer.order.list", "customer.view", OrderListIn, OrderPage, True),
    ],
)
def test_declarations(name, permission, input, output, expose_api):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output, op.expose_api) == (
        "query",
        permission,
        input,
        output,
        expose_api,
    )


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


@pytest.mark.parametrize(
    "reference",
    ["Ana García", "ana garcia", "+34 600 111 222", "600111222", "ANA@example.com"],
)
def test_a_card_is_found_by_its_exact_name_phone_or_email(reference):
    ana = card("Ana García", phone="+34600111222", email="ana@example.com")
    card("Ana García López")
    assert (
        run("customer.customer.detail", CustomerRefIn(customer=reference)).id == ana.id
    )


def test_a_reference_two_cards_share_asks_for_the_id():
    card("Ana")
    card("ana")
    with pytest.raises(Conflict) as excinfo:
        run("customer.customer.detail", CustomerRefIn(customer="Ana"))
    assert excinfo.value.code == "customer.customer_ambiguous"


def test_a_reference_nobody_has_is_not_found():
    with pytest.raises(NotFound) as excinfo:
        run("customer.customer.detail", CustomerRefIn(customer="Nobody"))
    assert excinfo.value.code == "customer.customer_unavailable"


@pytest.mark.parametrize(
    "fields", [{"deleted_at": NOW}, {"deleted_at": NOW, "erased_at": NOW}]
)
def test_a_card_that_is_no_longer_live_is_not_returned(fields):
    gone = card("Gone", **fields)
    with pytest.raises(NotFound) as excinfo:
        run("customer.customer.detail", CustomerRefIn(id=gone.id))
    assert (excinfo.value.status, excinfo.value.code) == (
        404,
        "customer.customer_unavailable",
    )


def test_an_inactive_card_is_returned():
    assert (
        run(
            "customer.customer.detail",
            CustomerRefIn(id=card("Ana", is_active=False).id),
        ).is_active
        is False
    )


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


# customer.customer.export (CUSTOMER-F09)


def exported(role="hub_admin", **params):
    result = run("customer.customer.export", CustomerExportIn(**params), role)
    return result, list(csv.DictReader(io.StringIO(result.csv)))


def test_the_export_is_every_matching_card_not_a_page():
    for n in range(120):
        card(f"Customer {n:03}")
    result, rows = exported()
    assert (result.filename, result.content_type, result.rows, len(rows)) == (
        "customers.csv",
        "text/csv",
        120,
        120,
    )
    assert rows[0]["name"] == "Customer 000"


def test_the_export_columns_follow_the_import_and_add_the_figures():
    ana = card(
        "Ana",
        email="ana@example.com",
        phone="+34600111222",
        tax_id="12345678Z",
        lifecycle_stage="vip",
        total_purchases=3,
        total_spent=1250,
        last_purchase_at=NOW,
        notes="VIP",
    )
    ana.groups.add(
        CustomerGroup.objects.create(name="Gold"),
        CustomerGroup.objects.create(name="Alpha"),
    )
    ana.tags.add(CustomerTag.objects.create(name="Moroso"))
    result, [row] = exported()
    assert result.csv.splitlines()[0] == (
        "name,email,phone,tax_id,company_name,address,city,postal_code,country,lifecycle_stage,notes,"
        "source,is_active,total_purchases,total_spent,last_purchase_at,created_at,groups,tags"
    )
    assert (row["email"], row["tax_id"], row["lifecycle_stage"], row["notes"]) == (
        "ana@example.com",
        "12345678Z",
        "vip",
        "VIP",
    )
    assert (row["total_purchases"], row["total_spent"], row["is_active"]) == (
        "3",
        "12.50",
        "true",
    )
    assert row["last_purchase_at"] == NOW.isoformat()
    assert (row["groups"], row["tags"]) == ("Alpha; Gold", "Moroso")


def test_a_cell_a_spreadsheet_would_run_as_a_formula_gets_an_apostrophe():
    card("=HYPERLINK(1)", phone="+34600111222", notes="@home")
    _, [row] = exported()
    assert (row["name"], row["phone"], row["notes"]) == (
        "'=HYPERLINK(1)",
        "'+34600111222",
        "'@home",
    )


def test_the_export_follows_the_search_and_filters():
    card("Ana", lifecycle_stage="vip")
    card("Bea")
    card("Gone", deleted_at=NOW)
    assert [row["name"] for row in exported(lifecycle_stage="vip")[1]] == ["Ana"]
    assert [row["name"] for row in exported(search="bea")[1]] == ["Bea"]


def test_an_empty_export_is_the_header_only():
    result, rows = exported()
    assert (result.rows, rows, len(result.csv.splitlines())) == (0, [], 1)


def test_only_who_may_export_does_even_through_the_api():
    with pytest.raises(PermissionDenied):
        exported(role="hub_employee")
    assert exported(role="hub_manager")[0].rows == 0


# Groups, tags and fields (groups_customer_count.pg)


def test_the_group_list_counts_the_live_customers_of_each_group():
    vip, wholesale = (
        CustomerGroup.objects.create(name="VIP", sort_order=2),
        CustomerGroup.objects.create(name="Wholesale"),
    )
    for name in ("Ana", "Bea"):
        card(name).groups.add(vip, wholesale)
    card("Gone", deleted_at=NOW).groups.add(vip)
    CustomerGroup.objects.create(name="Old", is_active=False)
    page = run("customer.group.list", GroupListIn())
    assert [(row.name, row.customer_count, row.is_active) for row in page.rows] == [
        ("Old", 0, False),
        ("VIP", 2, True),
        ("Wholesale", 2, True),
    ]
    assert [
        row.name
        for row in run(
            "customer.group.list",
            GroupListIn(is_active=True, sort="sort_order", descending=True),
        ).rows
    ] == [
        "VIP",
        "Wholesale",
    ]
    assert [
        row.name for row in run("customer.group.list", GroupListIn(search="whole")).rows
    ] == ["Wholesale"]
    assert [
        row.name
        for row in run(
            "customer.group.list", GroupListIn(customers_min=1, sort="customer_count")
        ).rows
    ] == [
        "VIP",
        "Wholesale",
    ]


def test_the_tag_list():
    moroso = CustomerTag.objects.create(name="Moroso", color="danger")
    CustomerTag.objects.create(name="Nuevo")
    card("Ana").tags.add(moroso)
    page = run("customer.tag.list", TagListIn(sort="customer_count", descending=True))
    assert [(row.name, row.color, row.customer_count) for row in page.rows] == [
        ("Moroso", "danger", 1),
        ("Nuevo", "primary", 0),
    ]
    assert [
        row.name for row in run("customer.tag.list", TagListIn(color="danger")).rows
    ] == ["Moroso"]


def test_the_field_list_and_its_filters():
    CustomField.objects.create(name="Allergies", is_required=True)
    CustomField.objects.create(name="Hair", field_type="select", options=["Short"])
    CustomField.objects.create(name="Old", is_active=False)
    assert [row.name for row in run("customer.field.list", FieldListIn()).rows] == [
        "Allergies",
        "Hair",
        "Old",
    ]
    assert [
        row.name
        for row in run("customer.field.list", FieldListIn(field_type="select")).rows
    ] == ["Hair"]
    assert [
        row.name
        for row in run("customer.field.list", FieldListIn(is_required=True)).rows
    ] == ["Allergies"]
    assert [
        row.name
        for row in run("customer.field.list", FieldListIn(is_active=False)).rows
    ] == ["Old"]
    assert run("customer.field.list", FieldListIn(search="hai")).rows[0].options == [
        "Short"
    ]


# A card's timeline, purchases, consent and orders


def test_the_activity_is_newest_first_and_searchable():
    ana = card("Ana")
    Activity.objects.create(
        customer=ana,
        kind="note_added",
        text="Prefers mornings",
        created_at=NOW - timedelta(hours=1),
    )
    Activity.objects.create(
        customer=ana, kind="purchase_recorded", related_id="s-1", created_at=NOW
    )
    Activity.objects.create(
        customer=card("Bea"), kind="note_added", text="Someone else"
    )
    page = run("customer.activity.list", ActivityListIn(customer_id=ana.id))
    assert [row.kind for row in page.rows] == ["purchase_recorded", "note_added"]
    assert [
        row.text
        for row in run(
            "customer.activity.list", ActivityListIn(customer="Ana", search="morning")
        ).rows
    ] == ["Prefers mornings"]


def test_the_timeline_of_a_card_that_is_gone_is_not_found():
    with pytest.raises(NotFound):
        run(
            "customer.activity.list",
            ActivityListIn(customer_id=card("Gone", deleted_at=NOW).id),
        )


def test_the_purchases_with_their_amount_and_status():
    ana = card("Ana")
    first = Purchase.objects.create(
        customer=ana,
        sale_id=uuid.uuid7(),
        amount=1250,
        currency="EUR",
        recorded_at=NOW - timedelta(days=1),
    )
    second = Purchase.objects.create(
        customer=ana, sale_id=uuid.uuid7(), amount=300, status="voided", recorded_at=NOW
    )
    page = run("customer.purchase.list", PurchaseListIn(customer_id=ana.id))
    assert [(row.sale_id, row.amount, row.status) for row in page.rows] == [
        (second.sale_id, 300, "voided"),
        (first.sale_id, 1250, "confirmed"),
    ]
    assert [
        row.amount
        for row in run(
            "customer.purchase.list",
            PurchaseListIn(customer_id=ana.id, status="confirmed"),
        ).rows
    ] == [1250]
    assert [
        row.amount
        for row in run(
            "customer.purchase.list",
            PurchaseListIn(customer_id=ana.id, sort="amount", descending=False),
        ).rows
    ] == [300, 1250]
    assert (
        run(
            "customer.purchase.list",
            PurchaseListIn(customer_id=ana.id, search=str(first.sale_id)[-6:]),
        ).total
        == 1
    )


def test_divergences_list_the_cards_whose_figures_disagree_with_their_purchases():
    healthy = card("Healthy", total_purchases=1, total_spent=500)
    Purchase.objects.create(customer=healthy, sale_id=uuid.uuid7(), amount=500)
    Purchase.objects.create(
        customer=healthy, sale_id=uuid.uuid7(), amount=700, status="voided"
    )
    card("Drifted", total_purchases=2, total_spent=900)
    page = run("customer.purchase.divergences", DivergencesIn())
    assert [
        (
            row.name,
            row.total_purchases,
            row.ledger_purchases,
            row.total_spent,
            row.ledger_spent,
        )
        for row in page.rows
    ] == [("Drifted", 2, 0, 900, 0)]


def test_the_consent_state_is_the_last_fact_per_purpose_and_channel():
    ana = card("Ana")
    Consent.objects.create(
        customer=ana,
        channel="email",
        state="granted",
        occurred_at=NOW - timedelta(days=2),
    )
    Consent.objects.create(
        customer=ana,
        channel="email",
        state="withdrawn",
        occurred_at=NOW - timedelta(days=1),
    )
    Consent.objects.create(
        customer=ana,
        channel="email",
        state="granted",
        occurred_at=NOW,
        recorded_by="clara",
    )
    Consent.objects.create(
        customer=ana, channel="sms", state="withdrawn", occurred_at=NOW
    )
    Consent.objects.create(
        customer=ana,
        purpose="surveys",
        channel="email",
        state="granted",
        occurred_at=NOW,
    )
    state = run("customer.consent.state", ConsentStateIn(customer_id=ana.id))
    assert state.customer_id == ana.id
    assert [
        (row.purpose, row.channel, row.state, row.recorded_by) for row in state.rows
    ] == [
        ("marketing", "email", "granted", "clara"),
        ("marketing", "sms", "withdrawn", ""),
        ("surveys", "email", "granted", ""),
    ]


def test_the_consent_history_keeps_every_fact_newest_first():
    ana = card("Ana")
    Consent.objects.create(
        customer=ana,
        channel="email",
        state="granted",
        notice_text="Yes to offers",
        occurred_at=NOW - timedelta(days=1),
    )
    Consent.objects.create(
        customer=ana,
        channel="email",
        state="withdrawn",
        reason="Too many",
        occurred_at=NOW,
    )
    page = run("customer.consent.history", ConsentHistoryIn(customer_id=ana.id))
    assert [(row.state, row.notice_text, row.reason) for row in page.rows] == [
        ("withdrawn", "", "Too many"),
        ("granted", "Yes to offers", ""),
    ]
    assert (
        run(
            "customer.consent.history",
            ConsentHistoryIn(customer_id=ana.id, search="offers"),
        ).total
        == 1
    )


def test_the_customer_of_an_order():
    order = uuid.uuid7()
    ana = card("Ana")
    assert run("customer.order.customer", OrderIn(order_id=order)).customer_id is None
    OrderLink.objects.create(order_id=order, customer=ana)
    assert run("customer.order.customer", OrderIn(order_id=order)).model_dump() == {
        "order_id": order,
        "customer_id": ana.id,
    }
    Customer.objects.filter(pk=ana.pk).update(deleted_at=timezone.now())
    # A card that is no longer available is no customer of the order: the till asks again.
    assert run("customer.order.customer", OrderIn(order_id=order)).customer_id is None


def test_the_orders_of_a_customer_newest_first():
    ana = card("Ana")
    old = OrderLink.objects.create(
        order_id=uuid.uuid7(), customer=ana, linked_at=NOW - timedelta(hours=1)
    )
    new = OrderLink.objects.create(order_id=uuid.uuid7(), customer=ana, linked_at=NOW)
    OrderLink.objects.create(order_id=uuid.uuid7(), customer=card("Bea"))
    page = run("customer.order.list", OrderListIn(customer_id=ana.id))
    assert [row.order_id for row in page.rows] == [new.order_id, old.order_id]
