// What the tests of Sell mount in place of the checkout sheet, the document window and Customers' search, by their
// contracts. The `vi.mock` calls of `pos-page.ts` are hoisted above its imports, so their factories reach this module
// through a dynamic import; it imports nothing that imports those pieces, which would make a factory wait for itself.
import { h } from 'vue';

export const CHECKOUT_SHEET = {
  default: {
    name: 'CheckoutSheet',
    props: { open: Boolean, orderId: String, lineIds: Array, orderVersion: Number, customer: Object, staffId: String },
    emits: ['update:open', 'charged'],
    render: () => h('div', { 'data-testid': 'checkout-stub' }),
  },
};

export const DOCUMENT_MODAL = {
  default: {
    name: 'DocumentModal',
    props: { open: Boolean, saleId: String, duplicate: Boolean },
    emits: ['update:open'],
    render: () => h('div', { 'data-testid': 'document-stub' }),
  },
};

export const CUSTOMER_SEARCH = {
  default: {
    name: 'CustomerSearch',
    props: { modelValue: Object, open: Boolean },
    emits: ['update:modelValue', 'update:open'],
    render: () => h('button', { 'data-testid': 'customer-stub' }),
  },
};
