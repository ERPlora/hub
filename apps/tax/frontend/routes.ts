// Routes → pages of the tax app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The three sections of the old module (Categories, Rules, Aliases) and the
// business's tax region (Settings, TAX-F11), on the paths of the menu in apps.py. Types only: `main.ts` globs this file eagerly and Vite hoists that
// glob above the shell's boot hooks. Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/tax/categories',
    component: () => import('./pages/CategoriesPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/tax/rules',
    component: () => import('./pages/RulesPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/tax/aliases',
    component: () => import('./pages/AliasesPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/tax/settings',
    component: () => import('./pages/SettingsPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
