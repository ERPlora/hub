"""Read operations of the service app: the catalog, its categories, the settings, who performs each
service, the vouchers of the catalog, the ones sold with their balance, their movements and the checks.
"""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import get

from apps.service.models import Assignment, GrantAdjustment, ServiceSettings
from apps.service.schemas import (
    AdjustCheckOut,
    AssignmentListIn,
    AssignmentPage,
    ByIdIn,
    CatalogStatusOut,
    CategoryListIn,
    CategoryOut,
    CategoryPage,
    CategoryRefIn,
    EligibleIn,
    EligiblePage,
    GrantListIn,
    GrantPage,
    MovementListIn,
    MovementPage,
    NoIn,
    OrphanPage,
    PackageListIn,
    PackageOut,
    PackagePage,
    PackageRefIn,
    PageIn,
    RedeemCheckIn,
    RedeemCheckOut,
    ServiceForSaleIn,
    ServiceListIn,
    ServiceOut,
    ServicePage,
    ServiceRefIn,
    ServiceSalePage,
    SettingsOut,
    TenderOptionPage,
    TenderOptionsIn,
    VoidCheckOut,
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


def run(name, data=None, role="hub_admin", **ctx):
    op = get(name)
    return op(ctx_for(role, **ctx), data if data is not None else op.input())


def names(page) -> list[str]:
    return [row.name for row in page.rows]


@pytest.fixture
def tax():
    return make_tax()


@pytest.mark.parametrize(
    ("name", "input", "output", "permission"),
    [
        ("service.service.list", ServiceListIn, ServicePage, "service.view_service"),
        ("service.service.get", ServiceRefIn, ServiceOut, "service.view_service"),
        (
            "service.service.list_for_sale",
            ServiceForSaleIn,
            ServiceSalePage,
            "service.view_service",
        ),
        ("service.catalog.status", NoIn, CatalogStatusOut, "service.view_service"),
        (
            "service.category.list",
            CategoryListIn,
            CategoryPage,
            "service.view_category",
        ),
        ("service.category.get", CategoryRefIn, CategoryOut, "service.view_category"),
        ("service.settings.get", NoIn, SettingsOut, "service.view_service"),
        (
            "service.assignment.list",
            AssignmentListIn,
            AssignmentPage,
            "service.view_service",
        ),
        (
            "service.assignment.eligible",
            EligibleIn,
            EligiblePage,
            "service.view_service",
        ),
        ("service.package.list", PackageListIn, PackagePage, "service.view_package"),
        ("service.package.get", PackageRefIn, PackageOut, "service.view_package"),
        ("service.grant.list", GrantListIn, GrantPage, "service.view_package_balance"),
        ("service.grant.list_orphans", PageIn, OrphanPage, "service.view_orphan_grant"),
        ("service.grant.void_check", ByIdIn, VoidCheckOut, "service.void_grant"),
        ("service.grant.adjust_check", ByIdIn, AdjustCheckOut, "service.adjust_grant"),
        (
            "service.grant.redeem_check",
            RedeemCheckIn,
            RedeemCheckOut,
            "service.redeem_package",
        ),
        (
            "service.movement.list",
            MovementListIn,
            MovementPage,
            "service.view_package_balance",
        ),
        (
            "service.grant.tender_options",
            TenderOptionsIn,
            TenderOptionPage,
            "service.redeem_package",
        ),
    ],
)
def test_declarations(name, input, output, permission):
    op = get(name)
    assert (op.kind, op.input, op.output, op.permission, op.expose_api) == (
        "query",
        input,
        output,
        permission,
        True,
    )


# ── Services ──────────────────────────────────────────────────────────────────────────────────


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


# ── Categories ────────────────────────────────────────────────────────────────────────────────


def test_categories_list_by_order_and_name_with_their_offered_services(tax):
    hair = make_category("Hair", sort_order=2)
    nails = make_category("Nails", sort_order=1)
    colour = make_category("Colour", parent=hair, sort_order=2)
    make_category("Gone", is_deleted=True)
    make_service("Cut", tax=tax, category=hair)
    make_service("Perm", tax=tax, category=hair, is_active=False)
    page = run("service.category.list", CategoryListIn())
    assert names(page) == ["Nails", "Colour", "Hair"]
    assert [(row.name, row.parent_name, row.service_count) for row in page.rows] == [
        ("Nails", None, 0),
        ("Colour", "Hair", 0),
        ("Hair", None, 1),
    ]
    assert names(run("service.category.list", CategoryListIn(search="ai"))) == ["Nails", "Hair"]
    assert names(run("service.category.list", CategoryListIn(parent_id=hair.id))) == [
        "Colour"
    ]
    assert names(
        run("service.category.list", CategoryListIn(sort="-service_count"))
    ) == ["Hair", "Nails", "Colour"]
    assert run("service.category.get", CategoryRefIn(category="colour")).id == colour.id
    assert run("service.category.get", CategoryRefIn(id=nails.id)).name == "Nails"


def test_a_deleted_category_is_not_found():
    gone = make_category("Gone", is_deleted=True)
    with pytest.raises(NotFound) as missing:
        run("service.category.get", CategoryRefIn(id=gone.id))
    assert missing.value.code == "service.category_not_found"


# ── Settings ──────────────────────────────────────────────────────────────────────────────────


def test_the_settings_are_the_factory_ones_until_saved(tax):
    settings = run("service.settings.get")
    assert (
        settings.default_duration,
        settings.default_buffer_time,
        settings.default_tax_category_key,
    ) == (60, 0, None)
    assert (
        settings.show_prices,
        settings.allow_online_booking,
        settings.updated_at,
    ) == (True, True, None)
    ServiceSettings.objects.create(default_duration=45, default_tax_category=tax)
    settings = run("service.settings.get", role="hub_employee")
    assert (
        settings.default_duration,
        settings.default_tax_category_key,
        settings.default_tax_category_name,
    ) == (
        45,
        tax.key,
        tax.name,
    )


# ── Who performs each service ─────────────────────────────────────────────────────────────────


def test_the_professionals_of_a_service_and_the_services_of_a_professional(tax):
    cut, colour = (
        make_service("Cut", tax=tax, price=2000, duration_minutes=30),
        make_service("Colour", tax=tax),
    )
    ana, bea = make_member("Ana", "López"), make_member("Bea", "Ruiz")
    Assignment.objects.create(service=cut, member=ana, custom_price=2500)
    Assignment.objects.create(
        service=cut, member=bea, is_primary=True, custom_duration=40
    )
    Assignment.objects.create(service=colour, member=ana)
    of_cut = run("service.assignment.list", AssignmentListIn(service_id=cut.id))
    assert [
        (row.member_name, row.duration, row.price, row.is_primary)
        for row in of_cut.rows
    ] == [
        ("Bea Ruiz", 40, 2000, True),
        ("Ana López", 30, 2500, False),
    ]
    of_ana = run("service.assignment.list", AssignmentListIn(member="ana"))
    assert [row.service_name for row in of_ana.rows] == ["Colour", "Cut"]
    assert run("service.assignment.list", AssignmentListIn(service="cut")).total == 2


def test_who_may_perform_a_service_is_the_active_bookable_people_with_an_active_assignment(
    tax,
):
    cut = make_service("Cut", tax=tax, price=2000, duration_minutes=30)
    ana, bea = make_member("Ana", "López", color="#AA3300"), make_member("Bea", "Ruiz")
    cris, dani = (
        make_member("Cris", "Gil", is_bookable=False),
        make_member("Dani", "Sanz", status="inactive"),
    )
    eva = make_member("Eva", "Mar")
    Assignment.objects.create(service=cut, member=ana, custom_price=2500)
    Assignment.objects.create(service=cut, member=bea, is_primary=True)
    Assignment.objects.create(service=cut, member=cris)
    Assignment.objects.create(service=cut, member=dani)
    Assignment.objects.create(service=cut, member=eva, is_active=False)
    page = run("service.assignment.eligible", EligibleIn(service="Cut"))
    assert [
        (row.full_name, row.price, row.duration, row.is_primary) for row in page.rows
    ] == [
        ("Bea Ruiz", 2000, 30, True),
        ("Ana López", 2500, 30, False),
    ]
    assert page.rows[1].color == "#AA3300"


def test_nobody_assigned_is_an_empty_list():
    assert (
        run(
            "service.assignment.eligible", EligibleIn(service_id=make_service("Cut").id)
        ).rows
        == []
    )


# ── Packages ──────────────────────────────────────────────────────────────────────────────────


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


# ── Vouchers sold ─────────────────────────────────────────────────────────────────────────────


def test_a_voucher_sold_shows_its_balance_and_expiry(tax):
    cut = make_service("Cut", tax=tax)
    package = make_package("Bono 5", [cut], max_uses=5, validity_days=90)
    lucia = make_customer("Lucía Pérez")
    grant = make_grant(package, lucia, days_ago=10, amount=9000)
    make_redemption(grant, cut)
    make_redemption(grant, cut)
    GrantAdjustment.objects.create(
        grant=grant, uses_delta=2, days_delta=30, reason="courtesy"
    )
    GrantAdjustment.objects.create(grant=grant, uses_delta=-1, reason="correction")
    [row] = run("service.grant.list", GrantListIn(package_id=package.id)).rows
    assert (row.customer_name, row.amount, row.used, row.max_uses, row.remaining) == (
        "Lucía Pérez",
        9000,
        2,
        6,
        4,
    )
    assert (
        row.uses_added,
        row.uses_removed,
        row.days_added,
        row.status,
        row.is_expired,
    ) == (2, 1, 30, "active", False)
    assert row.expires_at == grant.granted_at + dt.timedelta(days=120)
    assert (row.can_void, row.can_adjust) == (False, True)


def test_an_unlimited_voucher_has_no_remaining_and_one_without_validity_never_expires(
    tax,
):
    package = make_package("Unlimited", [make_service("Cut", tax=tax)])
    grant = make_grant(package, make_customer(), days_ago=1000)
    [row] = run("service.grant.list", GrantListIn(package_id=package.id)).rows
    assert (row.max_uses, row.remaining, row.expires_at, row.is_expired) == (
        None,
        None,
        None,
        False,
    )
    assert (row.can_void, row.can_adjust, row.id) == (True, False, grant.id)


def test_an_expired_voucher_says_so():
    package = make_package("Bono", validity_days=30, max_uses=3)
    make_grant(package, make_customer(), days_ago=31)
    [row] = run("service.grant.list", GrantListIn(package_id=package.id)).rows
    assert row.is_expired is True


def test_the_vouchers_of_a_customer_by_name_most_recent_first_voided_ones_included():
    package, other = make_package("Bono", max_uses=5), make_package("Other", max_uses=1)
    lucia, marta = make_customer("Lucía Pérez"), make_customer("Marta Gil")
    old = make_grant(package, lucia, days_ago=5)
    new = make_grant(
        other,
        lucia,
        days_ago=1,
        voided_at=timezone.now(),
        voided_by="boss",
        void_reason="wrong",
    )
    make_grant(package, marta)
    page = run("service.grant.list", GrantListIn(customer="Lucía Pérez"))
    assert [row.id for row in page.rows] == [new.id, old.id]
    assert (
        page.rows[0].status,
        page.rows[0].voided_by,
        page.rows[0].void_reason,
        page.rows[0].can_void,
    ) == (
        "voided",
        "boss",
        "wrong",
        False,
    )
    assert [
        row.id
        for row in run(
            "service.grant.list", GrantListIn(customer_id=lucia.id, status="active")
        ).rows
    ] == [old.id]


def test_a_customer_name_is_shown_only_to_who_may_read_customers():
    package = make_package("Bono", max_uses=5)
    make_grant(package, make_customer("Lucía"))
    permissions = {"service.view_package_balance"}
    [row] = run(
        "service.grant.list",
        GrantListIn(package_id=package.id),
        permissions=permissions,
    ).rows
    assert row.customer_name is None


def test_the_vouchers_of_a_deleted_card_lose_the_name_and_go_to_the_orphans():
    package = make_package("Bono", max_uses=5)
    gone, erased, merged, alive = (
        make_customer(name) for name in ("Gone", "Erased", "Merged", "Alive")
    )
    survivor = make_customer("Survivor")
    now = timezone.now()
    gone.deleted_at = now - dt.timedelta(days=2)
    gone.save()
    erased.deleted_at, erased.erased_at = now - dt.timedelta(days=1), now
    erased.save()
    merged.deleted_at, merged.merged_into = now, survivor
    merged.save()
    orphan_old = make_grant(package, gone)
    orphan_new = make_grant(package, erased)
    make_grant(package, erased, voided_at=now)
    make_grant(package, merged)
    make_grant(package, alive)
    page = run("service.grant.list_orphans", PageIn())
    assert [row.id for row in page.rows] == [orphan_new.id, orphan_old.id]
    assert (
        page.rows[1].customer_deleted_at,
        page.rows[1].remaining,
        page.rows[1].package_name,
    ) == (gone.deleted_at, 5, "Bono")
    rows = run("service.grant.list", GrantListIn(package_id=package.id)).rows
    assert {row.customer_id: row.customer_name for row in rows}[gone.id] is None
    with pytest.raises(PermissionDenied):
        run("service.grant.list_orphans", PageIn(), role="hub_employee")


def test_the_void_check_says_why_a_voucher_cannot_be_voided():
    package = make_package("Bono", max_uses=5)
    fresh, used = (
        make_grant(package, make_customer("A")),
        make_grant(package, make_customer("B")),
    )
    voided = make_grant(package, make_customer("C"), voided_at=timezone.now())
    make_redemption(used)
    check = lambda grant: run("service.grant.void_check", ByIdIn(id=grant.id))  # noqa: E731
    assert (check(fresh).voidable, check(fresh).reason) == (True, "")
    assert (check(used).voidable, check(used).reason, check(used).used) == (
        False,
        "in_use",
        1,
    )
    assert (check(voided).voidable, check(voided).reason) == (False, "already_voided")
    with pytest.raises(NotFound) as missing:
        run("service.grant.void_check", ByIdIn(id=uuid.uuid7()))
    assert missing.value.code == "service.grant_not_found"


def test_the_adjust_check_says_what_can_be_adjusted():
    limited = make_grant(make_package("Limited", max_uses=5), make_customer("A"))
    dated = make_grant(make_package("Dated", validity_days=30), make_customer("B"))
    voided = make_grant(
        make_package("Voided", max_uses=1), make_customer("C"), voided_at=timezone.now()
    )
    check = lambda grant: run("service.grant.adjust_check", ByIdIn(id=grant.id))  # noqa: E731
    assert (
        check(limited).can_add_uses,
        check(limited).can_extend,
        check(limited).uses_left,
    ) == (True, False, 5)
    assert (
        check(dated).can_add_uses,
        check(dated).can_extend,
        check(dated).uses_left,
    ) == (False, True, None)
    assert check(voided).reason == "already_voided"


def test_the_redeem_check_says_why_a_session_cannot_be_spent(tax):
    cut, shampoo = make_service("Cut", tax=tax), make_service("Shampoo", tax=tax)
    package = make_package("Bono", [cut], max_uses=1, validity_days=30)
    fresh = make_grant(package, make_customer("A"))
    spent = make_grant(package, make_customer("B"))
    make_redemption(spent, cut)
    expired = make_grant(package, make_customer("C"), days_ago=31)
    voided = make_grant(package, make_customer("D"), voided_at=timezone.now())
    check = lambda grant, **service: run(
        "service.grant.redeem_check", RedeemCheckIn(id=grant.id, **service)
    )  # noqa: E731
    assert (check(fresh).redeemable, check(fresh).reason, check(fresh).remaining) == (
        True,
        "",
        1,
    )
    assert check(fresh, service="Shampoo").reason == "does_not_cover_service"
    assert check(fresh, service_id=cut.id).redeemable is True
    assert check(spent).reason == "no_uses_left"
    assert check(expired).reason == "expired"
    assert check(voided).reason == "voided"
    assert shampoo.id


def test_the_movements_of_a_package_are_its_sessions_and_adjustments_most_recent_first(
    tax,
):
    cut = make_service("Cut", tax=tax)
    package = make_package("Bono", [cut], max_uses=5)
    lucia = make_customer("Lucía")
    grant = make_grant(package, lucia, days_ago=3)
    now = timezone.now()
    first = make_redemption(
        grant, cut, redeemed_at=now - dt.timedelta(days=2), actor="ana"
    )
    courtesy = GrantAdjustment.objects.create(
        grant=grant,
        uses_delta=1,
        days_delta=10,
        reason="closed",
        actor="boss",
        created_at=now - dt.timedelta(days=1),
    )
    correction = GrantAdjustment.objects.create(
        grant=grant, uses_delta=-1, reason="typo", actor="boss", created_at=now
    )
    make_redemption(make_grant(make_package("Other", max_uses=1), lucia))
    page = run("service.movement.list", MovementListIn(package="Bono"))
    assert [(row.kind, row.id) for row in page.rows] == [
        ("corrected", correction.id),
        ("adjusted", courtesy.id),
        ("consumed", first.id),
    ]
    assert (
        page.total,
        page.rows[2].service_name,
        page.rows[2].customer_name,
        page.rows[2].actor,
    ) == (3, "Cut", "Lucía", "ana")
    assert (page.rows[1].uses_delta, page.rows[1].days_delta, page.rows[1].reason) == (
        1,
        10,
        "closed",
    )
    second_page = run(
        "service.movement.list",
        MovementListIn(package_id=package.id, limit=2, offset=2),
    )
    assert [row.id for row in second_page.rows] == [first.id]


def test_the_vouchers_of_a_card_merged_into_it_show_before_the_relay_moves_them():
    # Customers flattens the chain of merged cards (one level): until the reaction to
    # customer.customer.merged moves the vouchers, they are read through the card that stays.
    package = make_package("Bono", max_uses=5)
    lucia, duplicate = make_customer("Lucía Pérez"), make_customer("Lucia P.")
    duplicate.deleted_at, duplicate.merged_into = timezone.now(), lucia
    duplicate.save()
    absorbed = make_grant(package, duplicate, days_ago=2)
    own = make_grant(package, lucia, days_ago=1)
    make_grant(package, make_customer("Marta"))
    page = run("service.grant.list", GrantListIn(customer_id=lucia.id))
    assert [row.id for row in page.rows] == [own.id, absorbed.id]
    assert run("service.grant.list", GrantListIn(customer="Lucía Pérez")).total == 2


# ── Sessions of the till (SERVICE-F22–F27) ───────────────────────────────────────────────────


def _sessions(grant, cut, **states):
    """One session of ``grant`` per state given (``held=…`` takes the hold's deadline)."""
    now = timezone.now()
    made = {}
    for name, value in states.items():
        if name == "held":
            made[name] = make_redemption(
                grant, cut, status="held", hold_until=value, order_line_id=uuid.uuid7()
            )
        else:
            made[name] = make_redemption(
                grant, cut, status=value, ended_at=now, order_line_id=uuid.uuid7()
            )
    return made


def test_a_live_hold_counts_as_used_and_a_released_expired_or_returned_session_does_not(
    tax,
):
    cut = make_service("Cut", tax=tax)
    package = make_package("Bono 5", [cut], max_uses=5)
    grant = make_grant(package, make_customer())
    now = timezone.now()
    make_redemption(grant, cut)  # spent outside the till
    make_redemption(
        grant, cut, status="held", hold_until=now + dt.timedelta(hours=3), order_line_id=uuid.uuid7()
    )
    # A hold past its deadline no longer counts, even before the hourly task marks it.
    make_redemption(
        grant, cut, status="held", hold_until=now - dt.timedelta(minutes=1), order_line_id=uuid.uuid7()
    )
    for state in ("released", "expired", "returned"):
        make_redemption(grant, cut, status=state, ended_at=now, order_line_id=uuid.uuid7())
    [row] = run("service.grant.list", GrantListIn(package_id=package.id)).rows
    assert (row.used, row.remaining, row.can_void) == (2, 3, False)


def test_a_voucher_whose_only_hold_expired_can_be_voided_again(tax):
    cut = make_service("Cut", tax=tax)
    grant = make_grant(make_package("Bono", [cut], max_uses=1), make_customer())
    make_redemption(
        grant,
        cut,
        status="held",
        hold_until=timezone.now() - dt.timedelta(seconds=1),
        order_line_id=uuid.uuid7(),
    )
    check = run("service.grant.void_check", ByIdIn(id=grant.id))
    assert (check.voidable, check.used) == (True, 0)


def _tender(customer, service, role="hub_admin", **more):
    return run(
        "service.grant.tender_options",
        TenderOptionsIn(customer_id=customer.id, service_id=service.id, **more),
        role=role,
    )


def test_the_tender_options_are_the_customers_vouchers_that_can_pay_the_service(tax):
    cut = make_service("Cut", tax=tax)
    colour = make_service("Colour", tax=make_tax("test.colour", "Colour"))
    lucia, marta = make_customer("Lucía"), make_customer("Marta")
    good = make_grant(make_package("Cuts", [cut], max_uses=5), lucia, amount=9000)
    make_grant(make_package("Colours", [colour], max_uses=5), lucia)  # does not cover it
    make_grant(make_package("Marta's", [cut], max_uses=5), marta)  # someone else's
    voided = make_grant(make_package("Voided", [cut], max_uses=5), lucia)
    voided.voided_at = timezone.now()
    voided.save()
    make_grant(make_package("Old", [cut], max_uses=5, validity_days=30), lucia, days_ago=31)
    spent = make_grant(make_package("Spent", [cut], max_uses=1), lucia)
    make_redemption(spent, cut)
    page = _tender(lucia, cut, role="hub_employee")
    assert [row.grant_id for row in page.rows] == [good.id]
    [row] = page.rows
    assert (row.package_name, row.max_uses, row.used, row.remaining_before, row.remaining_after) == (
        "Cuts",
        5,
        0,
        5,
        4,
    )
    assert (row.is_unlimited, row.is_default, row.default_reason, row.candidate_count) == (
        False,
        True,
        "only_option",
        1,
    )
    assert page.total == 1


def test_a_deleted_package_still_pays_with_what_was_sold(tax):
    cut = make_service("Cut", tax=tax)
    package = make_package("Retired", [cut], max_uses=3)
    lucia = make_customer("Lucía")
    grant = make_grant(package, lucia)
    package.is_deleted = True
    package.save()
    assert [row.grant_id for row in _tender(lucia, cut).rows] == [grant.id]


def test_the_voucher_spent_first_and_why(tax):
    cut = make_service("Cut", tax=tax)
    lucia = make_customer("Lucía")
    unlimited = make_grant(make_package("Unlimited", [cut]), lucia, days_ago=50)
    late = make_grant(make_package("Late", [cut], max_uses=5, validity_days=90), lucia, days_ago=1)
    soon = make_grant(make_package("Soon", [cut], max_uses=5, validity_days=90), lucia, days_ago=40)
    rows = _tender(lucia, cut).rows
    assert [row.grant_id for row in rows] == [soon.id, late.id, unlimited.id]
    assert [(row.is_default, row.default_reason) for row in rows] == [
        (True, "expires_first"),
        (False, ""),
        (False, ""),
    ]
    assert {row.candidate_count for row in rows} == {3}
    assert rows[2].remaining_before is None and rows[2].remaining_after is None
    assert rows[2].is_unlimited is True


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ("finite_vs_unlimited", "finite_before_unlimited"),
        ("started_vs_new", "already_started"),
        ("fewer_left", "fewest_sessions_left"),
        ("older", "oldest_voucher"),
        ("twins", "stable_order"),
    ],
)
def test_each_tie_break_says_its_reason(tax, setup, reason):
    cut = make_service("Cut", tax=tax)
    lucia = make_customer("Lucía")
    now = timezone.now()

    def grant(name, *, max_uses=5, at=now):
        made = make_grant(make_package(name, [cut], max_uses=max_uses), lucia)
        made.granted_at = at
        made.save()
        return made

    if setup == "finite_vs_unlimited":
        first, _ = grant("Finite"), grant("Unlimited", max_uses=None)
    elif setup == "started_vs_new":
        first, other = grant("Started"), grant("New")
        make_redemption(first, cut)
        other.max_uses = 4  # the same sessions left, so only «started» tells them apart
        other.save()
    elif setup == "fewer_left":
        first, _ = grant("Fewer", max_uses=2), grant("More", max_uses=5)
    elif setup == "older":
        first, _ = grant("Older", at=now - dt.timedelta(days=3)), grant("Newer")
    else:
        a, b = grant("Twin A"), grant("Twin B")
        first = min(a, b, key=lambda row: row.id)
    rows = _tender(lucia, cut).rows
    assert rows[0].grant_id == first.id
    assert rows[0].default_reason == reason


