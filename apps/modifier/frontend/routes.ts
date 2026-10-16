// Routes → pages of the modifier app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The old module's single section (Modifiers), on the path of the menu in
// apps.py; a group's options and what it applies to open in its sheet, over the same page. Types only:
// `main.ts` globs this file eagerly and Vite hoists that glob above the shell's boot hooks. The page is
// its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/modifier/groups',
    component: () => import('./pages/GroupsPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
