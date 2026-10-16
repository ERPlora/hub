// Routes → pages of the cart_checkout app, and nothing else: menu, permissions and active apps come from
// the server (`base.session.me`). Its two sections (Carts, Orders) on the paths of the menu in apps.py.
// Types only: `main.ts` globs this file eagerly and Vite hoists that glob above the shell's boot hooks.
// Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/cart_checkout/carts',
    component: () => import('./pages/CartsPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/cart_checkout/orders',
    component: () => import('./pages/OrdersPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
