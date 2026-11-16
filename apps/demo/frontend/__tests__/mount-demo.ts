// Test helper of the demo's pages and components: `mountInShell` with the demo catalogues, the items, its people and
// a test double of ion-alert. Pages are mounted as the shell would.
import type { SessionMe } from '@erplora/ui/shell';
import { type Component, defineComponent, h } from 'vue';

import { mountInShell } from '../../../../base/frontend/__tests__/mount-in-shell';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** `ion-alert` presents itself only in a real browser: the stub exposes what it would show. */
export const AlertStub = defineComponent({
  name: 'IonAlert',
  props: { isOpen: Boolean, header: { type: String, default: undefined }, buttons: { type: Array, default: () => [] } },
  emits: ['didDismiss'],
  setup(props) {
    return () => (props.isOpen ? h('div', { 'data-testid': 'alert' }, props.header) : null);
  },
});

export const MANAGER: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: ['demo.view', 'demo.manage'],
  menu: [],
  apps: [],
  language: 'en',
};

export const EMPLOYEE: SessionMe = { ...MANAGER, permissions: ['demo.view'] };

export interface MountOptions {
  props?: Record<string, unknown>;
  path?: string;
  locale?: 'en' | 'es';
  session?: SessionMe;
  stubs?: Record<string, unknown>;
}

export async function mountDemo(component: Component, options: MountOptions = {}) {
  const stubs = { IonAlert: AlertStub, ...options.stubs };
  const mounted = await mountInShell(component, { ...options, stubs }, { path: '/demo/items', session: MANAGER, messages: { en, es } });
  return { ...mounted, result: mounted.resultOn };
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
