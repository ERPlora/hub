// Routes → pages of the printing app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The printers (with the queue's summary), the devices that print, the queue and
// the settings; and its piece beside the pane, the print host (PRINTING-F18): a background route, which the shell
// keeps out of the router and mounts on every screen while a person is signed in. Types
// only: `main.ts` globs this file eagerly and Vite hoists that glob above the shell's boot hooks. Each
// page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  { path: '/printing/printers', component: () => import('./pages/PrintersPage.vue'), meta: { auth: true } },
  { path: '/printing/devices', component: () => import('./pages/DevicesPage.vue'), meta: { auth: true } },
  { path: '/printing/jobs', component: () => import('./pages/JobsPage.vue'), meta: { auth: true } },
  { path: '/printing/settings', component: () => import('./pages/SettingsPage.vue'), meta: { auth: true } },
  {
    path: '/printing/print-host',
    component: () => import('./components/PrintHost.vue'),
    meta: { auth: true, background: true },
  },
];

export default routes;
