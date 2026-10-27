// base's pieces of the shell's chrome (APP-BASE-1, APP-BASE-9): at the end of the topbar, «erplora.com» (BASE-F11),
// the assistant's sparkles then the bell, as in the old hub — on a phone (under 768 px) folded into one «More
// options», as the old hub did so that they never push the centred title; beside the pane, the device's notices, the
// assistant's panel and the business's apps followed live (AppsFollower).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { BellCounter } from '../operations';
import { accessibleName, flush, memoryStorage, mountBase } from '../__tests__/mount-base';
import { createAssistant, installAssistant, useAssistant } from '../lib/assistant';
import { forgetAppDistribution } from '../lib/management';
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
  delete (window as TauriWindow).__TAURI__;
  forgetAppDistribution();
});

type TauriWindow = { __TAURI__?: { core: { invoke: (command: string, args?: unknown) => Promise<unknown> } } };
type Link = HTMLElement & { href?: string; target?: string; rel?: string };

/** This business on erplora.com's panel, as `base/spa.py` embeds it for who may open it (`manage_url`). */
const MANAGE = 'https://erplora.com/dashboard/businesses/0192f0c4-7d2e-7c4a-9b1e-2f6a8d3c5e10';

function embedHome(manageUrl: string): void {
  const block = document.createElement('script');
  block.id = 'hub-home';
  block.type = 'application/json';
  block.textContent = JSON.stringify({ name: 'Bar', plan_url: '', account_url: '', manage_url: manageUrl });
  document.body.append(block);
}

/** The installed app, from `distribution` (`device_context`); its `invoke` to look at. */
function installedApp(distribution: string) {
  const invoke = vi.fn(async (command: string) => (command === 'device_context' ? { id: 'd1', distribution } : undefined));
  (window as TauriWindow).__TAURI__ = { core: { invoke } };
  return invoke;
}

describe('the chrome of base', () => {
  // gh:hub#38: the topbar's parity with the old shell: the assistant's sparkles and the bell at its end.
  it('the topbar: the assistant, then the bell', async () => {
    const { wrapper } = await mountBase(TopbarChrome);
    const order = [...wrapper.element.parentElement!.querySelectorAll('[data-testid="assistant-button"], [data-testid="hub-bell"]')];
    expect(order.map((element) => element.getAttribute('data-testid'))).toEqual(['assistant-button', 'hub-bell']);
  });

  // BASE-F11 (gh:hub#364, gh:hub#1400): the way to this business on erplora.com, first of base's piece and labelled.
  it('«erplora.com» first, a link to the business on erplora.com in a new tab, named in full', async () => {
    embedHome(MANAGE);
    const { wrapper } = await mountBase(TopbarChrome, { locale: 'es' });
    const order = [...wrapper.element.parentElement!.querySelectorAll('[data-testid="topbar-manage"], [data-testid="assistant-button"], [data-testid="hub-bell"]')];
    expect(order.map((element) => element.getAttribute('data-testid'))).toEqual(['topbar-manage', 'assistant-button', 'hub-bell']);
    const manage = wrapper.get('[data-testid="topbar-manage"]').element as Link;
    expect([manage.href, manage.target, manage.rel]).toEqual([MANAGE, '_blank', 'noopener']);
    // The word on the bar is the brand alone (Stencil patches a scoped label's textContent: its markup, then).
    expect(manage.querySelector('ion-label')?.innerHTML.replace(/<!--.*?-->/g, '').trim()).toBe('erplora.com');
    expect(accessibleName(manage)).toBe('Gestionar en erplora.com');
    const click = new MouseEvent('click', { bubbles: true, cancelable: true });
    manage.dispatchEvent(click);
    expect(click.defaultPrevented).toBe(false);
  });

  it('without an address (an employee, a session opened with a PIN, no hub) there is none', async () => {
    embedHome('');
    expect((await mountBase(TopbarChrome)).wrapper.find('[data-testid="topbar-manage"]').exists()).toBe(false);
    document.body.innerHTML = '';
    expect((await mountBase(TopbarChrome)).wrapper.find('[data-testid="topbar-manage"]').exists()).toBe(false);
  });

  it('in the installed app it opens the system browser; in its Google Play copy there is none (gh:hub#1897)', async () => {
    embedHome(MANAGE);
    const invoke = installedApp('direct');
    const m = await mountBase(TopbarChrome);
    await flush();
    const click = new MouseEvent('click', { bubbles: true, cancelable: true });
    m.wrapper.get('[data-testid="topbar-manage"]').element.dispatchEvent(click);
    await flush();
    expect(click.defaultPrevented).toBe(true);
    expect(invoke).toHaveBeenCalledWith('open_external_url', { url: MANAGE });

    m.wrapper.unmount();
    forgetAppDistribution();
    installedApp('play');
    const play = await mountBase(TopbarChrome);
    await flush();
    expect(play.wrapper.find('[data-testid="topbar-manage"]').exists()).toBe(false);
  });

  it('beside the pane: the device notices and the assistant’s panel', async () => {
    const { wrapper } = await mountBase(BackgroundChrome);
    expect(wrapper.find('[data-testid="device-notices"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="assistant-panel"]').exists()).toBe(true);
  });

  it('beside the pane, the business’s apps followed live: the menu follows an app turned on or off (PLAN-HUB §9)', async () => {
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

  it('«erplora.com» is the first row of «More options», named in full, and choosing it closes the menu', async () => {
    embedHome(MANAGE);
    const m = await mountBase(TopbarChrome, { locale: 'es' });
    expect(m.wrapper.find('[data-testid="topbar-manage"]').exists()).toBe(false);
    await m.wrapper.get('[data-testid="topbar-chrome-more"]').trigger('click');
    await flush();
    const rows = [...document.querySelectorAll('[data-testid^="topbar-chrome-more-"]')].filter((row) => row.tagName === 'ION-ITEM');
    expect(rows.map((row) => row.getAttribute('data-testid'))).toEqual([
      'topbar-chrome-more-manage', 'topbar-chrome-more-assistant', 'topbar-chrome-more-bell',
    ]);
    const row = inDoc('topbar-chrome-more-manage') as Link;
    expect([row.href, row.target, row.rel]).toEqual([MANAGE, '_blank', 'noopener']);
    expect(row.querySelector('ion-label')?.textContent?.trim()).toBe('Gestionar en erplora.com');
    row.click();
    await flush();
    expect(inDoc('topbar-chrome-more-manage')).toBeNull();
  });

  it('in the Google Play copy, «More options» has no «erplora.com»', async () => {
    embedHome(MANAGE);
    installedApp('play');
    const m = await mountBase(TopbarChrome);
    await flush();
    await m.wrapper.get('[data-testid="topbar-chrome-more"]').trigger('click');
    await flush();
    expect(inDoc('topbar-chrome-more-assistant')).not.toBeNull();
    expect(inDoc('topbar-chrome-more-manage')).toBeNull();
  });

  it('with nothing in the bell, the button has no count', async () => {
    const m = await mountBase(TopbarChrome);
    await m.result(await m.live(), 'base.bell.counters', { counters: [] });
    expect(m.wrapper.find('[data-testid="topbar-chrome-more-badge"]').exists()).toBe(false);
  });
});
