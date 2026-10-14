"""Ninja routes of the sale app: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``): ids travel in the input, because a route takes one parameter,
the operation's input. The reaction to Customers' merge (``sale.customer.reassign``) has no route:
only the platform runs it.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.sale import queries, services
from apps.sale.schemas import (
    CompleteIn,
    DepartmentIn,
    DepartmentListIn,
    DepartmentRefIn,
    DepartmentUpdateIn,
    OrderAddLineIn,
    OrderAddOpenLineIn,
    OrderFireIn,
    OrderLineRefIn,
    OrderListIn,
    OrderMergeIn,
    OrderOpenIn,
    OrderRefIn,
    OrderSetAppointmentIn,
    OrderSetDiscountIn,
    OrderSetLabelIn,
    OrderSetLineDiscountIn,
    OrderSetLineStaffIn,
    OrderSplitIn,
    OrderUpdateLineIn,
    OrderVoidLineIn,
    PaymentMethodIn,
    PaymentMethodListIn,
    PeriodIn,
    PreviewIn,
    QuickNoteIn,
    QuickNoteListIn,
    QuickNoteRefIn,
    QuickNoteUpdateIn,
    RefundByKeyIn,
    RefundIn,
    SaleByKeyIn,
    SaleListIn,
    SaleRefIn,
    SettingsPatchIn,
    VoidIn,
)

router = Router(tags=["sale"])


# Sales


@bind(router, "sale.sale.list", "/sale/sales")
async def sale_list(request, params: Query[SaleListIn]):
    return await run_operation(request, queries.list_sales, params)


@bind(router, "sale.sale.get", "/sale/sales/detail")
async def sale_get(request, params: Query[SaleRefIn]):
    return await run_operation(request, queries.get_sale, params)


@bind(router, "sale.sale.by_idempotency_key", "/sale/sales/by_key")
async def sale_by_key(request, params: Query[SaleByKeyIn]):
    return await run_operation(request, queries.sale_by_key, params)


@bind(router, "sale.sale.stats", "/sale/sales/stats")
async def sale_stats(request, params: Query[PeriodIn]):
    return await run_operation(request, queries.stats, params)


@bind(router, "sale.sale.today", "/sale/sales/today")
async def sale_today(request):
    return await run_operation(request, queries.today)


@bind(router, "sale.sale.last_7_days", "/sale/sales/last_7_days")
async def sale_last_7_days(request):
    return await run_operation(request, queries.last_7_days)


@bind(router, "sale.sale.by_staff", "/sale/sales/by_staff")
async def sale_by_staff(request, params: Query[PeriodIn]):
    return await run_operation(request, queries.by_staff, params)


@bind(router, "sale.sale.complete", "/sale/sales", status=201)
async def sale_complete(request, data: CompleteIn):
    return await run_operation(request, services.complete, data)


@bind(
    router,
    "sale.sale.complete_over_limit",
    "/sale/sales/complete_over_limit",
    status=201,
)
async def sale_complete_over_limit(request, data: CompleteIn):
    return await run_operation(request, services.complete_over_limit, data)


@bind(router, "sale.sale.void", "/sale/sales/void")
async def sale_void(request, data: VoidIn):
    return await run_operation(request, services.void_sale, data)


@bind(router, "sale.sale.refund", "/sale/sales/refund")
async def sale_refund(request, data: RefundIn):
    return await run_operation(request, services.refund, data)


@bind(router, "sale.checkout.preview", "/sale/checkout/preview")
async def checkout_preview(request, params: Query[PreviewIn]):
    return await run_operation(request, queries.preview, params)


# Open checks


@bind(router, "sale.order.list", "/sale/orders")
async def order_list(request, params: Query[OrderListIn]):
    return await run_operation(request, queries.list_orders, params)


@bind(router, "sale.order.get", "/sale/orders/detail")
async def order_get(request, params: Query[OrderRefIn]):
    return await run_operation(request, queries.get_order, params)


@bind(router, "sale.order.open", "/sale/orders", status=201)
async def order_open(request, data: OrderOpenIn):
    return await run_operation(request, services.open_order, data)


@bind(router, "sale.order.add_line", "/sale/orders/add_line")
async def order_add_line(request, data: OrderAddLineIn):
    return await run_operation(request, services.add_line, data)


@bind(router, "sale.order.add_open_line", "/sale/orders/add_open_line")
async def order_add_open_line(request, data: OrderAddOpenLineIn):
    return await run_operation(request, services.add_open_line, data)


@bind(router, "sale.order.update_line", "/sale/orders/update_line")
async def order_update_line(request, data: OrderUpdateLineIn):
    return await run_operation(request, services.update_line, data)


@bind(router, "sale.order.set_line_staff", "/sale/orders/set_line_staff")
async def order_set_line_staff(request, data: OrderSetLineStaffIn):
    return await run_operation(request, services.set_line_staff, data)


@bind(router, "sale.order.split_line", "/sale/orders/split_line")
async def order_split_line(request, data: OrderLineRefIn):
    return await run_operation(request, services.split_line, data)


@bind(router, "sale.order.remove_line", "/sale/orders/remove_line")
async def order_remove_line(request, data: OrderLineRefIn):
    return await run_operation(request, services.remove_line, data)


@bind(router, "sale.order.void_line", "/sale/orders/void_line")
async def order_void_line(request, data: OrderVoidLineIn):
    return await run_operation(request, services.void_line, data)


@bind(router, "sale.order.fire", "/sale/orders/fire")
async def order_fire(request, data: OrderFireIn):
    return await run_operation(request, services.fire, data)


@bind(router, "sale.order.split", "/sale/orders/split")
async def order_split(request, data: OrderSplitIn):
    return await run_operation(request, services.split, data)


@bind(router, "sale.order.merge", "/sale/orders/merge")
async def order_merge(request, data: OrderMergeIn):
    return await run_operation(request, services.merge, data)


@bind(router, "sale.order.void", "/sale/orders/void")
async def order_void(request, data: OrderRefIn):
    return await run_operation(request, services.void_order, data)


@bind(router, "sale.order.set_discount", "/sale/orders/set_discount")
async def order_set_discount(request, data: OrderSetDiscountIn):
    return await run_operation(request, services.set_discount, data)


@bind(
    router, "sale.order.set_discount_over_limit", "/sale/orders/set_discount_over_limit"
)
async def order_set_discount_over_limit(request, data: OrderSetDiscountIn):
    return await run_operation(request, services.set_discount_over_limit, data)


@bind(router, "sale.order.set_line_discount", "/sale/orders/set_line_discount")
async def order_set_line_discount(request, data: OrderSetLineDiscountIn):
    return await run_operation(request, services.set_line_discount, data)


@bind(
    router,
    "sale.order.set_line_discount_over_limit",
    "/sale/orders/set_line_discount_over_limit",
)
async def order_set_line_discount_over_limit(request, data: OrderSetLineDiscountIn):
    return await run_operation(request, services.set_line_discount_over_limit, data)


@bind(router, "sale.order.set_label", "/sale/orders/set_label")
async def order_set_label(request, data: OrderSetLabelIn):
    return await run_operation(request, services.set_label, data)


@bind(router, "sale.order.set_appointment", "/sale/orders/set_appointment")
async def order_set_appointment(request, data: OrderSetAppointmentIn):
    return await run_operation(request, services.set_appointment, data)


# Payment methods and settings


@bind(router, "sale.payment_method.list", "/sale/payment_methods")
async def payment_method_list(request, params: Query[PaymentMethodListIn]):
    return await run_operation(request, queries.list_payment_methods, params)


@bind(router, "sale.payment_method.create", "/sale/payment_methods", status=201)
async def payment_method_create(request, data: PaymentMethodIn):
    return await run_operation(request, services.create_payment_method, data)


@bind(router, "sale.settings.get", "/sale/settings")
async def settings_get(request):
    return await run_operation(request, queries.get_settings)


@bind(router, "sale.settings.update", "/sale/settings")
async def settings_update(request, data: SettingsPatchIn):
    return await run_operation(request, services.update_settings, data)


@bind(router, "sale.pos_settings.get", "/sale/pos_settings")
async def pos_settings_get(request):
    return await run_operation(request, queries.get_pos_settings)


# Departments and quick notes


@bind(router, "sale.department.list", "/sale/departments")
async def department_list(request, params: Query[DepartmentListIn]):
    return await run_operation(request, queries.list_departments, params)


@bind(router, "sale.department.create", "/sale/departments", status=201)
async def department_create(request, data: DepartmentIn):
    return await run_operation(request, services.create_department, data)


@bind(router, "sale.department.update", "/sale/departments/update")
async def department_update(request, data: DepartmentUpdateIn):
    return await run_operation(request, services.update_department, data)


@bind(router, "sale.department.delete", "/sale/departments/delete")
async def department_delete(request, data: DepartmentRefIn):
    return await run_operation(request, services.delete_department, data)


@bind(router, "sale.quick_note.list", "/sale/quick_notes")
async def quick_note_list(request, params: Query[QuickNoteListIn]):
    return await run_operation(request, queries.list_quick_notes, params)


@bind(router, "sale.quick_note.create", "/sale/quick_notes", status=201)
async def quick_note_create(request, data: QuickNoteIn):
    return await run_operation(request, services.create_quick_note, data)


@bind(router, "sale.quick_note.update", "/sale/quick_notes/update")
async def quick_note_update(request, data: QuickNoteUpdateIn):
    return await run_operation(request, services.update_quick_note, data)


@bind(router, "sale.quick_note.delete", "/sale/quick_notes/delete")
async def quick_note_delete(request, data: QuickNoteRefIn):
    return await run_operation(request, services.delete_quick_note, data)


# The business day and refunds


@bind(router, "sale.business_day.get", "/sale/business_day")
async def business_day(request):
    return await run_operation(request, queries.business_day)


@bind(router, "sale.refund.list", "/sale/refunds")
async def refund_list(request, params: Query[SaleRefIn]):
    return await run_operation(request, queries.list_refunds, params)


@bind(router, "sale.refund.options", "/sale/refunds/options")
async def refund_options(request, params: Query[SaleRefIn]):
    return await run_operation(request, queries.refund_options, params)


@bind(router, "sale.refund.by_idempotency_key", "/sale/refunds/by_key")
async def refund_by_key(request, params: Query[RefundByKeyIn]):
    return await run_operation(request, queries.refund_by_key, params)
