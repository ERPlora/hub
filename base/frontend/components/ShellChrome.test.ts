import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { createAssistant, installAssistant, useAssistant } from '@erplora/ui/components';

import { flush, memoryStorage, mountBase } from '../__tests__/mount-base';
import BackgroundChrome from './BackgroundChrome.vue';
import TopbarChrome from './TopbarChrome.vue';

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
  // The bell is the shell's own (`createShell({ actionNotices })`), after this piece in the bar.
  it('the topbar: the assistant and no bell of its own, nor a live query of the bell', async () => {
    const m = await mountBase(TopbarChrome);
    expect(m.wrapper.find('[data-testid="assistant-button"]').exists()).toBe(true);
    expect(m.client.stream.subscriptions('base.bell.counters')).toEqual([]);
  });

  // The way to this business on erplora.com is at the side menu's foot, under «Upgrade plan» (ManageLink.test.ts).
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

  it('the assistant’s empty conversation is base’s: its sentence and the setup’s shortcuts', async () => {
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
