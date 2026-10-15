"""Write operations of the service app: one operation = one transaction, with its events in the outbox.

Every refusal leaves no trace (nothing written, no event): the checks run before the first write.
"""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get

from apps.service.models import (
    Category,
    Assignment,
    Grant,
    GrantAdjustment,
    Package,
    PackageItem,
    Redemption,
    Service,
    ServiceSettings,
)
from apps.service.schemas import (
    AdjustIn,
    AssignmentPatchIn,
    CategoryPatchIn,
    MemberReleaseIn,
    PackagePatchIn,
    ReassignIn,
    RedeemIn,
    VoidIn,
)

from .conftest import (
    ctx_for,
    make_category,
    make_customer,
    make_grant,
    make_member,
    make_package,
    make_redemption,
    make_service,
    make_tax,
)

pytestmark = pytest.mark.django_db


def run(name, data, role="hub_admin", **ctx):
    op = get(name)
    return op(
        ctx_for(role, **ctx),
        op.input.model_validate(data) if isinstance(data, dict) else data,
    )


def events() -> list[str]:
    return list(OutboxEvent.objects.order_by("id").values_list("name", flat=True))


def payload(name: str) -> dict:
    return OutboxEvent.objects.filter(name=name).latest("id").payload


@pytest.fixture
def tax():
    return make_tax("test.service", "Service — test")


@pytest.mark.parametrize(
    ("name", "permission", "risk"),
    [
        ("service.service.create", "service.add_service", "normal"),
        ("service.service.bulk_create", "service.change_service", "high"),
        ("service.service.update", "service.change_service", "normal"),
        ("service.service.archive", "service.delete_service", "high"),
        ("service.service.restore", "service.change_service", "normal"),
        ("service.category.create", "service.add_category", "normal"),
        ("service.category.update", "service.change_category", "normal"),
        ("service.category.delete", "service.delete_category", "high"),
        ("service.settings.update", "service.manage_settings", "high"),
        ("service.assignment.assign", "service.change_service", "normal"),
        ("service.assignment.update", "service.change_service", "normal"),
        ("service.assignment.remove", "service.change_service", "normal"),
        ("service.assignment.release_member", "service.system", "normal"),
        ("service.package.create", "service.add_package", "normal"),
        ("service.package.update", "service.change_package", "normal"),
        ("service.package.delete", "service.delete_package", "high"),
        ("service.grant.create", "service.grant_package", "normal"),
        ("service.grant.void", "service.void_grant", "high"),
        ("service.grant.adjust", "service.adjust_grant", "high"),
        ("service.grant.redeem", "service.redeem_package", "normal"),
        ("service.grant.reassign", "service.system", "normal"),
        ("service.grant.forget_customer", "service.system", "normal"),
    ],
)
def test_declarations(name, permission, risk):
    op = get(name)
    assert (op.kind, op.permission, op.ai["risk"]) == ("command", permission, risk)
    # The reactions are the platform's: no API key reaches them.
    assert op.expose_api is (permission != "service.system")


# ── Services ──────────────────────────────────────────────────────────────────────────────────


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
    out = run("service.service.create", {"name": "Beard"})
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
            "name": "Shave",
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
    out = run("service.service.create", {"name": "Cut", "tax_category_key": tax.key})
    assert (out.duration_minutes, out.buffer_before, out.allow_online_booking) == (
        60,
        0,
        True,
    )


def test_a_service_without_a_tax_category_is_refused_under_the_field():
    with pytest.raises(InvalidPayload) as refused:
        run("service.service.create", {"name": "Cut"})
    assert refused.value.code == "service.tax_category_required"
    assert refused.value.fields == {
        "tax_category_key": "Pick a tax category: without one the service cannot be charged."
    }
    assert not Service.objects.exists() and events() == []


def test_an_unknown_or_deactivated_tax_category_is_refused(tax):
    off = make_tax("test.off", "Off", is_active=False)
    for key in ("nope.key", off.key):
        with pytest.raises(InvalidPayload) as refused:
            run("service.service.create", {"name": "Cut", "tax_category_key": key})
        assert refused.value.fields == {
            "tax_category_key": "That tax category does not exist in Taxes or is deactivated."
        }


