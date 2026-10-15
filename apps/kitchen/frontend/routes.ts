// Routes → pages of the kitchen app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The four sections of the old module (Display, Tickets, Stations, History) on
// the paths of the menu in apps.py, plus Settings (the old shell's settings tab). Types only: `main.ts`
// globs this file eagerly and Vite hoists that glob above the shell's boot hooks. Each page is its own
// chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  { path: '/kitchen/display', component: () => import('./pages/DisplayPage.vue'), meta: { auth: true } },
  { path: '/kitchen/tickets', component: () => import('./pages/TicketsPage.vue'), meta: { auth: true } },
  { path: '/kitchen/stations', component: () => import('./pages/StationsPage.vue'), meta: { auth: true } },
  { path: '/kitchen/history', component: () => import('./pages/HistoryPage.vue'), meta: { auth: true } },
  { path: '/kitchen/settings', component: () => import('./pages/SettingsPage.vue'), meta: { auth: true } },
];

export default routes;