def test_a_live_hold_is_counted_in_the_options_and_a_full_voucher_drops_out(tax):
    cut = make_service("Cut", tax=tax)
    lucia = make_customer("Lucía")
    grant = make_grant(make_package("Two", [cut], max_uses=2), lucia)
    make_redemption(
        grant, cut, status="held", hold_until=timezone.now() + dt.timedelta(hours=1), order_line_id=uuid.uuid7()
    )
    [row] = _tender(lucia, cut).rows
    assert (row.used, row.remaining_before, row.remaining_after) == (1, 1, 0)
    make_redemption(grant, cut)
    assert _tender(lucia, cut).rows == []


def test_the_options_of_a_card_include_the_vouchers_of_a_card_merged_into_it(tax):
    cut = make_service("Cut", tax=tax)
    lucia, duplicate = make_customer("Lucía Pérez"), make_customer("Lucia P.")
    duplicate.deleted_at, duplicate.merged_into = timezone.now(), lucia
    duplicate.save()
    absorbed = make_grant(make_package("Bono", [cut], max_uses=3), duplicate)
    assert [row.grant_id for row in _tender(lucia, cut).rows] == [absorbed.id]


def test_the_options_name_the_customer_and_the_service_as_a_person_says_them(tax):
    cut = make_service("Haircut", tax=tax)
    lucia = make_customer("Lucía Pérez")
    grant = make_grant(make_package("Bono", [cut], max_uses=3), lucia)
    page = run(
        "service.grant.tender_options",
        TenderOptionsIn(customer="Lucía Pérez", service="Haircut"),
    )
    assert [row.grant_id for row in page.rows] == [grant.id]


