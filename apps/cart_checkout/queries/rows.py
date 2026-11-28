"""How a cart, a line and an order read in the operations that give one (``CartOut``, ``ItemOut``, ``OrderOut``)."""

from apps.cart_checkout.models import Cart, CartItem, Order
from apps.cart_checkout.queries.reads import state_of
from base.business import currency_decimals


def cart_row(cart: Cart) -> dict:
    """A cart as the operations give it, with its status now."""
    return {
        "id": cart.id,
        "session_token": cart.session_token,
        "customer_email": cart.customer_email,
        "customer_name": cart.customer_name,
        "status": getattr(cart, "state", None) or state_of(cart),
        "total_items": cart.total_items,
        "total_amount": cart.total_amount,
        "currency": cart.currency,
        "currency_decimals": currency_decimals(cart.currency),
        "expires_at": cart.expires_at,
        "last_activity_at": cart.last_activity_at,
        "notes": cart.notes,
        "abandon_reason": cart.abandon_reason,
        "created_by": cart.created_by,
        "updated_by": cart.updated_by,
        "created_at": cart.created_at,
        "updated_at": cart.updated_at,
    }


def item_row(item: CartItem) -> dict:
    """A line as the operations give it, with its cart's currency: the one its price and its total are in."""
    return {
        "id": item.id,
        "cart_id": item.cart_id,
        "product_ref": item.product_ref,
        "product_name": item.product_name,
        "sku": item.sku,
        "quantity": item.quantity,
        "unit_price": item.unit_price,
        "line_total": item.line_total,
        "currency": item.cart.currency,
        "currency_decimals": currency_decimals(item.cart.currency),
        "variant_attributes": item.variant_attributes,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def order_row(order: Order) -> dict:
    return {
        "id": order.id,
        "cart_id": order.cart_id,
        "session_token": order.cart.session_token,
        "order_number": order.order_number,
        "customer_email": order.customer_email,
        "shipping_address": order.shipping_address,
        "billing_address": order.billing_address,
        "shipping_method": order.shipping_method,
        "payment_method": order.payment_method,
        "status": order.status,
        "total_amount": order.total_amount,
        "currency": order.currency,
        "currency_decimals": currency_decimals(order.currency),
        "notes": order.notes,
        "failure_reason": order.failure_reason,
        "placed_at": order.placed_at,
        "paid_at": order.paid_at,
        "failed_at": order.failed_at,
        "completed_at": order.completed_at,
        "created_by": order.created_by,
        "updated_by": order.updated_by,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }
