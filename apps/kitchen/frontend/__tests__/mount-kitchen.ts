// Test helper of the kitchen app's pages and components: `mountInShell` with its catalogues, the display and its people.
// A test that opens a popover passes `stubs: { IonPopover: PopoverStub }`.
import type { SessionMe } from '@erplora/ui/shell';
import { type Component, defineComponent } from 'vue';

import { mountInShell, type MountOptions } from '../../../../base/frontend/__tests__/mount-in-shell';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** Owner, admin or manager: `kitchen.*` (apps.py `role_permissions`), listed one by one. */
export const OWNER: SessionMe = {
  user: { id: '1', label: 'Ana' },
  permissions: [
    'kitchen.view_ticket',
    'kitchen.add_ticket',
    'kitchen.change_ticket',
    'kitchen.complete_ticket',
    'kitchen.cancel_ticket',
    'kitchen.delete_ticket',
    'kitchen.manage_station',
    'kitchen.change_settings',
    'kitchen.view_log',
    'inventory.view_product',
  ],
  menu: [],
  apps: [],
  language: 'en',
};

/** The cook and the waiter: they move states; no cancel, no delete, no stations, no settings. */
export const EMPLOYEE: SessionMe = {
  ...OWNER,
  user: { id: '2', label: 'Luis' },
  permissions: [
    'kitchen.view_ticket',
    'kitchen.add_ticket',
    'kitchen.change_ticket',
    'kitchen.complete_ticket',
    'kitchen.view_log',
    'inventory.view_product',
  ],
};

/** Who may only look at the board (no change, no serve). */
export const VIEWER: SessionMe = {
  ...OWNER,
  user: { id: '3', label: 'Eva' },
  permissions: ['kitchen.view_ticket'],
};

/** Ionic's popover as a plain box that shows its content while open (Ionic's overlay does not present in happy-dom). */
export const PopoverStub = defineComponent({
  name: 'IonPopover',
  props: { isOpen: Boolean, event: { type: null, default: undefined } },
  emits: ['didDismiss'],
  template: '<div v-if="isOpen" data-stub="ion-popover"><slot /></div>',
});

/** The words inside an element as a person reads them (Ionic's label patches its own textContent in happy-dom). */
export const said = (el: Element): string => el.innerHTML.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();

export async function mountKitchen(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, { path: '/kitchen/display', session: OWNER, messages: { en, es } });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
