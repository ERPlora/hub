// base's pieces of the shell's chrome: at the end of the topbar, the assistant's sparkles then
// the bell, as in the old hub — on a phone (under 768 px) folded into one «More options», as the old hub did so that
// they never push the centred title; beside the pane, the device's notices, the assistant's panel and the business's
// apps followed live (AppsFollower). «Manage on erplora.com» (BASE-F11) is at the side menu's foot (ManageLink.test.ts).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createAssistant, installAssistant, useAssistant } from '@erplora/ui/components';

import type { BellCounter } from '../operations';
import { accessibleName, flush, memoryStorage, mountBase } from '../__tests__/mount-base';
import BackgroundChrome from './BackgroundChrome.vue';
import TopbarChrome from './TopbarChrome.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonPopover: IonModalStub };
});

beforeEach(() => {
  installAssistant(createAssistant({ storage: memoryStorage(), openStorage: memoryStorage(), post: async () => undefined }));
});

afterEach(() => {
  installAssistant(undefined);
  document.body.innerHTML = '';
});

/** This business on erplora.com's panel, as `base/spa.py` embeds it for who may open it (`manage_url`). */
const MANAGE = 'https://erplora.com/dashboard/businesses/0192f0c4-7d2e-7c4a-9b1e-2f6a8d3c5e10';

function embedHome(manageUrl: string): void {
  const block = document.createElement('script');
  block.id = 'hub-home';
  block.type = 'application/json';
  block.textContent = JSON.stringify({ name: 'Bar', plan_url: '', account_url: '', manage_url: manageUrl });
  document.body.append(block);
}

describe('the chrome of base', () => {
  // gh:hub#38: the topbar's parity with the old shell: the assistant's sparkles and the bell at its end.
  it('the topbar: the assistant, then the bell', async () => {
    const { wrapper } = await mountBase(TopbarChrome);
    const order = [...wrapper.element.parentElement!.querySelectorAll('[data-testid="assistant-button"], [data-testid="hub-bell"]')];
    expect(order.map((element) => element.getAttribute('data-testid'))).toEqual(['assistant-button', 'hub-bell']);
  });

  // BASE-F11: the way to this business on erplora.com left the bar for the side menu's foot, under «Upgrade plan».
  it('the bar has no «erplora.com», even for who may open the panel', async () => {
    embedHome(MANAGE);
    const { wrapper } = await mountBase(TopbarChrome, { locale: 'es' });
    expect(wrapper.find('[data-testid="assistant-button"]').exists()).toBe(true);
    // Neither a link to the panel (ion-button and ion-item carry `href` as a property) nor the brand's word or name.
    const links = wrapper.findAll('*').filter((node) => (node.element as HTMLElement & { href?: string }).href === MANAGE);
    expect(links.map((node) => node.element.tagName)).toEqual([]);
    expect(wrapper.html()).not.toContain('erplora.com');
  });

  it('beside the pane: the device notices and the assistant’s panel', async () => {
    const { wrapper } = await mountBase(BackgroundChrome);
    expect(wrapper.find('[data-testid="device-notices"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="assistant-panel"]').exists()).toBe(true);
  });

  it('the assistant’s empty conversation is base’s: its sentence and the setup’s shortcuts (BASE-G121)', async () => {
    const { wrapper } = await mountBase(BackgroundChrome, { locale: 'es' });
    useAssistant().setOpen(true);
    for (let i = 0; i < 3; i += 1) await flush();
    const empty = wrapper.get('[data-testid="assistant-empty"]');
    expect(empty.text()).toContain('Pregúntame por tus ventas, tu inventario o cualquier cosa de tu negocio.');
    expect(empty.findAll('[data-testid="assistant-shortcut"]').map((button) => button.text())).toEqual(['¿Qué falta por configurar?']);
  });

  it('beside the pane, the business’s apps followed live: the menu follows an app turned on or off', async () => {
    const m = await mountBase(BackgroundChrome);
    await m.live();
    expect(m.client.stream.subscriptions('base.app.list').map((sub) => sub.params)).toEqual([{}]);
  });
});

describe('the topbar on a phone (under 768 px): one «More options», as in the old hub', () => {
  const counter = (count: number): BellCounter => ({
    key: 'base.failed_events', app: 'base', count, route: '/system#events', label: 'Failed events', icon: 'ion:warning-outline',
  });
  const inDoc = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);

  beforeEach(() => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: query === '(max-width: 767px)', addEventListener() {}, removeEventListener() {},
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('folds the sparkles and the bell into one button that carries the bell’s count', async () => {
    const m = await mountBase(TopbarChrome, { locale: 'es' });
    await m.result(await m.live(), 'base.bell.counters', { counters: [counter(2)] });
    expect(m.wrapper.find('[data-testid="assistant-button"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="hub-bell"]').exists()).toBe(false);
    const more = m.wrapper.get('[data-testid="topbar-chrome-more"]');
    expect(accessibleName(more.element)).toBe('Más opciones');
    expect(m.wrapper.get('[data-testid="topbar-chrome-more-badge"]').text()).toBe('2');
  });

  it('«Assistant» opens the panel and closes the menu; «Notifications» opens the bell’s list', async () => {
    const m = await mountBase(TopbarChrome);
    await m.result(await m.live(), 'base.bell.counters', { counters: [counter(3)] });
    await m.wrapper.get('[data-testid="topbar-chrome-more"]').trigger('click');
    await flush();
    expect(inDoc('topbar-chrome-more-assistant')?.textContent?.trim()).toBe('Assistant');
    expect(inDoc('topbar-chrome-more-bell')?.querySelector('ion-label')?.textContent?.trim()).toBe('Notifications');
    expect(inDoc('topbar-chrome-more-bell')?.querySelector('ion-badge')?.textContent?.trim()).toBe('3');
    inDoc('topbar-chrome-more-assistant')!.click();
    await flush();
    expect(useAssistant().state.open).toBe(true);
    expect(inDoc('topbar-chrome-more-assistant')).toBeNull();

    await m.wrapper.get('[data-testid="topbar-chrome-more"]').trigger('click');
    await flush();
    inDoc('topbar-chrome-more-bell')!.click();
    await flush();
    expect(inDoc('topbar-chrome-more-bell')).toBeNull();
    expect([...document.querySelectorAll('[data-testid="hub-bell-row"]')]).toHaveLength(1);
  });

  it('«More options» has the assistant and the bell, and no «erplora.com» (it is at the side menu’s foot)', async () => {
    embedHome(MANAGE);
    const m = await mountBase(TopbarChrome, { locale: 'es' });
    await m.wrapper.get('[data-testid="topbar-chrome-more"]').trigger('click');
    await flush();
    const rows = [...document.querySelectorAll('[data-testid^="topbar-chrome-more-"]')].filter((row) => row.tagName === 'ION-ITEM');
    expect(rows.map((row) => row.getAttribute('data-testid'))).toEqual(['topbar-chrome-more-assistant', 'topbar-chrome-more-bell']);
    expect(document.querySelector(`[href="${MANAGE}"]`)).toBeNull();
  });

  it('with nothing in the bell, the button has no count', async () => {
    const m = await mountBase(TopbarChrome);
    await m.result(await m.live(), 'base.bell.counters', { counters: [] });
    expect(m.wrapper.find('[data-testid="topbar-chrome-more-badge"]').exists()).toBe(false);
  });
});
