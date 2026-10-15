// Routes → pages of the cash register app, and nothing else: menu, permissions and active apps come from
// the server (`base.session.me`). The drawer's sessions, the detail of one (CASH_REGISTER-F11, pushed on
// the stack with its Back) and the settings. Types only: `main.ts` globs this file eagerly and Vite hoists
// that glob above the shell's boot hooks. Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/cash_register/sessions',
    component: () => import('./pages/SessionsPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/cash_register/sessions/:id',
    component: () => import('./pages/SessionDetailPage.vue'),
    // Ionic keeps one view per URL and hands it its params once: no reactive route to go stale.
    props: true,
    meta: { auth: true },
  },
  {
    path: '/cash_register/settings',
    component: () => import('./pages/SettingsPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
