"""Routes of People and permissions: people and roles, the business's API keys, a manager's approval and the
API's documentation."""

from live.ninja import bind, run_operation
from ninja import Query, Router

from base import queries, services
from base.schemas.api_keys import ApiDocSettingsUpdateIn, ApiKeyCreateIn, ApiKeyIdIn
from base.schemas.approvals import ApprovalExportIn, ApprovalIn, ApproversIn
from base.schemas.people import BadgeSetIn, PersonIn
from base.schemas.roles import RoleAssignIn, RoleCreateIn, RoleIn, RoleUpdateIn

router = Router()


# ── People and permissions: people, roles ───────────────────────────────────────────────────────────────────────────


@bind(router, "base.person.list", "/people")
async def person_list(request):
    return await run_operation(request, queries.people.person_list)


@bind(router, "base.person.detail", "/people/detail")
async def person_detail(request, data: Query[PersonIn]):
    return await run_operation(request, queries.people.person_detail, data)


@bind(router, "base.person.pin_remove", "/people/pin/remove")
async def person_pin_remove(request, data: PersonIn):
    return await run_operation(request, services.people.person_pin_remove, data)


@bind(router, "base.person.badge_set", "/people/badge")
async def person_badge_set(request, data: BadgeSetIn):
    return await run_operation(request, services.people.person_badge_set, data)


@bind(router, "base.person.badge_remove", "/people/badge/remove")
async def person_badge_remove(request, data: PersonIn):
    return await run_operation(request, services.people.person_badge_remove, data)


@bind(router, "base.role.list", "/roles")
async def role_list(request):
    return await run_operation(request, queries.roles.role_list)


@bind(router, "base.role.detail", "/roles/detail")
async def role_detail(request, data: Query[RoleIn]):
    return await run_operation(request, queries.roles.role_detail, data)


@bind(router, "base.role.create", "/roles")
async def role_create(request, data: RoleCreateIn):
    return await run_operation(request, services.roles.role_create, data)


@bind(router, "base.role.update", "/roles/update")
async def role_update(request, data: RoleUpdateIn):
    return await run_operation(request, services.roles.role_update, data)


@bind(router, "base.role.delete", "/roles/delete")
async def role_delete(request, data: RoleIn):
    return await run_operation(request, services.roles.role_delete, data)


@bind(router, "base.role.assign", "/roles/assign")
async def role_assign(request, data: RoleAssignIn):
    return await run_operation(request, services.roles.role_assign, data)


# ── People and permissions: the business's API keys ────────────────────────────────────────────────────────────────


@bind(router, "base.api_key.list", "/keys")
async def api_key_list(request):
    return await run_operation(request, queries.api_keys.api_key_list)


@bind(router, "base.api_key.detail", "/keys/detail")
async def api_key_detail(request, data: Query[ApiKeyIdIn]):
    return await run_operation(request, queries.api_keys.api_key_detail, data)


@bind(router, "base.api_key.create", "/keys")
async def api_key_create(request, data: ApiKeyCreateIn):
    return await run_operation(request, services.api_keys.api_key_create, data)


@bind(router, "base.api_key.rotate", "/keys/rotate")
async def api_key_rotate(request, data: ApiKeyIdIn):
    return await run_operation(request, services.api_keys.api_key_rotate, data)


@bind(router, "base.api_key.revoke", "/keys/revoke")
async def api_key_revoke(request, data: ApiKeyIdIn):
    return await run_operation(request, services.api_keys.api_key_revoke, data)


# ── People and permissions: a manager's approval ───────────────────────────────────────────────────────────────────


@bind(router, "base.approval.list", "/approvals")
async def approval_list(request):
    return await run_operation(request, queries.approvals.approval_list)


@bind(router, "base.approval.export", "/approvals/export")
async def approval_export(request, data: Query[ApprovalExportIn]):
    return await run_operation(request, queries.approvals.approval_export, data)


@bind(router, "base.approval.approvers", "/approvals/approvers")
async def approval_approvers(request, data: Query[ApproversIn]):
    return await run_operation(request, queries.approvals.approval_approvers, data)


# «No access» names who can give the screen: by name only.
@bind(router, "base.access.grantors", "/access/grantors")
async def access_grantors(request):
    return await run_operation(request, queries.access_rights.access_grantors)


@bind(router, "base.approval.approve", "/approvals")
async def approval_approve(request, data: ApprovalIn):
    return await run_operation(request, services.approvals.approval_approve, data)


# ── People and permissions: the API's documentation ────────────────────────────────────────────────────────────────


@bind(router, "base.api_doc.get", "/api-docs")
async def api_doc_get(request):
    return await run_operation(request, queries.api_keys.api_doc_get)


@bind(router, "base.api_doc.settings", "/api-docs/settings")
async def api_doc_settings(request):
    return await run_operation(request, queries.api_keys.api_doc_settings)


@bind(router, "base.api_doc.settings_update", "/api-docs/settings/update")
async def api_doc_settings_update(request, data: ApiDocSettingsUpdateIn):
    return await run_operation(request, services.api_keys.api_doc_settings_update, data)
