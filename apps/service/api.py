"""Ninja routes of the service app: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``): a record travels in the input (query string on GET, body on
POST), by its id or by its name. The platform's reactions (``release_member``, ``reassign``) have no
route, nor do the sessions of the till (``service.session.*``), which Sales runs inside its own writes.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.service import queries, services
from apps.service.schemas import (
    AdjustIn,
    AssignIn,
    AssignmentListIn,
    AssignmentPatchIn,
    ByIdIn,
    CategoryIn,
    CategoryListIn,
    CategoryPatchIn,
    CategoryRefIn,
    EligibleIn,
    GrantIn,
    GrantListIn,
    MovementListIn,
    PackageIn,
    PackageListIn,
    PackagePatchIn,
    PackageRefIn,
    PageIn,
    TenderOptionsIn,
    RedeemCheckIn,
    RedeemIn,
    ServiceBulkIn,
    ServiceForSaleIn,
    ServiceIn,
    ServiceListIn,
    ServicePatchIn,
    ServiceRefIn,
    SettingsIn,
    VoidIn,
)

router = Router(tags=["service"])


# Services


@bind(router, "service.service.list", "/service/services")
async def service_list(request, params: Query[ServiceListIn]):
    return await run_operation(request, queries.list_services, params)


@bind(router, "service.service.get", "/service/services/detail")
async def service_get(request, params: Query[ServiceRefIn]):
    return await run_operation(request, queries.get_service, params)


@bind(router, "service.service.list_for_sale", "/service/services/for_sale")
async def service_for_sale(request, params: Query[ServiceForSaleIn]):
    return await run_operation(request, queries.list_for_sale, params)


@bind(router, "service.service.create", "/service/services", status=201)
async def service_create(request, data: ServiceIn):
    return await run_operation(request, services.create_service, data)


@bind(
    router, "service.service.bulk_create", "/service/services/bulk_create", status=201
)
async def service_bulk_create(request, data: ServiceBulkIn):
    return await run_operation(request, services.bulk_create_services, data)


@bind(router, "service.service.update", "/service/services/update")
async def service_update(request, data: ServicePatchIn):
    return await run_operation(request, services.update_service, data)


@bind(router, "service.service.archive", "/service/services/archive")
async def service_archive(request, data: ServiceRefIn):
    return await run_operation(request, services.archive_service, data)


@bind(router, "service.service.restore", "/service/services/restore")
async def service_restore(request, data: ServiceRefIn):
    return await run_operation(request, services.restore_service, data)


@bind(router, "service.catalog.status", "/service/catalog/status")
async def catalog_status(request):
    return await run_operation(request, queries.catalog_status)


# Categories


@bind(router, "service.category.list", "/service/categories")
async def category_list(request, params: Query[CategoryListIn]):
    return await run_operation(request, queries.list_categories, params)


@bind(router, "service.category.get", "/service/categories/detail")
async def category_get(request, params: Query[CategoryRefIn]):
    return await run_operation(request, queries.get_category, params)


@bind(router, "service.category.create", "/service/categories", status=201)
async def category_create(request, data: CategoryIn):
    return await run_operation(request, services.create_category, data)


@bind(router, "service.category.update", "/service/categories/update")
async def category_update(request, data: CategoryPatchIn):
    return await run_operation(request, services.update_category, data)


@bind(router, "service.category.delete", "/service/categories/delete")
async def category_delete(request, data: CategoryRefIn):
    return await run_operation(request, services.delete_category, data)


# Settings


@bind(router, "service.settings.get", "/service/settings")
async def settings_get(request):
    return await run_operation(request, queries.get_settings)


@bind(router, "service.settings.update", "/service/settings")
async def settings_update(request, data: SettingsIn):
    return await run_operation(request, services.update_settings, data)


# Who performs each service


@bind(router, "service.assignment.list", "/service/assignments")
async def assignment_list(request, params: Query[AssignmentListIn]):
    return await run_operation(request, queries.list_assignments, params)


@bind(router, "service.assignment.eligible", "/service/assignments/eligible")
async def assignment_eligible(request, params: Query[EligibleIn]):
    return await run_operation(request, queries.eligible, params)


@bind(router, "service.assignment.assign", "/service/assignments/assign")
async def assignment_assign(request, data: AssignIn):
    return await run_operation(request, services.assign, data)


@bind(router, "service.assignment.update", "/service/assignments/update")
async def assignment_update(request, data: AssignmentPatchIn):
    return await run_operation(request, services.update_assignment, data)


@bind(router, "service.assignment.remove", "/service/assignments/remove")
async def assignment_remove(request, data: ByIdIn):
    return await run_operation(request, services.remove_assignment, data)


# Packages


@bind(router, "service.package.list", "/service/packages")
async def package_list(request, params: Query[PackageListIn]):
    return await run_operation(request, queries.list_packages, params)


@bind(router, "service.package.get", "/service/packages/detail")
async def package_get(request, params: Query[PackageRefIn]):
    return await run_operation(request, queries.get_package, params)


@bind(router, "service.package.create", "/service/packages", status=201)
async def package_create(request, data: PackageIn):
    return await run_operation(request, services.create_package, data)


@bind(router, "service.package.update", "/service/packages/update")
async def package_update(request, data: PackagePatchIn):
    return await run_operation(request, services.update_package, data)


@bind(router, "service.package.delete", "/service/packages/delete")
async def package_delete(request, data: PackageRefIn):
    return await run_operation(request, services.delete_package, data)


# Vouchers sold


@bind(router, "service.grant.list", "/service/grants")
async def grant_list(request, params: Query[GrantListIn]):
    return await run_operation(request, queries.list_grants, params)


@bind(router, "service.grant.list_orphans", "/service/grants/orphans")
async def grant_orphans(request, params: Query[PageIn]):
    return await run_operation(request, queries.list_orphans, params)


@bind(router, "service.grant.void_check", "/service/grants/void_check")
async def grant_void_check(request, params: Query[ByIdIn]):
    return await run_operation(request, queries.void_check, params)


@bind(router, "service.grant.adjust_check", "/service/grants/adjust_check")
async def grant_adjust_check(request, params: Query[ByIdIn]):
    return await run_operation(request, queries.adjust_check, params)


@bind(router, "service.grant.redeem_check", "/service/grants/redeem_check")
async def grant_redeem_check(request, params: Query[RedeemCheckIn]):
    return await run_operation(request, queries.redeem_check, params)


@bind(router, "service.grant.tender_options", "/service/grants/tender_options")
async def grant_tender_options(request, params: Query[TenderOptionsIn]):
    return await run_operation(request, queries.tender_options, params)


@bind(router, "service.grant.create", "/service/grants", status=201)
async def grant_create(request, data: GrantIn):
    return await run_operation(request, services.create_grant, data)


@bind(router, "service.grant.void", "/service/grants/void")
async def grant_void(request, data: VoidIn):
    return await run_operation(request, services.void_grant, data)


@bind(router, "service.grant.adjust", "/service/grants/adjust")
async def grant_adjust(request, data: AdjustIn):
    return await run_operation(request, services.adjust_grant, data)


@bind(router, "service.grant.redeem", "/service/grants/redeem")
async def grant_redeem(request, data: RedeemIn):
    return await run_operation(request, services.redeem, data)


# Movements


@bind(router, "service.movement.list", "/service/movements")
async def movement_list(request, params: Query[MovementListIn]):
    return await run_operation(request, queries.list_movements, params)
