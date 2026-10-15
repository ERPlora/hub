// Routes → pages of the task app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The two sections of the old module (Tasks, Projects) on the paths of the
// menu in apps.py. Types only: `main.ts` globs this file eagerly and Vite hoists that glob above the
// shell's boot hooks. Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/task/tasks',
    component: () => import('./pages/TasksPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/task/projects',
    component: () => import('./pages/ProjectsPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