def test_a_deleted_category_is_not_available(tax):
    gone = make_category("Gone", is_deleted=True)
    with pytest.raises(InvalidPayload) as refused:
        run(
            "service.service.create",
            {"name": "Cut", "tax_category_key": tax.key, "category_id": str(gone.id)},
        )
    assert refused.value.code == "service.category_unavailable"
    assert refused.value.fields == {
        "category_id": "That category is not available: it does not exist in this business or it has been deleted."
    }


def test_an_employee_creates_a_service_but_does_not_edit_it(tax):
    out = run(
        "service.service.create",
        {"name": "Cut", "tax_category_key": tax.key},
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
                {"name": "Beard", "duration_minutes": 15},
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
                    {"name": "Cut", "tax_category_key": tax.key},
                    {"name": "Beard", "tax_category_key": "nope"},
                ]
            },
        )
    assert refused.value.fields == {
        "services.1.tax_category_key": "That tax category does not exist in Taxes or is deactivated."
    }
    assert not Service.objects.exists() and events() == []


# ── Categories ────────────────────────────────────────────────────────────────────────────────


def test_create_a_category_inside_another_one():
    hair = make_category("Hair")
    out = run(
        "service.category.create", {"name": "Colour", "parent": "hair", "sort_order": 3}
    )
    assert (out.parent_id, out.parent_name, out.sort_order, out.service_count) == (
        hair.id,
        "Hair",
        3,
        0,
    )
    assert events() == ["service.category.created"]


def test_a_category_name_is_taken_ignoring_case_and_spaces():
    make_category("Hair")
    with pytest.raises(Conflict) as taken:
        run("service.category.create", {"name": "  HAIR "})
    assert taken.value.code == "service.category_name_taken"
    assert taken.value.fields == {
        "name": "There is already a category with that name. Pick another name."
    }


def test_a_deleted_parent_is_not_available():
    gone = make_category("Gone", is_deleted=True)
    with pytest.raises(InvalidPayload) as refused:
        run("service.category.create", {"name": "Colour", "parent_id": str(gone.id)})
    assert refused.value.code == "service.parent_category_unavailable"
    assert "parent_id" in refused.value.fields


def test_a_category_never_hangs_from_itself_or_from_one_of_its_children():
    hair = make_category("Hair")
    colour = make_category("Colour", parent=hair)
    blonde = make_category("Blonde", parent=colour)
    for parent in (hair, blonde):
        with pytest.raises(InvalidPayload) as refused:
            run(
                "service.category.update",
                {"id": str(hair.id), "parent_id": str(parent.id)},
            )
        assert refused.value.code == "service.category_cycle"
        assert refused.value.fields == {
            "parent_id": "A category cannot hang from itself or from one of its subcategories."
        }


def test_an_edit_changes_what_it_sends_and_null_makes_it_a_root():
    hair = make_category("Hair")
    colour = make_category("Colour", parent=hair, sort_order=1)
    out = run(
        "service.category.update",
        {"category": "colour", "parent_id": None, "name": "Colours"},
    )
    assert (out.name, out.parent_id, out.sort_order) == ("Colours", None, 1)
    assert events() == ["service.category.updated"]
    assert colour.id == out.id


def test_deleting_a_category_frees_its_services_and_lifts_its_children(tax):
    hair = make_category("Hair")
    colour = make_category("Colour", parent=hair)
    blonde = make_category("Blonde", parent=colour)
    cut = make_service("Cut", tax=tax, category=colour)
    run("service.category.delete", {"id": str(colour.id)})
    colour.refresh_from_db()
    blonde.refresh_from_db()
    cut.refresh_from_db()
    assert (
        colour.is_deleted,
        colour.deleted_at is not None,
        blonde.parent,
        cut.category,
    ) == (True, True, hair, None)
    assert events() == ["service.category.deleted"]
    with pytest.raises(NotFound) as gone:
        run("service.category.delete", {"id": str(colour.id)})
    assert gone.value.message == "That category does not exist in this business."
    assert run("service.category.create", {"name": "colour"}).name == "colour"


def test_only_the_owner_and_the_admin_delete_categories():
    hair = make_category("Hair")
    with pytest.raises(PermissionDenied):
        run("service.category.delete", {"id": str(hair.id)}, role="hub_manager")


# ── Settings ──────────────────────────────────────────────────────────────────────────────────


