// Routes → pages of the sale app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The sections of the old module (Sell, Sales, Quick notes, Departments — «Sections» here) and
// the settings the old hub added as a tab, on the paths of the menu in apps.py. Types only: `main.ts`
// globs this file eagerly and Vite hoists that glob above the shell's boot hooks. Each page is its own
// chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  { path: '/sale/pos', component: () => import('./pages/PosPage.vue'), meta: { auth: true } },
  { path: '/sale/sales', component: () => import('./pages/SalesPage.vue'), meta: { auth: true } },
  { path: '/sale/quick-notes', component: () => import('./pages/QuickNotesPage.vue'), meta: { auth: true } },
  { path: '/sale/departments', component: () => import('./pages/DepartmentsPage.vue'), meta: { auth: true } },
  { path: '/sale/settings', component: () => import('./pages/SettingsPage.vue'), meta: { auth: true } },
];

export default routes;
