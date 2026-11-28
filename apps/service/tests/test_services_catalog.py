"""Writes of the services themselves: create one or many at once, edit, archive and restore."""

import uuid

import pytest
from live.errors import InvalidPayload, NotFound, PermissionDenied

from apps.service.models.catalog import Service
from apps.service.models.settings import ServiceSettings

from .conftest import HUB_DB, events, make_category, make_service, make_tax, payload, run

pytestmark = HUB_DB


def test_create_a_service_with_its_tax_category_and_category(tax):
    hair = make_category("Hair")
    out = run(
        "service.service.create",
        {
            "name": "Haircut",
            "price": 2250,
            "duration_minutes": 30,
            "tax_category_key": tax.key,
            "category": "hair",
        },
    )
    service = Service.objects.get()
    assert (out.name, out.price, out.duration_minutes, out.category_id, out.status) == (
        "Haircut",
        2250,
        30,
        hair.id,
        "active",
    )
    assert (
        service.tax_category,
        service.created_by,
        service.is_bookable,
        service.max_capacity,
    ) == (tax, "tester", True, 1)
    assert events() == ["service.service.created"]
    assert payload("service.service.created") == {
        "id": str(service.id),
        "name": "Haircut",
    }


def test_what_a_new_service_does_not_say_comes_from_the_settings(tax):
    ServiceSettings.objects.create(
        default_duration=45,
        default_buffer_time=10,
        allow_online_booking=False,
        default_tax_category=tax,
    )
    out = run("service.service.create", {"name": "Beard", "price": 1200})
    assert (
        out.duration_minutes,
        out.buffer_before,
        out.buffer_after,
        out.allow_online_booking,
    ) == (45, 10, 10, False)
    assert out.tax_category_key == tax.key
    plain = run(
        "service.service.create",
        {
            "name": "Shave", "price": 1000,
            "duration_minutes": 20,
            "buffer_before": 0,
            "allow_online_booking": True,
        },
    )
    assert (
        plain.duration_minutes,
        plain.buffer_before,
        plain.buffer_after,
        plain.allow_online_booking,
    ) == (20, 0, 10, True)


def test_without_settings_a_new_service_lasts_an_hour_with_no_buffer_and_online_booking(
    tax,
):
    out = run("service.service.create", {"name": "Cut", "price": 2000, "tax_category_key": tax.key})
    assert (out.duration_minutes, out.buffer_before, out.allow_online_booking) == (
        60,
        0,
        True,
    )


def test_a_service_without_a_tax_category_is_refused_under_the_field():
    with pytest.raises(InvalidPayload) as refused:
        run("service.service.create", {"name": "Cut", "price": 2000})
    assert refused.value.code == "service.tax_category_required"
    assert refused.value.fields == {
        "tax_category_key": "Pick a tax category: without one the service cannot be charged."
    }
    assert not Service.objects.exists() and events() == []


def test_an_unknown_or_deactivated_tax_category_is_refused(tax):
    off = make_tax("test.off", "Off", is_active=False)
    for key in ("nope.key", off.key):
        with pytest.raises(InvalidPayload) as refused:
            run("service.service.create", {"name": "Cut", "price": 2000, "tax_category_key": key})
        assert refused.value.fields == {
            "tax_category_key": "That tax category does not exist in Taxes or is deactivated."
        }


def test_a_deleted_category_is_not_available(tax):
    gone = make_category("Gone", is_deleted=True)
    with pytest.raises(InvalidPayload) as refused:
        run(
            "service.service.create",
            {"name": "Cut", "price": 2000, "tax_category_key": tax.key, "category_id": str(gone.id)},
        )
    assert refused.value.code == "service.category_unavailable"
    assert refused.value.fields == {
        "category_id": "That category is not available: it does not exist in this business or it has been deleted."
    }


def test_an_employee_creates_a_service_but_does_not_edit_it(tax):
    out = run(
        "service.service.create",
        {"name": "Cut", "price": 2000, "tax_category_key": tax.key},
        role="hub_employee",
    )
    with pytest.raises(PermissionDenied):
        run(
            "service.service.update",
            {"id": str(out.id), "price": 1},
            role="hub_employee",
        )


