// Routes → pages of the WhatsApp inbox, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The two sections of the old module (Inbox, Settings), on the paths of the
// menu in apps.py. Types only: `main.ts` globs this file eagerly and Vite hoists that glob above the
// shell's boot hooks. Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/whatsapp_inbox/inbox',
    component: () => import('./pages/InboxPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/whatsapp_inbox/settings',
    component: () => import('./pages/SettingsPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
