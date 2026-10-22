// Routes → pages of the staff app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The four sections of the old module (Staff, Roles, Time Off, Schedules)
// on the paths of the menu in apps.py, plus Commissions (STAFF-F21) and Settings (the old shell's
// settings tab). Types only:
// `main.ts` globs this file eagerly and Vite hoists that glob above the shell's boot hooks. Each page
// is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/staff/members',
    component: () => import('./pages/MembersPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/staff/roles',
    component: () => import('./pages/RolesPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/staff/time-off',
    component: () => import('./pages/TimeOffPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/staff/schedules',
    component: () => import('./pages/SchedulesPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/staff/commissions',
    component: () => import('./pages/CommissionsPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/staff/settings',
    component: () => import('./pages/SettingsPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
