// «Manage on erplora.com» at the foot of the side menu, right below «Upgrade plan» (BASE-F11; gh:hub#364, gh:hub#1400):
// this business on erplora.com's panel, where `base/spa.py` embeds its address (`hub-home`'s `manage_url`: whoever may
// open the panel, with their account, never a PIN session). It does not sell, so the installed app offers it too, in the
// system browser; its Google Play copy never does (gh:hub#1897), and nothing paints until the app says which copy it is.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { flush, mountBase } from '../__tests__/mount-base';
import { forgetAppDistribution } from '../lib/management';
import ManageLink from './ManageLink.vue';

const MANAGE_URL = 'https://erplora.com/dashboard/businesses/0192f0c4-7d2e-7c4a-9b1e-2f6a8d3c5e10';

type TauriWindow = { __TAURI__?: { core: { invoke: (command: string, args?: unknown) => Promise<unknown> } } };

function embed(block: object | null) {
  document.head.innerHTML = block
    ? `<script id="hub-home" type="application/json">${JSON.stringify(block)}</script>`
    : '';
}

/** The installed app; `device_context` answers with `context` (a promise: the test decides when). */
function installedApp(context: Promise<unknown>) {
  const invoke = vi.fn((command: string) => (command === 'device_context' ? context : Promise.resolve(undefined)));
  (window as TauriWindow).__TAURI__ = { core: { invoke } };
  return invoke;
}

const click = () => new MouseEvent('click', { bubbles: true, cancelable: true });

afterEach(() => {
  applySurface('web');
  delete (window as TauriWindow).__TAURI__;
  forgetAppDistribution();
  document.head.innerHTML = '';
});

describe('ManageLink', () => {
  it('opens this business on erplora.com’s panel in a new tab, named in full, with the external link’s icon', async () => {
    embed({ name: 'Bar', plan_url: '', manage_url: MANAGE_URL });
    const m = await mountBase(ManageLink, { locale: 'es' });
    const link = m.wrapper.get('a[data-testid="menu-manage"]');
    expect(link.text()).toBe('Gestionar en erplora.com');
    expect([link.attributes('href'), link.attributes('target'), link.attributes('rel')]).toEqual([
      MANAGE_URL,
      '_blank',
      'noopener',
    ]);
    expect(link.get('ion-icon').attributes('name')).toBe('open-outline');
    // In a browser the link itself opens the tab: its click is left alone (read as it reaches the document, then
    // stopped there, so the test's page navigates nowhere).
    let leftAlone: boolean | undefined;
    const watch = (event: Event) => {
      leftAlone = !event.defaultPrevented;
      event.preventDefault();
    };
    document.addEventListener('click', watch, { once: true });
    link.element.dispatchEvent(click());
    expect(leftAlone).toBe(true);
  });

  it("on the rail keeps only its icon, as the menu's other labels, and still says where it goes", async () => {
    embed({ name: 'Bar', manage_url: MANAGE_URL });
    const m = await mountBase(ManageLink, { locale: 'en' });
    const link = m.wrapper.get('a[data-testid="menu-manage"]');
    // polish.css hides `.nav-label` on `ion-split-pane.rail`: the text goes, the icon stays.
    expect(link.get('.nav-label').text()).toBe('Manage on erplora.com');
    expect([link.attributes('title'), link.attributes('aria-label')]).toEqual(['Manage on erplora.com', 'Manage on erplora.com']);
  });

  it('paints nothing without the address (an employee, a session opened with a PIN, no hub)', async () => {
    embed({ name: 'Bar', plan_url: 'https://erplora.com/store/plans', manage_url: '' });
    expect((await mountBase(ManageLink)).wrapper.find('[data-testid="menu-manage"]').exists()).toBe(false);
    embed(null);
    expect((await mountBase(ManageLink)).wrapper.find('[data-testid="menu-manage"]').exists()).toBe(false);
  });

  it('does not sell, so the installed app has it too, and its click opens the system browser', async () => {
    embed({ name: 'Bar', manage_url: MANAGE_URL });
    applySurface('mobile');
    const invoke = installedApp(Promise.resolve({ id: 'd1', distribution: 'direct' }));
    const m = await mountBase(ManageLink);
    await flush();
    const event = click();
    m.wrapper.get('[data-testid="menu-manage"]').element.dispatchEvent(event);
    await flush();
    expect(event.defaultPrevented).toBe(true);
    expect(invoke).toHaveBeenCalledWith('open_external_url', { url: MANAGE_URL });
  });

  it('paints nothing until the installed app says which copy it is, and never in the Google Play copy', async () => {
    embed({ name: 'Bar', manage_url: MANAGE_URL });
    applySurface('desktop');
    let answer!: (context: unknown) => void;
    installedApp(new Promise((resolve) => (answer = resolve)));
    const m = await mountBase(ManageLink);
    await flush();
    expect(m.wrapper.find('[data-testid="menu-manage"]').exists()).toBe(false);
    answer({ id: 'd1', distribution: 'msstore' });
    await flush();
    expect(m.wrapper.find('[data-testid="menu-manage"]').exists()).toBe(true);

    m.wrapper.unmount();
    forgetAppDistribution();
    installedApp(Promise.resolve({ id: 'd1', distribution: 'play' }));
    const play = await mountBase(ManageLink);
    await flush();
    expect(play.wrapper.find('[data-testid="menu-manage"]').exists()).toBe(false);
  });
});
