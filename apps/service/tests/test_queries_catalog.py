"""The services of the catalog: their list with its filters, sort and pages, one named as a person says it, the
catalog the till sells from and what the catalog counts."""

import pytest
from django.utils import timezone
from live.errors import Conflict, NotFound, PermissionDenied

from apps.service.schemas.catalog import ServiceForSaleIn, ServiceListIn
from apps.service.schemas.fields import ServiceRefIn

from .conftest import HUB_DB, make_category, make_service, make_tax, names, run

pytestmark = HUB_DB


def test_a_service_without_a_family_stays_last_in_both_directions():
    tax = make_tax()
    hair, nails = make_category("Hair"), make_category("Nails")
    make_service("Cut", tax=tax, category=hair)
    make_service("Manicure", tax=tax, category=nails)
    make_service("Loose", tax=tax)

    def listed(sort):
        return names(run("service.service.list", ServiceListIn(sort=sort)))

    assert listed("category_name") == ["Cut", "Manicure", "Loose"]
    assert listed("-category_name") == ["Manicure", "Cut", "Loose"]


def test_the_list_shows_the_offered_services_by_name_with_their_category_and_status(
    tax,
):
    hair = make_category("Hair")
    make_service("Haircut", tax=tax, category=hair, price=2000, duration_minutes=30)
    make_service("Beard", tax=None)
    make_service("Old perm", tax=tax, is_active=False)
    page = run("service.service.list", ServiceListIn())
    assert names(page) == ["Beard", "Haircut"]
    cut = page.rows[1]
    assert (
        cut.category_name,
        cut.price,
        cut.duration_minutes,
        cut.status,
        cut.needs_tax_setup,
    ) == (
        "Hair",
        2000,
        30,
        "active",
        False,
    )
    assert (
        page.rows[0].status,
        page.rows[0].needs_tax_setup,
        cut.tax_category_key,
    ) == ("unconfigured", True, tax.key)


def test_a_deactivated_tax_category_leaves_the_service_unconfigured(tax):
    tax.is_active = False
    tax.save()
    make_service("Cut", tax=tax)
    assert run("service.service.list", ServiceListIn()).rows[0].status == "unconfigured"


def test_the_status_filter_shows_the_archived_view_or_narrows_the_offered_ones(tax):
    make_service("Cut", tax=tax)
    make_service("Beard")
    make_service("Perm", tax=tax, is_active=False, archived_at=timezone.now())
    assert names(run("service.service.list", ServiceListIn(status="archived"))) == [
        "Perm"
    ]
    assert names(run("service.service.list", ServiceListIn(status="unconfigured"))) == [
        "Beard"
    ]
    assert names(run("service.service.list", ServiceListIn(status="active"))) == ["Cut"]


def test_search_filters_and_sort(tax):
    hair, nails = make_category("Hair"), make_category("Nails")
    make_service("Haircut", tax=tax, category=hair, price=2000, duration_minutes=30)
    make_service(
        "Colour",
        tax=tax,
        category=hair,
        price=4500,
        duration_minutes=90,
        pricing_type="from",
    )
    make_service("Manicure", tax=tax, category=nails, price=1500, duration_minutes=45)
    assert names(run("service.service.list", ServiceListIn(search="hair"))) == [
        "Colour",
        "Haircut",
    ]
    assert names(run("service.service.list", ServiceListIn(category="nails"))) == [
        "Manicure"
    ]
    assert names(run("service.service.list", ServiceListIn(category_id=hair.id))) == [
        "Colour",
        "Haircut",
    ]
    assert names(run("service.service.list", ServiceListIn(pricing_type="from"))) == [
        "Colour"
    ]
    assert names(
        run("service.service.list", ServiceListIn(price_min=1600, price_max=4500))
    ) == ["Colour", "Haircut"]
    assert names(
        run("service.service.list", ServiceListIn(duration_min=40, duration_max=60))
    ) == ["Manicure"]
    assert names(run("service.service.list", ServiceListIn(sort="-price"))) == [
        "Colour",
        "Haircut",
        "Manicure",
    ]
    assert names(run("service.service.list", ServiceListIn(sort="category_name"))) == [
        "Colour",
        "Haircut",
        "Manicure",
    ]


def test_the_list_pages_with_a_stable_order(tax):
    for name in ("A", "B", "C"):
        make_service(name, tax=tax)
    first = run("service.service.list", ServiceListIn(limit=2))
    second = run("service.service.list", ServiceListIn(limit=2, offset=2))
    assert (names(first), names(second), first.total) == (["A", "B"], ["C"], 3)


def test_get_names_a_service_by_id_or_by_name_and_says_when_a_name_fits_several(tax):
    cut = make_service("Haircut", tax=tax)
    make_service("Haircut and wash", tax=tax)
    make_service("Colour", tax=tax)
    assert run("service.service.get", ServiceRefIn(id=cut.id)).name == "Haircut"
    assert run("service.service.get", ServiceRefIn(service="haircut")).id == cut.id
    assert run("service.service.get", ServiceRefIn(service="colo")).name == "Colour"
    with pytest.raises(Conflict) as ambiguous:
        run("service.service.get", ServiceRefIn(service="hair"))
    assert ambiguous.value.code == "service.service_ambiguous"
    assert "Haircut, Haircut and wash" in ambiguous.value.message
    with pytest.raises(NotFound) as missing:
        run("service.service.get", ServiceRefIn(service="Perm"))
    assert missing.value.message == "That service does not exist in this business."


def test_get_still_finds_an_archived_service_by_id(tax):
    old = make_service("Perm", tax=tax, is_active=False)
    assert run("service.service.get", ServiceRefIn(id=old.id)).status == "archived"


def test_the_sale_catalog_is_the_offered_services_with_what_prices_a_line(tax):
    hair = make_category("Hair")
    make_service("Haircut", tax=tax, category=hair, price=2000)
    make_service("Beard")
    make_service("Perm", tax=tax, is_active=False)
    page = run("service.service.list_for_sale", ServiceForSaleIn())
    assert names(page) == ["Beard", "Haircut"]
    cut = page.rows[1]
    assert (
        cut.category_name,
        cut.tax_category_key,
        cut.needs_tax_setup,
        cut.pricing_type,
    ) == ("Hair", tax.key, False, "fixed")
    assert page.rows[0].needs_tax_setup is True
    assert names(
        run("service.service.list_for_sale", ServiceForSaleIn(category_id=hair.id))
    ) == ["Haircut"]


def test_an_employee_reads_the_catalog(tax):
    make_service("Cut", tax=tax)
    assert names(run("service.service.list", ServiceListIn(), role="hub_employee")) == [
        "Cut"
    ]


def test_a_role_without_the_permission_is_refused():
    with pytest.raises(PermissionDenied):
        run("service.service.list", ServiceListIn(), role="nobody")


def test_the_catalog_status_counts_what_can_be_charged(tax):
    make_service("Cut", tax=tax)
    make_service("Beard")
    make_service("Perm", tax=tax, is_active=False)
    status = run("service.catalog.status")
    assert (status.services, status.sellable_services, status.needs_tax_setup) == (
        2,
        1,
        1,
    )
