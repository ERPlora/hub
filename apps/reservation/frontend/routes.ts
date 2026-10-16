// Routes → pages of the reservation app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The three sections of the old module (Reservations, Waitlist, Availability) on
// the paths of the menu in apps.py, plus Settings (a tab of the pages, for whoever may save them). Types
// only: `main.ts` globs this file eagerly and Vite hoists that glob above the shell's boot hooks. Each page
// is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/reservation/reservations',
    component: () => import('./pages/ReservationsPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/reservation/waitlist',
    component: () => import('./pages/WaitlistPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/reservation/availability',
    component: () => import('./pages/AvailabilityPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/reservation/settings',
    component: () => import('./pages/SettingsPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
