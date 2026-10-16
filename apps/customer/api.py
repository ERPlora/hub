"""Ninja routes of the customer app: each route calls exactly one operation and holds no logic.

No path parameters: ids travel in the input (query string on GET, body on POST), because a route
takes one parameter, the operation's input. ``customer.purchase.record`` and ``.void`` have no
route: only the system runs them (the sale app's events).
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.customer import queries, services
from apps.customer.schemas import (
    ActivityIn,
    ActivityListIn,
    ByPhoneIn,
    ConsentGrantIn,
    ConsentHistoryIn,
    ConsentStateIn,
    ConsentWithdrawIn,
    CustomerExportIn,
    CustomerIn,
    CustomerListIn,
    CustomerPatchIn,
    CustomerRefIn,
    DivergencesIn,
    EraseIn,
    FieldIn,
    FieldListIn,
    FieldPatchIn,
    FieldRefIn,
    GroupIn,
    GroupListIn,
    GroupPatchIn,
    GroupRefIn,
    HealthDetailIn,
    HealthGrantIn,
    HealthIn,
    HealthWithdrawIn,
    ImportIn,
    MergeIn,
    NoteIn,
    OrderIn,
    OrderLinkIn,
    OrderListIn,
    PurchaseListIn,
    SetGroupsIn,
    SetTagsIn,
    TagIn,
    TagListIn,
    TagPatchIn,
    TagRefIn,
)

router = Router(tags=["customer"])


# Customers


@bind(router, "customer.customer.list", "/customer/customers")
async def customer_list(request, params: Query[CustomerListIn]):
    return await run_operation(request, queries.list_customers, params)


@bind(router, "customer.customer.detail", "/customer/customers/detail")
async def customer_detail(request, params: Query[CustomerRefIn]):
    return await run_operation(request, queries.customer_detail, params)


@bind(router, "customer.customer.stats", "/customer/customers/stats")
async def customer_stats(request):
    return await run_operation(request, queries.customer_stats)


@bind(router, "customer.customer.by_phone", "/customer/customers/by_phone")
async def customer_by_phone(request, params: Query[ByPhoneIn]):
    return await run_operation(request, queries.customers_by_phone, params)


@bind(router, "customer.customer.export", "/customer/customers/export")
async def customer_export(request, params: Query[CustomerExportIn]):
    return await run_operation(request, queries.export_customers, params)


@bind(router, "customer.customer.create", "/customer/customers", status=201)
async def customer_create(request, data: CustomerIn):
    return await run_operation(request, services.create_customer, data)


@bind(router, "customer.customer.update", "/customer/customers/update")
async def customer_update(request, data: CustomerPatchIn):
    return await run_operation(request, services.update_customer, data)


@bind(router, "customer.customer.import", "/customer/customers/import")
async def customer_import(request, data: ImportIn):
    return await run_operation(request, services.import_customers, data)


@bind(router, "customer.customer.set_groups", "/customer/customers/set_groups")
async def customer_set_groups(request, data: SetGroupsIn):
    return await run_operation(request, services.set_groups, data)


@bind(router, "customer.customer.set_tags", "/customer/customers/set_tags")
async def customer_set_tags(request, data: SetTagsIn):
    return await run_operation(request, services.set_tags, data)


@bind(router, "customer.customer.delete", "/customer/customers/delete")
async def customer_delete(request, data: CustomerRefIn):
    return await run_operation(request, services.delete_customer, data)


@bind(router, "customer.customer.merge", "/customer/customers/merge")
async def customer_merge(request, data: MergeIn):
    return await run_operation(request, services.merge_customers, data)


@bind(router, "customer.customer.erase", "/customer/customers/erase")
async def customer_erase(request, data: EraseIn):
    return await run_operation(request, services.erase_customer, data)


# Groups, tags and custom fields


@bind(router, "customer.group.list", "/customer/groups")
async def group_list(request, params: Query[GroupListIn]):
    return await run_operation(request, queries.list_groups, params)


@bind(router, "customer.group.create", "/customer/groups", status=201)
async def group_create(request, data: GroupIn):
    return await run_operation(request, services.create_group, data)


@bind(router, "customer.group.update", "/customer/groups/update")
async def group_update(request, data: GroupPatchIn):
    return await run_operation(request, services.update_group, data)


@bind(router, "customer.group.delete", "/customer/groups/delete")
async def group_delete(request, data: GroupRefIn):
    return await run_operation(request, services.delete_group, data)


@bind(router, "customer.tag.list", "/customer/tags")
async def tag_list(request, params: Query[TagListIn]):
    return await run_operation(request, queries.list_tags, params)


@bind(router, "customer.tag.create", "/customer/tags", status=201)
async def tag_create(request, data: TagIn):
    return await run_operation(request, services.create_tag, data)


@bind(router, "customer.tag.update", "/customer/tags/update")
async def tag_update(request, data: TagPatchIn):
    return await run_operation(request, services.update_tag, data)


@bind(router, "customer.tag.delete", "/customer/tags/delete")
async def tag_delete(request, data: TagRefIn):
    return await run_operation(request, services.delete_tag, data)


@bind(router, "customer.field.list", "/customer/fields")
async def field_list(request, params: Query[FieldListIn]):
    return await run_operation(request, queries.list_fields, params)


@bind(router, "customer.field.create", "/customer/fields", status=201)
async def field_create(request, data: FieldIn):
    return await run_operation(request, services.create_field, data)


@bind(router, "customer.field.update", "/customer/fields/update")
async def field_update(request, data: FieldPatchIn):
    return await run_operation(request, services.update_field, data)


@bind(router, "customer.field.delete", "/customer/fields/delete")
async def field_delete(request, data: FieldRefIn):
    return await run_operation(request, services.delete_field, data)


# A card's notes, activity, purchases, consent and orders


@bind(router, "customer.activity.list", "/customer/activity")
async def activity_list(request, params: Query[ActivityListIn]):
    return await run_operation(request, queries.list_activity, params)


@bind(router, "customer.activity.add", "/customer/activity", status=201)
async def activity_add(request, data: ActivityIn):
    return await run_operation(request, services.add_activity, data)


@bind(router, "customer.note.add", "/customer/notes", status=201)
async def note_add(request, data: NoteIn):
    return await run_operation(request, services.add_note, data)


@bind(router, "customer.purchase.list", "/customer/purchases")
async def purchase_list(request, params: Query[PurchaseListIn]):
    return await run_operation(request, queries.list_purchases, params)


@bind(router, "customer.purchase.divergences", "/customer/purchases/divergences")
async def purchase_divergences(request, params: Query[DivergencesIn]):
    return await run_operation(request, queries.purchase_divergences, params)


@bind(router, "customer.consent.history", "/customer/consents")
async def consent_history(request, params: Query[ConsentHistoryIn]):
    return await run_operation(request, queries.consent_history, params)


@bind(router, "customer.consent.state", "/customer/consents/state")
async def consent_state(request, params: Query[ConsentStateIn]):
    return await run_operation(request, queries.consent_state, params)


@bind(router, "customer.consent.grant", "/customer/consents/grant", status=201)
async def consent_grant(request, data: ConsentGrantIn):
    return await run_operation(request, services.grant_consent, data)


@bind(router, "customer.consent.withdraw", "/customer/consents/withdraw", status=201)
async def consent_withdraw(request, data: ConsentWithdrawIn):
    return await run_operation(request, services.withdraw_consent, data)


# Health data (CUSTOMER-F32): for the screen only (no API key reaches these operations).


@bind(router, "customer.health.detail", "/customer/health")
async def health_detail(request, params: Query[HealthDetailIn]):
    return await run_operation(request, queries.health_detail, params)


@bind(router, "customer.health.grant", "/customer/health/grant")
async def health_grant(request, data: HealthGrantIn):
    return await run_operation(request, services.grant_health, data)


@bind(router, "customer.health.withdraw", "/customer/health/withdraw")
async def health_withdraw(request, data: HealthWithdrawIn):
    return await run_operation(request, services.withdraw_health, data)


@bind(router, "customer.health.update", "/customer/health/update")
async def health_update(request, data: HealthIn):
    return await run_operation(request, services.update_health, data)


@bind(router, "customer.order.list", "/customer/orders")
async def order_list(request, params: Query[OrderListIn]):
    return await run_operation(request, queries.list_orders, params)


@bind(router, "customer.order.customer", "/customer/orders/customer")
async def order_customer(request, params: Query[OrderIn]):
    return await run_operation(request, queries.order_customer, params)


@bind(router, "customer.order.link", "/customer/orders/link")
async def order_link(request, data: OrderLinkIn):
    return await run_operation(request, services.link_order, data)
