// base's pieces of the shell's chrome (APP-BASE-1, APP-BASE-9): at the end of the topbar, the assistant's sparkles
// then the bell, as in the old hub — on a phone (under 768 px) folded into one «More options», as the old hub did so
// that they never push the centred title; beside the pane, the device's notices and the assistant's panel.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { BellCounter } from '../operations';
import { accessibleName, flush, memoryStorage, mountBase } from '../__tests__/mount-base';
import { createAssistant, installAssistant, useAssistant } from '../lib/assistant';
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

describe('the chrome of base', () => {
  it('the topbar: the assistant, then the bell', async () => {
    const { wrapper } = await mountBase(TopbarChrome);
    const order = [...wrapper.element.parentElement!.querySelectorAll('[data-testid="assistant-button"], [data-testid="hub-bell"]')];
    expect(order.map((element) => element.getAttribute('data-testid'))).toEqual(['assistant-button', 'hub-bell']);
  });

  it('beside the pane: the device notices and the assistant’s panel', async () => {
    const { wrapper } = await mountBase(BackgroundChrome);
    expect(wrapper.find('[data-testid="device-notices"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="assistant-panel"]').exists()).toBe(true);
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

  it('with nothing in the bell, the button has no count', async () => {
    const m = await mountBase(TopbarChrome);
    await m.result(await m.live(), 'base.bell.counters', { counters: [] });
    expect(m.wrapper.find('[data-testid="topbar-chrome-more-badge"]').exists()).toBe(false);
  });
});
