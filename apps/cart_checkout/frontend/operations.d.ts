// Types of the cart_checkout app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`),
// from apps/cart_checkout/schemas.py. Written by hand, as the other apps', until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py (tests/test_queries.py compares the list inputs)
// and `frontend/generated/operations.json`. One input per operation (ninja's parity): no path
// parameters, an id travels in the input. On the wire: money in whole minor units of its currency,
// quantities as decimal strings (`"2.500"`), moments ISO 8601.
import type { Page } from '../../../frontend/sdk-types';

export type CartStatus = 'active' | 'abandoned' | 'converted' | 'expired';
export type OrderStatus = 'initiated' | 'paid' | 'failed' | 'completed';
/** A decimal as JSON carries it: a string out of the server (`"2.500"`), a string or number in. */
export type DecimalText = string;
export type FreeFields = Record<string, string>;

export interface PageIn {
  limit?: number;
  offset?: number;
}

// ── Carts ──────────────────────────────────────────────────────────────────────────────────────

/** A cart by its id, its session code or its customer (exact email or part of the name). */
export interface CartRefIn {
  cart_id?: string | null;
  session_token?: string | null;
  customer?: string | null;
}

export interface CartIn {
  session_token: string;
  customer_email?: string;
  customer_name?: string;
  /** ISO 4217; without it, the business's currency. */
  currency?: string | null;
  expires_at?: string | null;
}

export interface AbandonIn extends CartRefIn {
  reason?: string;
}

export type CleanupIn = Record<string, never>;

export interface CleanupOut {
  expired: number;
}

export interface CartListIn extends PageIn {
  search?: string;
  session_token?: string;
  customer_email?: string;
  customer_name?: string;
  status?: CartStatus;
  currency?: string;
  notes?: string;
  total_items_min?: DecimalText;
  total_items_max?: DecimalText;
  /** Minor units, both ends inclusive. */
  total_amount_min?: number;
  total_amount_max?: number;
  expires_from?: string;
  expires_to?: string;
  last_activity_from?: string;
  last_activity_to?: string;
  created_from?: string;
  created_to?: string;
  /** A column, `-` first for descending; by default `-created_at`. */
  sort?: string;
}

export interface CartOut {
  id: string;
  session_token: string;
  customer_email: string;
  customer_name: string;
  /** An active cart past its expiry reads as `expired`. */
  status: CartStatus;
  total_items: DecimalText;
  /** Minor units of `currency`. */
  total_amount: number;
  currency: string;
  expires_at: string | null;
  last_activity_at: string | null;
  notes: string;
  abandon_reason: string;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
}

// ── Lines ──────────────────────────────────────────────────────────────────────────────────────

export interface ItemOut {
  id: string;
  cart_id: string;
  product_ref: string;
  product_name: string;
  sku: string;
  quantity: DecimalText;
  unit_price: number;
  line_total: number;
  variant_attributes: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CartDetailOut extends CartOut {
  items: ItemOut[];
}

export interface ItemRefIn {
  item_id: string;
}

export interface ItemAddIn extends CartRefIn {
  product_ref: string;
  product_name: string;
  sku?: string;
  quantity: DecimalText | number;
  unit_price: number;
  variant_attributes?: FreeFields;
}

export interface ItemUpdateIn extends ItemRefIn {
  /** 0 removes the line. */
  quantity: DecimalText | number;
}

export interface ItemChangeOut {
  item: ItemOut | null;
  removed: boolean;
  cart: CartOut;
}

export interface ItemListIn extends PageIn {
  cart_id?: string | null;
  session_token?: string | null;
  search?: string;
  product_ref?: string;
  product_name?: string;
  sku?: string;
  quantity_min?: DecimalText;
  quantity_max?: DecimalText;
  unit_price_min?: number;
  unit_price_max?: number;
  line_total_min?: number;
  line_total_max?: number;
  sort?: string;
}

// ── Orders ─────────────────────────────────────────────────────────────────────────────────────

/** An order by its id or its number (`OS-20261014-0003`). */
export interface OrderRefIn {
  order_id?: string | null;
  order_number?: string | null;
}

export interface FailIn extends OrderRefIn {
  reason: string;
}

export interface CheckoutIn extends CartRefIn {
  /** Without it, the cart's. */
  customer_email?: string | null;
  shipping_address?: FreeFields;
  /** Without it, the shipping address. */
  billing_address?: FreeFields | null;
  shipping_method?: string;
  payment_method?: string;
  notes?: string;
}

export interface OrderListIn extends PageIn {
  search?: string;
  cart_id?: string;
  order_number?: string;
  customer_email?: string;
  shipping_method?: string;
  payment_method?: string;
  status?: OrderStatus;
  currency?: string;
  notes?: string;
  /** Minor units, both ends inclusive. */
  total_amount_min?: number;
  total_amount_max?: number;
  placed_from?: string;
  placed_to?: string;
  paid_from?: string;
  paid_to?: string;
  completed_from?: string;
  completed_to?: string;
  created_from?: string;
  created_to?: string;
  /** A column, `-` first for descending; by default `-created_at`. */
  sort?: string;
}

export interface OrderOut {
  id: string;
  cart_id: string;
  /** The session code of its cart. */
  session_token: string;
  order_number: string;
  customer_email: string;
  shipping_address: Record<string, unknown>;
  billing_address: Record<string, unknown>;
  shipping_method: string;
  payment_method: string;
  status: OrderStatus;
  /** Minor units of `currency`. */
  total_amount: number;
  currency: string;
  notes: string;
  failure_reason: string;
  placed_at: string | null;
  paid_at: string | null;
  failed_at: string | null;
  completed_at: string | null;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
}

// ── Personal data ──────────────────────────────────────────────────────────────────────────────

/** The customer's exact email (any case). */
export interface CustomerEraseIn {
  email: string;
}

export interface CustomerEraseOut {
  carts: number;
  orders: number;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'cart_checkout.cart.list': { input: CartListIn; output: Page<CartOut> };
    'cart_checkout.cart.get': { input: CartRefIn; output: CartDetailOut };
    'cart_checkout.cart.create': { input: CartIn; output: CartOut };
    'cart_checkout.cart.mark_abandoned': { input: AbandonIn; output: CartOut };
    'cart_checkout.cart.delete': { input: CartRefIn; output: CartOut };
    'cart_checkout.cart.clear': { input: CartRefIn; output: CartOut };
    'cart_checkout.cart.cleanup_expired': { input: CleanupIn; output: CleanupOut };
    'cart_checkout.item.list': { input: ItemListIn; output: Page<ItemOut> };
    'cart_checkout.item.get': { input: ItemRefIn; output: ItemOut };
    'cart_checkout.item.add': { input: ItemAddIn; output: ItemChangeOut };
    'cart_checkout.item.update': { input: ItemUpdateIn; output: ItemChangeOut };
    'cart_checkout.item.remove': { input: ItemRefIn; output: ItemChangeOut };
    'cart_checkout.checkout.initiate': { input: CheckoutIn; output: OrderOut };
    'cart_checkout.order.list': { input: OrderListIn; output: Page<OrderOut> };
    'cart_checkout.order.get': { input: OrderRefIn; output: OrderOut };
    'cart_checkout.order.mark_paid': { input: OrderRefIn; output: OrderOut };
    'cart_checkout.order.fail': { input: FailIn; output: OrderOut };
    'cart_checkout.order.complete': { input: OrderRefIn; output: OrderOut };
    'cart_checkout.customer.erase': { input: CustomerEraseIn; output: CustomerEraseOut };
  }
}
