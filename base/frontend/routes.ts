// Routes → pages of base, and nothing else: the Home at `/` (PLAN-HUB round 2026-10-21, the old hub's
// dashboard). Registered before the shell's grid, so it wins `/`; named apart from it (`home`), because a
// second route with the same name would replace the first. Types only: `main.ts` globs this file eagerly.
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'base-home',
    component: () => import('./pages/HomePage.vue'),
    meta: { auth: true },
  },
];

export default routes;
