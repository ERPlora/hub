// BASE-G110: the sparkles «Assistant» in the topbar opens and closes the panel and says which; only to a person who
// may use it (the assistant answers to whoever sees the Home: `base.view_home`).
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { accessibleName, flush, memoryStorage, mountBase, OWNER } from '../../__tests__/mount-base';
import { type Assistant, createAssistant, installAssistant } from '../../lib/assistant';
import AssistantButton from './AssistantButton.vue';

let assistant: Assistant;

/** Attached, `ion-button` moves its `aria-*` to the native button of its shadow root, as in a browser, and follows
 *  only `aria-checked`, `aria-label` and `aria-pressed` afterwards: a toggle says its state with `aria-pressed`. */
const pressed = (element: Element) =>
  element.shadowRoot?.querySelector('button')?.getAttribute('aria-pressed') ?? element.getAttribute('aria-pressed');

beforeEach(() => {
  assistant = createAssistant({ storage: memoryStorage(), openStorage: memoryStorage(), post: async () => undefined });
  installAssistant(assistant);
});

afterEach(() => {
  installAssistant(undefined);
  document.body.innerHTML = '';
});

describe('AssistantButton', () => {
  it('opens and closes the panel, named «Asistente», pressed while it is open', async () => {
    const { wrapper } = await mountBase(AssistantButton, { locale: 'es' });
    const button = wrapper.get('[data-testid="assistant-button"]');
    expect(accessibleName(button.element)).toBe('Asistente');
    expect(pressed(button.element)).toBe('false');
    await button.trigger('click');
    await flush();
    expect(assistant.state.open).toBe(true);
    expect(pressed(wrapper.get('[data-testid="assistant-button"]').element)).toBe('true');
    await wrapper.get('[data-testid="assistant-button"]').trigger('click');
    expect(assistant.state.open).toBe(false);
  });

  it('not there for a person who cannot use the assistant', async () => {
    const { wrapper } = await mountBase(AssistantButton, { session: { ...OWNER, permissions: ['demo.view'] } });
    expect(wrapper.find('[data-testid="assistant-button"]').exists()).toBe(false);
  });
});
