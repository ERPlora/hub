"""The cards as a CSV file (CUSTOMER-F09): every card the list's search and filters find, in the list's order, with
the columns of the import and the figures, and nothing a spreadsheet would run as a formula."""

import csv
import io

import pytest
from live.errors import PermissionDenied

from apps.customer.models import CustomerGroup, CustomerTag
from apps.customer.schemas.exports import CustomerExportIn

from .conftest import HUB_DB, NOW, card, run


pytestmark = HUB_DB


def exported(role="hub_admin", **params):
    result = run("customer.customer.export", CustomerExportIn(**params), role)
    return result, list(csv.DictReader(io.StringIO(result.csv)))


def test_the_export_settles_its_ties_the_way_the_list_does():
    ids = [card(f"Tie {n}", total_spent=500) for n in range(3)]
    in_order = [row.name for row in sorted(ids, key=lambda row: row.id)]
    _, rows = exported(sort="total_spent", descending=True)
    assert [row["name"] for row in rows] == in_order[::-1]


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
