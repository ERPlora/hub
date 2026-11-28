"""Writes of the packages: create, edit and delete, never touching the vouchers already sold."""

import pytest
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied

from apps.service.models.packages import Package, PackageItem

from .conftest import HUB_DB, events, make_customer, make_grant, make_package, make_service, run

pytestmark = HUB_DB


def test_create_a_package_with_its_lines(tax):
    cut, colour = make_service("Cut", tax=tax), make_service("Colour", tax=tax)
    out = run(
        "service.package.create",
        {
            "name": "Bono 5 cortes",
            "max_uses": 5,
            "validity_days": 180,
            "fixed_price": 9000,
            "discount_type": "percentage",
            "discount_percent_bp": 1050,
            "items": [
                {"service": "Cut", "sessions": 5},
                {"service_id": str(colour.id)},
            ],
        },
    )
    assert (
        out.name,
        out.max_uses,
        out.validity_days,
        out.fixed_price,
        out.discount_percent_bp,
        out.item_count,
    ) == (
        "Bono 5 cortes",
        5,
        180,
        9000,
        1050,
        2,
    )
    assert [(item.service_id, item.sessions) for item in out.items] == [
        (cut.id, 5),
        (colour.id, 1),
    ]
    assert events() == ["service.package.created"]


def test_a_package_line_needs_an_offered_service_once(tax):
    cut = make_service("Cut", tax=tax)
    old = make_service("Perm", tax=tax, is_active=False)
    with pytest.raises(InvalidPayload) as archived:
        run(
            "service.package.create",
            {"name": "Bono", "items": [{"service_id": str(old.id)}]},
        )
    assert archived.value.fields == {
        "items.0.service_id": "That service is archived: it cannot go into a voucher."
    }
    with pytest.raises(InvalidPayload) as repeated:
        run(
            "service.package.create",
            {
                "name": "Bono",
                "items": [{"service": "Cut"}, {"service_id": str(cut.id)}],
            },
        )
    assert repeated.value.fields == {
        "items": "A service is repeated in the lines: each service goes once."
    }
    assert not Package.objects.exists()


def test_a_package_name_is_taken_while_the_other_lives():
    make_package("Bono 5")
    with pytest.raises(Conflict) as taken:
        run(
            "service.package.create",
            {"name": "bono 5", "items": [{"service_id": str(make_service().id)}]},
        )
    assert taken.value.code == "service.package_name_taken"
    assert taken.value.fields == {
        "name": "There is already a package with that name. Pick another name."
    }


def test_renaming_a_package_to_a_name_already_taken_is_refused_under_name():
    # SERVICE-F13: the check on edit is the one of the create (same code, same field), not a database error.
    make_package("Bono 5")
    other = make_package("Bono 10")
    with pytest.raises(Conflict) as taken:
        run("service.package.update", {"id": str(other.id), "name": " BONO 5 "})
    assert taken.value.code == "service.package_name_taken"
    assert taken.value.fields == {"name": "There is already a package with that name. Pick another name."}
    assert Package.objects.get(pk=other.pk).name == "Bono 10"


def test_editing_a_package_never_touches_what_was_sold_and_null_removes_limits(tax):
    package = make_package(
        "Bono",
        [make_service("Cut", tax=tax)],
        max_uses=5,
        validity_days=90,
        fixed_price=9000,
    )
    grant = make_grant(package, make_customer())
    out = run(
        "service.package.update",
        {"package": "bono", "max_uses": 10, "validity_days": None, "name": "Bono 10"},
    )
    grant.refresh_from_db()
    assert (out.max_uses, out.validity_days, out.fixed_price, out.name) == (
        10,
        None,
        9000,
        "Bono 10",
    )
    assert (grant.max_uses, grant.validity_days) == (5, 90)
    assert events() == ["service.package.updated"]


def test_deleting_a_package_keeps_its_lines_for_the_vouchers_sold(tax):
    package = make_package("Bono", [make_service("Cut", tax=tax)])
    run("service.package.delete", {"id": str(package.id)})
    package.refresh_from_db()
    assert (package.is_deleted, PackageItem.objects.count()) == (True, 1)
    assert events() == ["service.package.deleted"]
    with pytest.raises(NotFound):
        run("service.package.delete", {"id": str(package.id)})
    with pytest.raises(PermissionDenied):
        run(
            "service.package.delete",
            {"id": str(make_package("Other").id)},
            role="hub_manager",
        )
