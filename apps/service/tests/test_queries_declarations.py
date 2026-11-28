"""What each read of the service app declares (its input, its output, its permission and that the API serves it),
and that a read by id refuses who lacks its permission."""

import uuid

import pytest
from live.errors import PermissionDenied
from live.operations import get

from apps.service.schemas.assignments import (
    AssignmentDetailOut,
    AssignmentListIn,
    AssignmentPage,
    EligibleIn,
    EligiblePage,
)
from apps.service.schemas.catalog import (
    CatalogStatusOut,
    ServiceForSaleIn,
    ServiceListIn,
    ServiceOut,
    ServicePage,
    ServiceSalePage,
)
from apps.service.schemas.categories import CategoryListIn, CategoryOut, CategoryPage
from apps.service.schemas.fields import ByIdIn, CategoryRefIn, NoIn, PackageRefIn, PageIn, ServiceRefIn
from apps.service.schemas.grant_checks import AdjustCheckOut, RedeemCheckIn, RedeemCheckOut, VoidCheckOut
from apps.service.schemas.grants import GrantDetailOut, GrantListIn, GrantPage, OrphanPage
from apps.service.schemas.movements import MovementListIn, MovementPage
from apps.service.schemas.packages import PackageListIn, PackageOut, PackagePage
from apps.service.schemas.sessions import SessionDetailOut, SessionRefIn
from apps.service.schemas.settings import SettingsOut
from apps.service.schemas.tender import TenderOptionPage, TenderOptionsIn

from .conftest import HUB_DB, ctx_for

pytestmark = HUB_DB


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
        ("service.assignment.get", ByIdIn, AssignmentDetailOut, "service.view_service"),
        ("service.grant.list", GrantListIn, GrantPage, "service.view_package_balance"),
        ("service.grant.get", ByIdIn, GrantDetailOut, "service.view_package_balance"),
        ("service.session.get", SessionRefIn, SessionDetailOut, "service.view_package_balance"),
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


@pytest.mark.parametrize("read", ["service.assignment.get", "service.grant.get", "service.session.get"])
def test_each_read_by_id_asks_for_its_permission(read):
    op = get(read)
    with pytest.raises(PermissionDenied):
        op(ctx_for(permissions=frozenset()), op.input(id=uuid.uuid7()))