def test_the_first_save_writes_the_row_and_only_what_is_sent_changes(tax):
    out = run(
        "service.settings.update",
        {"default_duration": 45, "default_tax_category_key": tax.key},
    )
    assert (
        out.default_duration,
        out.default_buffer_time,
        out.default_tax_category_key,
    ) == (45, 0, tax.key)
    assert ServiceSettings.objects.get().updated_by == "tester"
    out = run("service.settings.update", {"show_prices": False})
    assert (out.default_duration, out.show_prices, out.default_tax_category_key) == (
        45,
        False,
        tax.key,
    )
    out = run("service.settings.update", {"default_tax_category_key": None})
    assert out.default_tax_category_key is None
    assert events() == ["service.settings.updated"] * 3
    run("service.settings.update", {"show_prices": False})
    assert len(events()) == 3


def test_a_settings_tax_category_that_does_not_exist_is_refused_under_its_field():
    with pytest.raises(InvalidPayload) as refused:
        run("service.settings.update", {"default_tax_category_key": "nope"})
    assert "default_tax_category_key" in refused.value.fields


def test_only_the_owner_and_the_admin_change_the_settings():
    with pytest.raises(PermissionDenied):
        run("service.settings.update", {"show_prices": False}, role="hub_manager")


# ── Who performs each service ─────────────────────────────────────────────────────────────────


def test_assign_a_professional_by_name_with_their_own_time_and_price(tax):
    cut = make_service("Cut", tax=tax, price=2000, duration_minutes=30)
    ana = make_member("Ana", "López")
    out = run(
        "service.assignment.assign",
        {
            "service": "Cut",
            "member": "ana lópez",
            "custom_duration": 40,
            "custom_price": 2500,
        },
    )
    assert (
        out.member_id,
        out.service_id,
        out.duration,
        out.price,
        out.is_active,
        out.is_primary,
    ) == (ana.id, cut.id, 40, 2500, True, False)
    assert events() == ["service.assignment.assigned"]
    assert payload("service.assignment.assigned") == {
        "id": str(out.id),
        "service_id": str(cut.id),
        "member_id": str(ana.id),
    }


def test_assigning_again_changes_the_assignment_instead_of_adding_one(tax):
    cut = make_service("Cut", tax=tax)
    ana = make_member("Ana")
    first = run(
        "service.assignment.assign",
        {"service_id": str(cut.id), "member_id": str(ana.id), "custom_duration": 40},
    )
    Assignment.objects.filter(pk=first.id).update(is_active=False)
    again = run(
        "service.assignment.assign",
        {"service_id": str(cut.id), "member_id": str(ana.id), "custom_price": 900},
    )
    assert (again.id, again.custom_duration, again.custom_price, again.is_active) == (
        first.id,
        None,
        900,
        True,
    )
    assert events() == ["service.assignment.assigned", "service.assignment.updated"]


def test_one_main_service_per_professional(tax):
    cut, colour = make_service("Cut", tax=tax), make_service("Colour", tax=tax)
    ana = make_member("Ana")
    first = run(
        "service.assignment.assign",
        {"service": "Cut", "member": "Ana", "is_primary": True},
    )
    second = run(
        "service.assignment.assign",
        {"service": "Colour", "member": "Ana", "is_primary": True},
    )
    assert Assignment.objects.get(pk=first.id).is_primary is False
    assert Assignment.objects.get(pk=second.id).is_primary is True
    run("service.assignment.update", {"id": str(first.id), "is_primary": True})
    assert list(
        Assignment.objects.filter(is_primary=True).values_list("service_id", flat=True)
    ) == [cut.id]
    assert colour.id


def test_a_professional_who_does_not_exist_or_left_cannot_be_assigned(tax):
    make_service("Cut", tax=tax)
    make_member("Gone", status="terminated")
    with pytest.raises(NotFound):
        run("service.assignment.assign", {"service": "Cut", "member": "Gone"})
    make_member("Ana", "López")
    make_member("Ana", "Ruiz")
    with pytest.raises(Conflict) as ambiguous:
        run("service.assignment.assign", {"service": "Cut", "member": "Ana"})
    assert ambiguous.value.code == "staff.ambiguous_member"


def test_update_an_assignment_and_null_brings_back_the_services_own(tax):
    cut = make_service("Cut", tax=tax, price=2000)
    assignment = Assignment.objects.create(
        service=cut, member=make_member(), custom_price=2500, custom_duration=40
    )
    out = run(
        "service.assignment.update",
        {"id": str(assignment.id), "custom_price": None, "is_active": False},
    )
    assert (out.custom_price, out.price, out.custom_duration, out.is_active) == (
        None,
        2000,
        40,
        False,
    )
    assert events() == ["service.assignment.updated"]