def test_an_edit_changes_only_what_it_sends_and_null_empties_the_category(tax):
    hair = make_category("Hair")
    cut = make_service(
        "Cut",
        tax=tax,
        category=hair,
        price=2000,
        duration_minutes=30,
        pricing_type="from",
        min_price=1500,
        max_price=3000,
    )
    out = run(
        "service.service.update", {"service": "cut", "price": 2200, "category_id": None}
    )
    assert (
        out.price,
        out.duration_minutes,
        out.category_id,
        out.min_price,
        out.tax_category_key,
    ) == (2200, 30, None, 1500, tax.key)
    assert events() == ["service.service.updated"]
    run("service.service.update", {"id": str(cut.id), "price": 2200})
    assert events() == ["service.service.updated"]


def test_an_edit_keeps_the_price_range_right_side_up(tax):
    cut = make_service(
        "Cut", tax=tax, pricing_type="from", min_price=1500, max_price=3000
    )
    with pytest.raises(InvalidPayload) as refused:
        run("service.service.update", {"id": str(cut.id), "min_price": 4000})
    assert (
        refused.value.message == "The minimum price cannot be above the maximum price."
    )


def test_an_edit_changes_the_tax_category_and_never_empties_it(tax):
    other = make_tax("test.other", "Other")
    cut = make_service("Cut", tax=tax)
    assert (
        run(
            "service.service.update", {"id": str(cut.id), "tax_category_key": other.key}
        ).tax_category_key
        == other.key
    )
    assert (
        run(
            "service.service.update", {"id": str(cut.id), "tax_category_key": None}
        ).tax_category_key
        == other.key
    )


def test_editing_a_service_that_does_not_exist():
    with pytest.raises(NotFound) as missing:
        run("service.service.update", {"id": str(uuid.uuid7()), "price": 1})
    assert missing.value.message == "That service does not exist in this business."


def test_archive_and_restore_once_each(tax):
    cut = make_service("Cut", tax=tax)
    out = run("service.service.archive", {"id": str(cut.id)})
    assert (out.status, out.is_active, out.archived_at is not None) == (
        "archived",
        False,
        True,
    )
    run("service.service.archive", {"id": str(cut.id)})
    restored = run("service.service.restore", {"id": str(cut.id)})
    run("service.service.restore", {"id": str(cut.id)})
    assert (restored.status, restored.archived_at) == ("active", None)
    assert events() == ["service.service.archived", "service.service.restored"]


def test_only_the_owner_and_the_admin_archive(tax):
    cut = make_service("Cut", tax=tax)
    with pytest.raises(PermissionDenied):
        run("service.service.archive", {"id": str(cut.id)}, role="hub_manager")
    assert (
        run("service.service.restore", {"id": str(cut.id)}, role="hub_manager").status
        == "active"
    )


def test_a_bulk_create_creates_all_of_them_with_the_settings_and_an_event_each(tax):
    ServiceSettings.objects.create(default_duration=40, default_tax_category=tax)
    hair = make_category("Hair")
    out = run(
        "service.service.bulk_create",
        {
            "services": [
                {"name": "Cut", "price": 2000, "category": "Hair"},
                {"name": "Beard", "price": 1200, "duration_minutes": 15},
            ]
        },
    )
    created = {service.name: service for service in Service.objects.all()}
    assert (out.created, out.ids) == (2, [created["Cut"].id, created["Beard"].id])
    assert (
        created["Cut"].duration_minutes,
        created["Cut"].category,
        created["Beard"].duration_minutes,
    ) == (40, hair, 15)
    assert created["Beard"].tax_category == tax
    assert events() == ["service.service.created", "service.service.created"]


def test_a_bulk_create_with_one_bad_line_creates_nothing_and_names_the_line(tax):
    with pytest.raises(InvalidPayload) as refused:
        run(
            "service.service.bulk_create",
            {
                "services": [
                    {"name": "Cut", "price": 2000, "tax_category_key": tax.key},
                    {"name": "Beard", "price": 1200, "tax_category_key": "nope"},
                ]
            },
        )
    assert refused.value.fields == {
        "services.1.tax_category_key": "That tax category does not exist in Taxes or is deactivated."
    }
    assert not Service.objects.exists() and events() == []


def test_no_event_without_a_change(tax):
    cut = make_service("Cut", tax=tax)
    run("service.service.update", {"id": str(cut.id)})
    assert events() == []
