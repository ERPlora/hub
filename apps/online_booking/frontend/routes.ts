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
  // The booking page a customer opens without a session; base's public door serves its HTML on this path.
  {
    path: '/p/:slug/book',
    component: () => import('./pages/PublicBookingPage.vue'),
    meta: { auth: false, chrome: false },
  },
  // The same flow for the team, through its session, on the dev server only.
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
