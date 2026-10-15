// Routes → pages of the pricing app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The old module's one screen (the lists and the rules) on the path of the
// menu in apps.py, and a list's detail with its prices. Types only: `main.ts` globs this file eagerly and
// Vite hoists that glob above the shell's boot hooks. Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/pricing/lists',
    component: () => import('./pages/ListsPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/pricing/lists/:id',
    component: () => import('./pages/ListDetailPage.vue'),
    // Ionic keeps one view per URL and hands it its params once: no reactive route to go stale.
    props: true,
    meta: { auth: true },
  },
];

export default routes;