def test_remove_an_assignment_and_an_unknown_one_is_not_found(tax):
    assignment = Assignment.objects.create(
        service=make_service("Cut", tax=tax), member=make_member()
    )
    run("service.assignment.remove", {"id": str(assignment.id)})
    assert not Assignment.objects.exists()
    assert events() == ["service.assignment.removed"]
    with pytest.raises(NotFound) as missing:
        run("service.assignment.remove", {"id": str(assignment.id)})
    assert missing.value.message == "That assignment does not exist in this business."


def test_an_employee_reads_assignments_but_does_not_change_them(tax):
    make_service("Cut", tax=tax)
    make_member("Ana")
    with pytest.raises(PermissionDenied):
        run(
            "service.assignment.assign",
            {"service": "Cut", "member": "Ana"},
            role="hub_employee",
        )


def test_releasing_a_professional_is_the_platforms_only():
    with pytest.raises(PermissionDenied):
        run("service.assignment.release_member", MemberReleaseIn(id=uuid.uuid7()))


# ── Packages ──────────────────────────────────────────────────────────────────────────────────


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


# ── Vouchers sold ─────────────────────────────────────────────────────────────────────────────


def test_grant_a_voucher_to_a_customer_freezing_its_terms(tax):
    package = make_package(
        "Bono 5", [make_service("Cut", tax=tax)], max_uses=5, validity_days=90
    )
    lucia = make_customer("Lucía Pérez")
    out = run(
        "service.grant.create",
        {
            "package": "Bono 5",
            "customer": "Lucía Pérez",
            "amount": 9000,
            "note": "paid cash",
        },
        role="hub_employee",
    )
    grant = Grant.objects.get()
    assert (
        out.customer_id,
        out.max_uses,
        out.remaining,
        out.amount,
        out.status,
        out.source,
    ) == (lucia.id, 5, 5, 9000, "active", "manual")
    assert (grant.validity_days, grant.created_by, grant.note) == (
        90,
        "tester",
        "paid cash",
    )
    assert out.expires_at == grant.granted_at + dt.timedelta(days=90)
    assert payload("service.grant.granted") == {
        "id": str(grant.id),
        "package_id": str(package.id),
        "customer_id": str(lucia.id),
    }


def test_a_voucher_cannot_be_granted_from_a_deleted_or_inactive_package():
    lucia = make_customer("Lucía")
    for package in (
        make_package("Gone", is_deleted=True),
        make_package("Off", is_active=False),
    ):
        with pytest.raises(NotFound) as missing:
            run(
                "service.grant.create",
                {"package_id": str(package.id), "customer_id": str(lucia.id)},
            )
        assert missing.value.message == "That package does not exist in this business."


def test_a_voucher_bought_earlier_counts_its_expiry_from_then():
    package = make_package("Bono", max_uses=5, validity_days=30)
    make_customer("Lucía")
    bought = timezone.now() - dt.timedelta(days=40)
    data = {"package_id": str(package.id), "customer": "Lucía", "granted_at": bought.isoformat()}
    out = run("service.grant.create", data)
    assert out.is_expired is True


def test_void_an_untouched_voucher_with_its_reason():
    grant = make_grant(make_package("Bono", max_uses=5), make_customer())
    out = run(
        "service.grant.void",
        {"id": str(grant.id), "reason": "sold to the wrong customer"},
    )
    grant.refresh_from_db()
    assert (
        out.status,
        grant.voided_by,
        grant.void_reason,
        grant.voided_at is not None,
    ) == ("voided", "tester", "sold to the wrong customer", True)
    assert payload("service.grant.voided") == {
        "id": str(grant.id),
        "package_id": str(grant.package_id),
        "customer_id": str(grant.customer_id),
    }
    with pytest.raises(Conflict) as again:
        run("service.grant.void", {"id": str(grant.id), "reason": "twice"})
    assert (again.value.code, again.value.message) == (
        "service.grant_already_voided",
        "That voucher was already voided.",
    )


def test_a_voucher_already_used_is_not_voided():
    grant = make_grant(make_package("Bono", max_uses=5), make_customer())
    make_redemption(grant)
    with pytest.raises(Conflict) as used:
        run("service.grant.void", {"id": str(grant.id), "reason": "oops"})
    assert (used.value.code, used.value.message) == (
        "service.grant_in_use",
        "That voucher was already used: it cannot be voided.",
    )
    assert events() == []


