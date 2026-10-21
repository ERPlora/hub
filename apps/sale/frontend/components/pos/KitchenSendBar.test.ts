// flow: SALE-F20, KITCHEN-F18 — the send bar of «Current order»: «Send order» with how many items go, and the
// rush flame beside it; armed, the button says «Send RUSH» and the round goes urgent. Sending disarms the flame.
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import KitchenSendBar from './KitchenSendBar.vue';

async function setup(props: Record<string, unknown> = {}) {
  return mountSale(KitchenSendBar, { props: { pending: 2, busy: false, ...props }, locale: 'es' });
}

describe('KitchenSendBar', () => {
  it('sends the round as it is, saying how many items go', async () => {
    const s = await setup();
    expect(s.find('pos-kitchen-send').text()).toContain('Enviar comanda (2)');
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
    expect(s.find('pos-kitchen-send').text()).toContain('Enviar URGENTE (2)');
    await click(s.find('pos-kitchen-send').element);
    expect(s.wrapper.emitted('send')).toEqual([[true]]);
    expect(s.find('pos-kitchen-rush').attributes('aria-pressed')).toBe('false');
  });

  it('the flame answers every tap, on and off and on again (kitchen#88)', async () => {
    const s = await setup();
    const pressed = () => s.find('pos-kitchen-rush').attributes('aria-pressed');
    for (const expected of ['true', 'false', 'true', 'false']) {
      await click(s.find('pos-kitchen-rush').element);
      expect(pressed()).toBe(expected);
    }
    expect(s.find('pos-kitchen-send').text()).toContain('Enviar comanda (2)');
  });

  it('waits while a write is on its way', async () => {
    const s = await setup({ busy: true });
    // Ionic's `disabled` is a property of the element, not an attribute.
    expect((s.find('pos-kitchen-send').element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
  });
});
