"""Ninja routes of the payment app: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``): a payment's or a method's id travels in the input, because a
route takes one parameter, the operation's input.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.payment import queries, services
from apps.payment.schemas import (
    CancelIn,
    MethodIn,
    MethodListIn,
    MethodPatchIn,
    MethodRefIn,
    PaymentIn,
    PaymentListIn,
    PaymentRefIn,
)

router = Router(tags=["payment"])


# Payments


@bind(router, "payment.payment.list", "/payment/payments")
async def payment_list(request, params: Query[PaymentListIn]):
    return await run_operation(request, queries.list_payments, params)


@bind(router, "payment.payment.get", "/payment/payments/detail")
async def payment_get(request, params: Query[PaymentRefIn]):
    return await run_operation(request, queries.get_payment, params)


@bind(router, "payment.payment.create", "/payment/payments", status=201)
async def payment_create(request, data: PaymentIn):
    return await run_operation(request, services.create_payment, data)


@bind(router, "payment.payment.approve", "/payment/payments/approve")
async def payment_approve(request, data: PaymentRefIn):
    return await run_operation(request, services.approve_payment, data)


@bind(router, "payment.payment.mark_sent", "/payment/payments/mark_sent")
async def payment_mark_sent(request, data: PaymentRefIn):
    return await run_operation(request, services.mark_sent, data)


@bind(router, "payment.payment.mark_completed", "/payment/payments/mark_completed")
async def payment_mark_completed(request, data: PaymentRefIn):
    return await run_operation(request, services.mark_completed, data)


@bind(router, "payment.payment.cancel", "/payment/payments/cancel")
async def payment_cancel(request, data: CancelIn):
    return await run_operation(request, services.cancel_payment, data)


# Methods


@bind(router, "payment.method.list", "/payment/methods")
async def method_list(request, params: Query[MethodListIn]):
    return await run_operation(request, queries.list_methods, params)


@bind(router, "payment.method.get", "/payment/methods/detail")
async def method_get(request, params: Query[MethodRefIn]):
    return await run_operation(request, queries.get_method, params)


@bind(router, "payment.method.create", "/payment/methods", status=201)
async def method_create(request, data: MethodIn):
    return await run_operation(request, services.create_method, data)


@bind(router, "payment.method.update", "/payment/methods/update")
async def method_update(request, data: MethodPatchIn):
    return await run_operation(request, services.update_method, data)


@bind(router, "payment.method.deactivate", "/payment/methods/deactivate")
async def method_deactivate(request, data: MethodRefIn):
    return await run_operation(request, services.deactivate_method, data)


@bind(router, "payment.method.activate", "/payment/methods/activate")
async def method_activate(request, data: MethodRefIn):
    return await run_operation(request, services.activate_method, data)
