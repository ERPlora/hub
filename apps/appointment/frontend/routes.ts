// Routes → pages of the appointment app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The Agenda (the old module's single entry: List, By professional and
// Repeating) on the path of the menu in apps.py, plus Settings (the old shell's settings tab). Types
// only: `main.ts` globs this file eagerly and Vite hoists that glob above the shell's boot hooks. Each
// page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/appointment/agenda',
    component: () => import('./pages/AgendaPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/appointment/settings',
    component: () => import('./pages/SettingsPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
