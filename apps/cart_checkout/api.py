"""Ninja routes of the cart_checkout app: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``): a cart's, a line's or an order's id travels in the input, because
a route takes one parameter, the operation's input.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.cart_checkout import queries, services
from apps.cart_checkout.schemas import (
    AbandonIn,
    CartIn,
    CartListIn,
    CartRefIn,
    CheckoutIn,
    CleanupIn,
    CustomerEraseIn,
    FailIn,
    ItemAddIn,
    ItemListIn,
    ItemRefIn,
    ItemUpdateIn,
    OrderListIn,
    OrderRefIn,
)

router = Router(tags=["cart_checkout"])


# Carts


@bind(router, "cart_checkout.cart.list", "/cart_checkout/carts")
async def cart_list(request, params: Query[CartListIn]):
    return await run_operation(request, queries.list_carts, params)


@bind(router, "cart_checkout.cart.get", "/cart_checkout/carts/detail")
async def cart_get(request, params: Query[CartRefIn]):
    return await run_operation(request, queries.get_cart, params)


@bind(router, "cart_checkout.cart.create", "/cart_checkout/carts", status=201)
async def cart_create(request, data: CartIn):
    return await run_operation(request, services.create_cart, data)


@bind(router, "cart_checkout.cart.mark_abandoned", "/cart_checkout/carts/mark_abandoned")
async def cart_mark_abandoned(request, data: AbandonIn):
    return await run_operation(request, services.mark_abandoned, data)


@bind(router, "cart_checkout.cart.delete", "/cart_checkout/carts/delete")
async def cart_delete(request, data: CartRefIn):
    return await run_operation(request, services.delete_cart, data)


@bind(router, "cart_checkout.cart.clear", "/cart_checkout/carts/clear")
async def cart_clear(request, data: CartRefIn):
    return await run_operation(request, services.clear_cart, data)


@bind(router, "cart_checkout.cart.cleanup_expired", "/cart_checkout/carts/cleanup_expired")
async def cart_cleanup_expired(request, data: CleanupIn):
    return await run_operation(request, services.cleanup_expired, data)


# Lines


@bind(router, "cart_checkout.item.list", "/cart_checkout/items")
async def item_list(request, params: Query[ItemListIn]):
    return await run_operation(request, queries.list_items, params)


@bind(router, "cart_checkout.item.get", "/cart_checkout/items/detail")
async def item_get(request, params: Query[ItemRefIn]):
    return await run_operation(request, queries.get_item, params)


@bind(router, "cart_checkout.item.add", "/cart_checkout/items", status=201)
async def item_add(request, data: ItemAddIn):
    return await run_operation(request, services.add_item, data)


@bind(router, "cart_checkout.item.update", "/cart_checkout/items/update")
async def item_update(request, data: ItemUpdateIn):
    return await run_operation(request, services.update_item, data)


@bind(router, "cart_checkout.item.remove", "/cart_checkout/items/remove")
async def item_remove(request, data: ItemRefIn):
    return await run_operation(request, services.remove_item, data)


# Orders


@bind(router, "cart_checkout.checkout.initiate", "/cart_checkout/checkout/initiate", status=201)
async def checkout_initiate(request, data: CheckoutIn):
    return await run_operation(request, services.initiate_checkout, data)


@bind(router, "cart_checkout.order.list", "/cart_checkout/orders")
async def order_list(request, params: Query[OrderListIn]):
    return await run_operation(request, queries.list_orders, params)


@bind(router, "cart_checkout.order.get", "/cart_checkout/orders/detail")
async def order_get(request, params: Query[OrderRefIn]):
    return await run_operation(request, queries.get_order, params)


@bind(router, "cart_checkout.order.mark_paid", "/cart_checkout/orders/mark_paid")
async def order_mark_paid(request, data: OrderRefIn):
    return await run_operation(request, services.mark_paid, data)


@bind(router, "cart_checkout.order.fail", "/cart_checkout/orders/fail")
async def order_fail(request, data: FailIn):
    return await run_operation(request, services.fail_order, data)


@bind(router, "cart_checkout.order.complete", "/cart_checkout/orders/complete")
async def order_complete(request, data: OrderRefIn):
    return await run_operation(request, services.complete_order, data)


# Personal data


@bind(router, "cart_checkout.customer.erase", "/cart_checkout/customers/erase")
async def customer_erase(request, data: CustomerEraseIn):
    return await run_operation(request, services.erase_customer, data)
