"""How a read names a card: by its id, else by its exact name, phone or email, the live cards only (CUSTOMER-F03,
F30); and how every list sorts: its ties go by the id in the list's own direction."""

import uuid

import pytest
from live.errors import Conflict, NotFound

from apps.customer.models import CustomerGroup, CustomerTag, CustomField, Purchase
from apps.customer.schemas.cards import CustomerListIn
from apps.customer.schemas.custom_fields import FieldListIn
from apps.customer.schemas.fields import CustomerRefIn
from apps.customer.schemas.groups import GroupListIn
from apps.customer.schemas.purchases import PurchaseListIn
from apps.customer.schemas.tags import TagListIn

from .conftest import HUB_DB, NOW, card, run


pytestmark = HUB_DB


def _tied_cards():
    return [card("Same", total_spent=500).id for _ in range(4)], {}, CustomerListIn


def _tied_groups():
    rows = [CustomerGroup.objects.create(name=f"Group {n}") for n in range(4)]
    return [row.id for row in rows], {}, GroupListIn


def _tied_tags():
    rows = [CustomerTag.objects.create(name=f"Tag {n}") for n in range(4)]
    return [row.id for row in rows], {}, TagListIn


def _tied_fields():
    rows = [CustomField.objects.create(name=f"Field {n}") for n in range(4)]
    return [row.id for row in rows], {}, FieldListIn


def _tied_purchases():
    owner = card("Owner")
    rows = [
        Purchase.objects.create(
            customer=owner,
            sale_id=uuid.uuid7(),
            amount=700,
            status="confirmed",
            recorded_at=NOW,
        )
        for _ in range(4)
    ]
    return [row.id for row in rows], {"customer_id": owner.id}, PurchaseListIn


@pytest.mark.parametrize(
    ("operation", "tied", "column"),
    [
        ("customer.customer.list", _tied_cards, "total_spent"),
        ("customer.customer.list", _tied_cards, "last_purchase_at"),
        ("customer.group.list", _tied_groups, "sort_order"),
        ("customer.tag.list", _tied_tags, "color"),
        ("customer.field.list", _tied_fields, "field_type"),
        ("customer.purchase.list", _tied_purchases, "amount"),
    ],
)
def test_ties_go_by_id_in_the_lists_own_direction(operation, tied, column):
    """hub#684 (as in Sales, Cash register, Inventory and Tasks): a descending list is
    the ascending one read backwards, ties included, and its pages neither repeat nor lose rows."""
    ids, filters, schema = tied()
    by_id = sorted(ids)

    def listed(descending, **page):
        params = schema(sort=column, descending=descending, **filters, **page)
        return [row.id for row in run(operation, params).rows]

    assert listed(False) == by_id
    assert listed(True) == by_id[::-1]
    assert [
        row for offset in (0, 2) for row in listed(True, limit=2, offset=offset)
    ] == by_id[::-1]


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
