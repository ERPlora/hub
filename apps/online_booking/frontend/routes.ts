// Routes → pages of the online booking app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The old module's two sections (Bookings, Settings), on the paths of the menu in
// apps.py. Types only: `main.ts` globs this file eagerly and Vite hoists that glob above the shell's boot
// hooks. Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/online_booking/bookings',
    component: () => import('./pages/BookingsPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/online_booking/settings',
    component: () => import('./pages/SettingsPage.vue'),
    meta: { auth: true },
  },
  // The public booking page is base's (Django templates, `/p/<slug>/book`); this preview drives the same
  // public operations on the dev server only (its e2e books through it).
  ...(import.meta.env.DEV
    ? [
        {
          path: '/online_booking/preview',
          component: () => import('./pages/PreviewPage.vue'),
          meta: { auth: true },
        },
      ]
    : []),
];

export default routes;
