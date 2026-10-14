// Routes → pages of the inventory app, and nothing else: menu, permissions and active apps come from
// the server (`base.session.me`). One route per tab of the old module (Dashboard, Products,
// Movements, Categories) plus Settings; `/inventory` lands on the dashboard. Types only: `main.ts`
// globs this file eagerly and Vite hoists that glob above the shell's boot hooks. Each page is its
// own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  { path: '/inventory', redirect: '/inventory/dashboard', meta: { auth: true } },
  {
    path: '/inventory/dashboard',
    component: () => import('./pages/DashboardPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/inventory/products',
    component: () => import('./pages/ProductsPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/inventory/movements',
    component: () => import('./pages/MovementsPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/inventory/categories',
    component: () => import('./pages/CategoriesPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/inventory/settings',
    component: () => import('./pages/SettingsPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