def test_adjust_gives_sessions_and_days_and_revives_a_spent_voucher():
    grant = make_grant(
        make_package("Bono", max_uses=1, validity_days=30), make_customer(), days_ago=40
    )
    make_redemption(grant)
    out = run(
        "service.grant.adjust",
        {
            "id": str(grant.id),
            "uses_delta": 2,
            "days_delta": 30,
            "reason": "we were closed",
        },
    )
    adjustment = GrantAdjustment.objects.get()
    assert (out.remaining, out.is_expired, out.uses_added, out.days_added) == (
        2,
        False,
        2,
        30,
    )
    assert (adjustment.actor, adjustment.reason) == ("tester", "we were closed")
    assert payload("service.grant.adjusted") == {
        "id": str(grant.id),
        "uses_delta": 2,
        "days_delta": 30,
    }


def test_adjust_takes_sessions_but_never_more_than_are_left():
    grant = make_grant(make_package("Bono", max_uses=3), make_customer())
    make_redemption(grant)
    with pytest.raises(Conflict) as below:
        run(
            "service.grant.adjust",
            {"id": str(grant.id), "uses_delta": -3, "reason": "typo"},
        )
    assert (below.value.code, below.value.message) == (
        "service.grant_adjust_below_used",
        "You cannot take away more sessions than the customer has left.",
    )
    out = run(
        "service.grant.adjust",
        {"id": str(grant.id), "uses_delta": -2, "reason": "typo"},
    )
    assert (out.remaining, out.uses_removed) == (0, 2)


def test_adjust_refuses_what_the_voucher_does_not_have():
    unlimited = make_grant(
        make_package("Unlimited", validity_days=30), make_customer("A")
    )
    forever = make_grant(make_package("Forever", max_uses=5), make_customer("B"))
    voided = make_grant(
        make_package("Voided", max_uses=5), make_customer("C"), voided_at=timezone.now()
    )
    cases = [
        (unlimited, {"uses_delta": 1}, "service.grant_unlimited"),
        (forever, {"days_delta": 1}, "service.grant_no_expiry"),
        (voided, {"uses_delta": 1}, "service.grant_already_voided"),
    ]
    for grant, change, code in cases:
        with pytest.raises(Conflict) as refused:
            run("service.grant.adjust", {"id": str(grant.id), "reason": "x", **change})
        assert refused.value.code == code
    assert not GrantAdjustment.objects.exists()


def test_redeem_a_session_of_a_service_the_voucher_covers(tax):
    cut = make_service("Cut", tax=tax)
    grant = make_grant(make_package("Bono", [cut], max_uses=2), make_customer())
    sale = uuid.uuid7()
    out = run(
        "service.grant.redeem",
        {"id": str(grant.id), "service": "Cut", "sale_id": str(sale), "note": "Friday"},
        role="hub_employee",
    )
    session = Redemption.objects.get()
    assert (
        out.remaining,
        out.service_name,
        session.sale_id,
        session.actor,
        session.note,
    ) == (1, "Cut", sale, "tester", "Friday")
    assert payload("service.grant.redeemed") == {
        "id": str(grant.id),
        "redemption_id": str(session.id),
        "service_id": str(cut.id),
    }


def test_a_session_is_refused_with_the_real_reason(tax):
    cut, shampoo = make_service("Cut", tax=tax), make_service("Shampoo", tax=tax)
    package = make_package("Bono", [cut], max_uses=1, validity_days=30)
    spent = make_grant(package, make_customer("A"))
    make_redemption(spent)
    cases = [
        (
            make_grant(package, make_customer("B"), voided_at=timezone.now()),
            {},
            "service.grant_voided",
            "This voucher was voided: it can no longer be used.",
        ),
        (
            make_grant(package, make_customer("C"), days_ago=31),
            {},
            "service.grant_expired",
            "This voucher has expired.",
        ),
        (spent, {}, "service.grant_no_uses_left", "This voucher has no sessions left."),
        (
            make_grant(package, make_customer("D")),
            {"service_id": str(shampoo.id)},
            "service.grant_does_not_cover_service",
            "This voucher does not cover that service. A voucher of haircuts pays for haircuts, not for the shampoo.",
        ),
    ]
    for grant, service, code, message in cases:
        with pytest.raises(Conflict) as refused:
            run("service.grant.redeem", {"id": str(grant.id), **service})
        assert (refused.value.code, refused.value.message) == (code, message)
    assert Redemption.objects.count() == 1


