// Routes → pages of the service app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The three sections of the old module (Services, Categories, Packages) on
// the paths of the menu in apps.py, plus Settings (the old shell's settings tab). Types only: `main.ts`
// globs this file eagerly and Vite hoists that glob above the shell's boot hooks. Each page is its own
// chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/service/services',
    component: () => import('./pages/ServicesPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/service/categories',
    component: () => import('./pages/CategoriesPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/service/packages',
    component: () => import('./pages/PackagesPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/service/settings',
    component: () => import('./pages/SettingsPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
