// What the tests of Sell mount in place of the checkout sheet, the document window and Customers' search, by their
// contracts. `vi.mock` is hoisted above a test's imports, so its factory reaches this module through a dynamic import,
// and this module imports nothing that imports those pieces:
//
//   vi.mock('../components/checkout/CheckoutSheet.vue', async () => (await import('../__tests__/pos-page-stubs')).CHECKOUT_SHEET);
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
