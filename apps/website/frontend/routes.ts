// Routes → pages of the website app, and nothing else: menu, permissions and active apps come from the server
// (`base.session.me`). Types only: `main.ts` globs this file eagerly and Vite hoists that glob above the shell's boot
// hooks, so a runtime import here would load `@ionic/vue` too early. The page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/website',
    component: () => import('./pages/WebsitePage.vue'),
    meta: { auth: true },
  },
];

export default routes;
