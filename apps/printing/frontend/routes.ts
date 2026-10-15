// Routes → pages of the printing app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The printers (with the queue's summary), the queue and the settings. Types
// only: `main.ts` globs this file eagerly and Vite hoists that glob above the shell's boot hooks. Each
// page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  { path: '/printing/printers', component: () => import('./pages/PrintersPage.vue'), meta: { auth: true } },
  { path: '/printing/jobs', component: () => import('./pages/JobsPage.vue'), meta: { auth: true } },
  { path: '/printing/settings', component: () => import('./pages/SettingsPage.vue'), meta: { auth: true } },
];

export default routes;
