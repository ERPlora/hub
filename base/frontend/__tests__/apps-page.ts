// What the tests of the Apps screen share: its apps, its list and how a row is read and handled.
import { applySurface, toastError, toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, vi } from 'vitest';

import { app } from './app-row';
import { confirmSpy } from './apps-page-spies';
import { flush, mountBase } from './mount-base';
import { sessionChanged } from '../lib/access';
import type { AppList } from '../operations';
import AppsPage from '../pages/AppsPage.vue';

const PopoverStub = { props: { isOpen: Boolean }, template: '<div v-if="isOpen"><slot /></div>' };

export const STORE = 'https://erplora.com/store/modules?business=h1';
export const PLANS = 'https://erplora.com/store/plans?business=h1';
export const TAX = app('tax', { name: 'Taxes', required_by: ['invoice'] });
export const INVOICE = app('invoice', { name: 'Invoicing', requires: ['tax'], category: 'sales' });
export const REPORTS = app('reports', { name: 'Reports', path: null, category: 'organization', category_label: 'Organization' });
export const STOCK = app('stock', {
  name: 'Stock',
  premium: true,
  right: 'missing',
  state: 'blocked',
  path: null,
  category: 'catalog',
  category_label: 'Catalog and stock',
});
export const LIST: AppList = {
  apps: [TAX, INVOICE, REPORTS, STOCK],
  country_name: 'Spain',
  store_url: STORE,
  plan_url: PLANS,
  max_apps: null,
  enabled: 3,
};

export async function open(path = '/apps', options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(AppsPage, {
    path,
    routes: ['/apps', '/tax/home', '/invoice/home'],
    ...options,
    stubs: { ...options.stubs, IonPopover: PopoverStub },
  });
  const call = await m.live();
  return { ...m, call };
}
export type Mounted = Awaited<ReturnType<typeof open>>;

/** Each test starts on the web with every spy new, and leaves the page empty. The test file mocks the confirmation,
 *  the toasts and the session's refresh (`apps-page-spies.ts`, `toast-spies.ts`). */
export function freshEachTest(): void {
  beforeEach(() => {
    applySurface('web');
    confirmSpy.mockReset();
    vi.mocked(toastSuccess).mockClear();
    vi.mocked(toastError).mockClear();
    vi.mocked(sessionChanged).mockClear();
  });
  afterEach(() => {
    document.body.innerHTML = '';
  });
}

export const ids = (m: Mounted) => m.wrapper.findAll('[data-testid="apps-row"]').map((row) => row.attributes('data-id'));
export const rowOf = (m: Mounted, id: string) => m.wrapper.find(`[data-testid="apps-row"][data-id="${id}"]`);

type Toggle = HTMLElement & { checked?: boolean; disabled?: boolean };
/** The switch that turns the app on or off, as Ionic holds it. */
export const switchOf = (m: Mounted, id: string) => rowOf(m, id).find('ion-toggle');
export const switchState = (m: Mounted, id: string) => {
  const el = switchOf(m, id).element as Toggle;
  return { checked: el.checked, disabled: el.disabled, label: el.getAttribute('aria-label') };
};
/** Whoever runs the business flips the switch: Ionic moves it, then tells. Nothing is awaited, for a test that runs
 *  the clock itself. */
export function flipNow(m: Mounted, id: string, checked: boolean): void {
  const el = switchOf(m, id).element as Toggle;
  el.checked = checked;
  el.dispatchEvent(new CustomEvent('ionChange', { detail: { checked } }));
}
/** The switch flipped, and what it asked for answered. */
export async function flip(m: Mounted, id: string, checked: boolean): Promise<void> {
  flipNow(m, id, checked);
  await flush();
}
/** Why the row's switch cannot change, or what went wrong, under its state. */
export const noteOf = (m: Mounted, id: string) => rowOf(m, id).find('.data-table__cell-note, .data-table__card-note');

/** Presses a row action, on its button or, when it lives in «⋮», in the menu. */
export async function pressAppAction(m: Mounted, id: string, action: string): Promise<void> {
  const hook = `apps-row-${id}-${action}`;
  const direct = m.wrapper.find(`ion-button[data-testid="${hook}"]`);
  if (direct.exists()) {
    await direct.trigger('click');
    await flush();
    return;
  }
  await rowOf(m, id).find(`[data-testid="apps-row-${id}-menu"]`).trigger('click');
  await flush();
  await m.wrapper.find(`.data-table__row-menu [data-testid="${hook}"]`).trigger('click');
  await flush();
}

/** The label of a row action, on its button (its title: Ionic moves `aria-label` inside) or in the menu; nothing
 *  when the row does not offer it. */
export async function appActionLabel(m: Mounted, id: string, action: string): Promise<string | undefined> {
  const hook = `apps-row-${id}-${action}`;
  const direct = m.wrapper.find(`ion-button[data-testid="${hook}"]`);
  if (direct.exists()) return direct.attributes('title');
  const menu = rowOf(m, id).find(`[data-testid="apps-row-${id}-menu"]`);
  if (!menu.exists()) return undefined;
  await menu.trigger('click');
  await flush();
  const item = m.wrapper.find(`.data-table__row-menu [data-testid="${hook}"] ion-label`);
  // Stencil keeps the label's text behind a comment node of its own.
  return item.exists() ? item.element.innerHTML.replace(/<!--.*?-->/g, '').trim() : undefined;
}
