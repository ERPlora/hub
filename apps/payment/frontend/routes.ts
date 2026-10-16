// Routes → pages of the payment app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). Its two sections (Payments, Methods) on the paths of the menu in apps.py.
// Types only: `main.ts` globs this file eagerly and Vite hoists that glob above the shell's boot hooks.
// Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/payment/payments',
    component: () => import('./pages/PaymentsPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/payment/methods',
    component: () => import('./pages/MethodsPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
