// Routes → pages of the flow app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The list with the drafts and the gallery (`?template=` opens a card), a
// new automation (`?draft=` reviews the assistant's), a saved one (`?tab=`) and the guide. Types only:
// `main.ts` globs this file eagerly and Vite hoists that glob above the shell's boot hooks. Each page is
// its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/flow/automations',
    component: () => import('./pages/AutomationsPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/flow/automations/new',
    component: () => import('./pages/NewFlowPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/flow/automations/:id',
    component: () => import('./pages/FlowEditorPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/flow/guide',
    component: () => import('./pages/GuidePage.vue'),
    meta: { auth: true },
  },
];

export default routes;
