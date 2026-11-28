"""The vouchers of the catalog: their list with their lines and status, and one by its id or name."""

import pytest
from live.errors import Conflict, NotFound

from apps.service.schemas.fields import PackageRefIn
from apps.service.schemas.packages import PackageListIn

from .conftest import HUB_DB, make_customer, make_grant, make_package, make_service, names, run

pytestmark = HUB_DB


def test_packages_list_the_live_ones_with_their_lines_and_status(tax):
    cut, colour = (
        make_service("Cut", tax=tax, price=2000),
        make_service("Colour", tax=tax, price=4500),
    )
    make_package("Bono cortes", [cut, colour], sessions=5, max_uses=5, fixed_price=9000)
    make_package("Old bono", [cut], is_active=False)
    make_package("Gone, never sold", [cut], is_deleted=True)
    page = run("service.package.list", PackageListIn())
    assert names(page) == ["Bono cortes", "Old bono"]
    bono = page.rows[0]
    assert (bono.item_count, bono.status, bono.fixed_price, bono.grant_count) == (
        2,
        "active",
        9000,
        0,
    )
    assert [
        (item.service_name, item.sessions, item.service_price) for item in bono.items
    ] == [
        ("Cut", 5, 2000),
        ("Colour", 5, 4500),
    ]
    assert names(run("service.package.list", PackageListIn(status="archived"))) == [
        "Old bono"
    ]
    assert names(run("service.package.list", PackageListIn(search="cortes"))) == [
        "Bono cortes"
    ]


def test_the_deleted_view_shows_only_the_packages_somebody_bought(tax):
    cut = make_service("Cut", tax=tax)
    sold = make_package("Sold bono", [cut], is_deleted=True)
    make_package("Never sold", [cut], is_deleted=True)
    make_grant(sold, make_customer())
    page = run("service.package.list", PackageListIn(status="deleted"))
    assert [(row.name, row.status, row.grant_count) for row in page.rows] == [
        ("Sold bono", "deleted", 1)
    ]


def test_get_names_a_package_by_name_and_says_when_it_fits_several():
    make_package("Bono 5 cortes")
    make_package("Bono 10 cortes")
    assert (
        run("service.package.get", PackageRefIn(package="bono 5")).name
        == "Bono 5 cortes"
    )
    with pytest.raises(Conflict) as ambiguous:
        run("service.package.get", PackageRefIn(package="cortes"))
    assert ambiguous.value.code == "service.package_ambiguous"


def test_a_deleted_package_is_still_read_by_its_id_but_no_longer_by_its_name(tax):
    # Its vouchers sold still name it: their «Bonos vendidos» opens it by its id.
    sold = make_package("Sold bono", [make_service("Cut", tax=tax)], is_deleted=True)
    shown = run("service.package.get", PackageRefIn(id=sold.id))
    assert (shown.id, shown.status, [item.service_name for item in shown.items]) == (
        sold.id,
        "deleted",
        ["Cut"],
    )
    with pytest.raises(NotFound) as gone:
        run("service.package.get", PackageRefIn(package="sold bono"))
    assert gone.value.code == "service.package_not_found"
