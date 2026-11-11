// flow: BASE-F05 and one create form per app of hub#1031 (hub#1020's second stage; the walks are
// `expectBackAsksOnDirtyForm` and, for its own ways out, `expectWaysOutAskOnDirtyForm`, hub#1156). Time clock's only
// window, «Correct working day», is covered by its component test.
import { test } from '@playwright/test';

import { expectBackAsksOnDirtyForm, expectWaysOutAskOnDirtyForm, type UnsavedFormCase } from './unsaved-back-helpers';

const CASES: UnsavedFormCase[] = [
  { app: 'cart_checkout', flow: 'CART_CHECKOUT-F01', route: '/cart_checkout/carts', add: 'cart-checkout-carts-add', form: 'cart-checkout-cart-form', field: 'cart-checkout-cart-form-name' },
  { app: 'cash_register', flow: 'CASH_REGISTER-F02', route: '/cash_register/settings', add: 'cash-register-registers-add', form: 'cash-register-register', field: 'cash-register-register-name' },
  { app: 'combo', flow: 'COMBO-F02', route: '/combo/menus', add: 'combo-menus-add', form: 'combo-menu-form', field: 'combo-menu-form-name' },
  { app: 'inventory', flow: 'INVENTORY-F06', route: '/inventory/categories', add: 'inventory-categories-add', form: 'inventory-category-form', field: 'inventory-category-name' },
  { app: 'modifier', flow: 'MODIFIER-F02', route: '/modifier/groups', add: 'modifier-groups-add', form: 'modifier-group-form', field: 'modifier-group-form-name' },
  { app: 'payment', flow: 'PAYMENT-F01', route: '/payment/methods', add: 'payment-methods-add', form: 'payment-method-form', field: 'payment-method-form-name' },
  { app: 'pricing', flow: 'PRICING-F02', route: '/pricing/lists', add: 'pricing-lists-add', form: 'pricing-list-form', field: 'pricing-list-form-name' },
];

for (const item of CASES) {
  test(`${item.flow} ${item.app}: Android Back asks before discarding a dirty form and closes a clean one`, async ({ page }) => {
    await expectBackAsksOnDirtyForm(page, item, 'HUB-1031');
  });

  test(`${item.flow} ${item.app}: Cancel, ×, Escape and a tap outside ask before discarding a dirty form and close a clean one (hub#1156)`, async ({ page }) => {
    await expectWaysOutAskOnDirtyForm(page, item, 'HUB-1156');
  });
}