def test_a_voucher_of_a_deleted_package_is_still_spent(tax):
    cut = make_service("Cut", tax=tax)
    grant = make_grant(
        make_package("Bono", [cut], max_uses=2, is_deleted=True), make_customer()
    )
    assert (
        run(
            "service.grant.redeem", {"id": str(grant.id), "service_id": str(cut.id)}
        ).remaining
        == 1
    )


def test_an_unknown_voucher_sold_is_not_found():
    with pytest.raises(NotFound) as missing:
        run("service.grant.redeem", RedeemIn(id=uuid.uuid7()))
    assert (missing.value.code, missing.value.message) == (
        "service.grant_not_found",
        "That voucher sale does not exist in this business.",
    )


def test_forgetting_a_customer_is_the_platforms_only():
    with pytest.raises(PermissionDenied):
        run("service.grant.forget_customer", {"id": str(uuid.uuid7())})


def test_reassigning_is_the_platforms_only():
    with pytest.raises(PermissionDenied):
        run(
            "service.grant.reassign",
            ReassignIn(id=uuid.uuid7(), absorbed_id=uuid.uuid7()),
        )


def test_the_refusals_leave_no_trace(tax):
    for name, data in (
        ("service.category.update", CategoryPatchIn(id=uuid.uuid7(), name="X")),
        ("service.package.update", PackagePatchIn(id=uuid.uuid7(), name="X")),
        (
            "service.assignment.update",
            AssignmentPatchIn(id=uuid.uuid7(), is_active=False),
        ),
        ("service.grant.void", VoidIn(id=uuid.uuid7(), reason="x")),
        ("service.grant.adjust", AdjustIn(id=uuid.uuid7(), uses_delta=1, reason="x")),
    ):
        with pytest.raises(NotFound):
            run(name, data)
    assert events() == []


def test_no_event_without_a_change(tax):
    cut = make_service("Cut", tax=tax)
    run("service.service.update", {"id": str(cut.id)})
    assert events() == []


def test_who_acted_is_kept_by_the_name_a_person_reads(make_user):
    # «Voided by {who}», «Given by {who}»: the account's full name, else its email, else its username.
    boss = make_user("saas:01a1355a")
    boss.first_name, boss.last_name = "Ana", "López"
    boss.save()
    grant = make_grant(make_package("Bono", max_uses=5), make_customer())
    run("service.grant.adjust", {"id": str(grant.id), "uses_delta": 1, "reason": "courtesy"}, actor=boss)
    run("service.grant.void", {"id": str(make_grant(make_package("Other", max_uses=1), make_customer("B")).id), "reason": "x"}, actor=boss)
    assert GrantAdjustment.objects.get().actor == "Ana López"
    assert Grant.objects.exclude(voided_by="").get().voided_by == "Ana López"
    mail = make_user("saas:02b", host=None)
    mail.email = "eva@example.com"
    mail.save()
    run("service.grant.redeem", {"id": str(grant.id)}, actor=mail)
    assert Redemption.objects.get().actor == "eva@example.com"


def test_assigning_again_keeps_the_main_service_unless_it_is_said(tax):
    cut = make_service("Cut", tax=tax)
    ana = make_member("Ana")
    run("service.assignment.assign", {"service": "Cut", "member": "Ana", "is_primary": True})
    again = run("service.assignment.assign", {"service": "Cut", "member": "Ana", "custom_price": 900})
    assert (again.is_primary, again.custom_price) == (True, 900)
    off = run("service.assignment.assign", {"service": "Cut", "member": "Ana", "is_primary": False})
    assert off.is_primary is False
    assert cut.id and ana.id


def test_categories_that_already_loop_are_refused_and_deleted_without_crashing():
    # A loop left by a raw write (the database only forbids a category being its own parent).
    a, b, c = make_category("A"), make_category("B"), make_category("C")
    Category.objects.filter(pk=a.pk).update(parent=b)
    Category.objects.filter(pk=b.pk).update(parent=a)
    with pytest.raises(Conflict) as looped:
        run("service.category.update", {"id": str(c.id), "parent_id": str(a.id)})
    assert looped.value.code == "service.category_cycle"
    run("service.category.delete", {"id": str(a.id)})
    b.refresh_from_db()
    assert b.parent is None
