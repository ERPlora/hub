// Routes → pages of the combo app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). One menu entry, as the old module: Menus, whose rows open the builder of
// one menu. Types only: `main.ts` globs this file eagerly and Vite hoists that glob above the shell's
// boot hooks. Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/combo/menus',
    component: () => import('./pages/MenusPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/combo/menus/:id',
    component: () => import('./pages/MenuBuilderPage.vue'),
    // Ionic keeps one view per URL and hands it its params once: no reactive route to go stale.
    props: true,
    meta: { auth: true },
  },
];

export default routes;
