// Routes → pages of the tips app, and nothing else: menu, permissions and active apps come from the server
// (`base.session.me`). Types only: `main.ts` globs this file eagerly and Vite hoists that glob above the shell's boot
// hooks. Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/tip/tips',
    component: () => import('./pages/TipsPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/tip/settings',
    component: () => import('./pages/SettingsPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