def test_the_options_page_and_need_the_permission_to_spend_sessions(tax):
    cut = make_service("Cut", tax=tax)
    lucia = make_customer("Lucía")
    for index in range(3):
        make_grant(make_package(f"Bono {index}", [cut], max_uses=3), lucia)
    page = _tender(lucia, cut, limit=2, offset=0)
    assert (len(page.rows), page.total) == (2, 3)
    assert {row.candidate_count for row in page.rows} == {3}
    with pytest.raises(PermissionDenied):
        run(
            "service.grant.tender_options",
            TenderOptionsIn(customer_id=lucia.id, service_id=cut.id),
            permissions={"service.view_package"},
        )


def test_the_movements_show_every_state_of_a_session(tax):
    cut = make_service("Cut", tax=tax)
    package = make_package("Bono", [cut], max_uses=9)
    grant = make_grant(package, make_customer("Lucía"), days_ago=2)
    now = timezone.now()
    held = make_redemption(
        grant,
        cut,
        status="held",
        hold_until=now + dt.timedelta(hours=5),
        order_line_id=uuid.uuid7(),
        redeemed_at=now - dt.timedelta(hours=6),
    )
    lapsed = make_redemption(
        grant,
        cut,
        status="held",
        hold_until=now - dt.timedelta(hours=1),
        order_line_id=uuid.uuid7(),
        redeemed_at=now - dt.timedelta(hours=25),
    )
    released = make_redemption(
        grant,
        cut,
        status="released",
        order_line_id=uuid.uuid7(),
        redeemed_at=now - dt.timedelta(hours=10),
        ended_at=now - dt.timedelta(hours=9),
        ended_by="ana",
    )
    returned = make_redemption(
        grant,
        cut,
        status="returned",
        sale_id=uuid.uuid7(),
        redeemed_at=now - dt.timedelta(hours=30),
        ended_at=now - dt.timedelta(hours=2),
        ended_by="boss",
        return_reason="did not come",
    )
    page = run("service.movement.list", MovementListIn(package_id=package.id))
    rows = {row.id: row for row in page.rows}
    assert (rows[held.id].kind, rows[held.id].uses_delta) == ("held", -1)
    # A hold past its deadline reads as expired, at its deadline, before the task marks it.
    assert (rows[lapsed.id].kind, rows[lapsed.id].uses_delta, rows[lapsed.id].at) == (
        "expired",
        0,
        lapsed.hold_until,
    )
    assert (rows[released.id].kind, rows[released.id].at, rows[released.id].actor) == (
        "released",
        released.ended_at,
        "ana",
    )
    assert (
        rows[returned.id].kind,
        rows[returned.id].uses_delta,
        rows[returned.id].reason,
        rows[returned.id].actor,
    ) == ("returned", 0, "did not come", "boss")
    # Each row is dated by its last step (released, expired, given back, held), the latest first.
    assert [row.id for row in page.rows] == [lapsed.id, returned.id, held.id, released.id]
