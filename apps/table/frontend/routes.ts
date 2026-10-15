// Routes → pages of the table app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The four sections of the old module (Floor plan, Zones, Tables, Sessions)
// on the paths of the menu in apps.py, plus Settings (the old shell's settings tab). Types only: `main.ts`
// globs this file eagerly and Vite hoists that glob above the shell's boot hooks. Each page is its own
// chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  { path: '/table/floor-plan', component: () => import('./pages/FloorPlanPage.vue'), meta: { auth: true } },
  { path: '/table/zones', component: () => import('./pages/ZonesPage.vue'), meta: { auth: true } },
  { path: '/table/tables', component: () => import('./pages/TablesPage.vue'), meta: { auth: true } },
  { path: '/table/sessions', component: () => import('./pages/SessionsPage.vue'), meta: { auth: true } },
  { path: '/table/settings', component: () => import('./pages/SettingsPage.vue'), meta: { auth: true } },
];

export default routes;
