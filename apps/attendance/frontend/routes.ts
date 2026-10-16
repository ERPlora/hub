// Routes → pages of the attendance app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The old module's two sections (Clock in, Records) on the paths of the menu
// in apps.py, plus Settings (the old shell's settings tab). Types only: `main.ts` globs this file eagerly
// and Vite hoists that glob above the shell's boot hooks. Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/attendance/clock',
    component: () => import('./pages/ClockPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/attendance/records',
    component: () => import('./pages/RecordsPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/attendance/settings',
    component: () => import('./pages/SettingsPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
