// base's pieces of the shell's chrome (APP-BASE-1, APP-BASE-9): at the end of the topbar, the assistant's sparkles
// then the bell, as in the old hub; beside the pane, the device's notices and the assistant's panel.
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { memoryStorage, mountBase } from '../__tests__/mount-base';
import { createAssistant, installAssistant } from '../lib/assistant';
import BackgroundChrome from './BackgroundChrome.vue';
import TopbarChrome from './TopbarChrome.vue';

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
