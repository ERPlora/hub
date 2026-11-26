// flow: SALE-F20, KITCHEN-F18 — the send bar of «Current order»: the send icon with how many items go, named «Send
// order (N)», and the rush flame beside it; armed, the button is named «Send RUSH (N)» and the round goes urgent.
// Sending disarms the flame.
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import KitchenSendBar from './KitchenSendBar.vue';

async function setup(props: Record<string, unknown> = {}) {
  return mountSale(KitchenSendBar, { props: { pending: 2, busy: false, ...props }, locale: 'es' });
}

/** What the send button shows (how many go), what it is called and its tooltip. */
function sendButton(s: Awaited<ReturnType<typeof setup>>) {
  const button = s.find('pos-kitchen-send');
  return { shown: button.text(), name: button.attributes('aria-label'), tooltip: button.attributes('title') };
}

describe('KitchenSendBar', () => {
  it('sends the round as it is, saying how many items go', async () => {
    const s = await setup();
    expect(sendButton(s)).toEqual({ shown: '2', name: 'Enviar comanda (2)', tooltip: 'Enviar comanda (2)' });
    await click(s.find('pos-kitchen-send').element);
    expect(s.wrapper.emitted('send')).toEqual([[false]]);
  });

  it('the armed flame sends it urgent and disarms after the send', async () => {
    const s = await setup();
    const flame = s.find('pos-kitchen-rush');
    expect(flame.attributes('aria-pressed')).toBe('false');
    expect(flame.attributes('aria-label')).toBe('Marcar la comanda como urgente');
    await click(flame.element);
    expect(s.find('pos-kitchen-rush').attributes('aria-pressed')).toBe('true');
    expect(sendButton(s)).toEqual({ shown: '2', name: 'Enviar URGENTE (2)', tooltip: 'Enviar URGENTE (2)' });
    await click(s.find('pos-kitchen-send').element);
    expect(s.wrapper.emitted('send')).toEqual([[true]]);
    expect(s.find('pos-kitchen-rush').attributes('aria-pressed')).toBe('false');
  });

  it('the flame answers every tap, on and off and on again', async () => {
    const s = await setup();
    const pressed = () => s.find('pos-kitchen-rush').attributes('aria-pressed');
    for (const expected of ['true', 'false', 'true', 'false']) {
      await click(s.find('pos-kitchen-rush').element);
      expect(pressed()).toBe(expected);
    }
    expect(sendButton(s).name).toBe('Enviar comanda (2)');
  });

  it('waits while a write is on its way', async () => {
    const s = await setup({ busy: true });
    // Ionic's `disabled` is a property of the element, not an attribute.
    expect((s.find('pos-kitchen-send').element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
  });
});
