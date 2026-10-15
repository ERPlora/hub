// Routes → pages of the schedule app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The three sections of the old module (Hours, Special days, Settings), on the
// paths of the menu in apps.py. Types only: `main.ts` globs this file eagerly and Vite hoists that glob
// above the shell's boot hooks. Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/schedule/hours',
    component: () => import('./pages/HoursPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/schedule/special-days',
    component: () => import('./pages/SpecialDaysPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/schedule/settings',
    component: () => import('./pages/SettingsPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
