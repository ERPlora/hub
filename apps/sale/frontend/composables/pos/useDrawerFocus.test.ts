// The phone's cart drawer is a dialog over the till: opening it moves the focus inside, Tab and
// Shift+Tab go round inside it, and closing it gives the focus back to the button that opened it.
import { mount } from '@vue/test-utils';
import { afterEach, describe, expect, it } from 'vitest';
import { defineComponent, h, nextTick, shallowRef } from 'vue';

import { useDrawerFocus } from './useDrawerFocus';

afterEach(() => {
  document.body.innerHTML = '';
});

function setup(active = true) {
  const open = shallowRef(false);
  const enabled = shallowRef(active);
  const Probe = defineComponent({
    setup() {
      const drawer = shallowRef<HTMLElement | null>(null);
      const opener = shallowRef<HTMLElement | null>(null);
      const { onKeydown } = useDrawerFocus({ container: drawer, open, enabled, returnTo: () => opener.value });
      return () =>
        h('div', [
          h('button', { ref: (el) => (opener.value = el as HTMLElement), 'data-testid': 'fab' }, 'cart'),
          h('div', { ref: (el) => (drawer.value = el as HTMLElement), tabindex: -1, onKeydown, 'data-testid': 'drawer' }, [
            h('button', { 'data-testid': 'first' }, 'park'),
            h('button', { disabled: true }, 'off'),
            h('input', { 'data-testid': 'middle' }),
            h('button', { 'data-testid': 'last' }, 'charge'),
          ]),
        ]);
    },
  });
  const wrapper = mount(Probe, { attachTo: document.body });
  const el = (id: string) => wrapper.find(`[data-testid="${id}"]`).element as HTMLElement;
  const tab = (shift = false) => {
    const event = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: shift, bubbles: true, cancelable: true });
    (document.activeElement ?? document.body).dispatchEvent(event);
    return event;
  };
  return { open, enabled, el, tab };
}

describe('useDrawerFocus', () => {
  it('opening moves the focus to the first thing inside the drawer', async () => {
    const s = setup();
    s.el('fab').focus();
    s.open.value = true;
    await nextTick();
    await nextTick();
    expect(document.activeElement).toBe(s.el('first'));
  });

  it('Tab from the last goes round to the first, Shift+Tab from the first to the last', async () => {
    const s = setup();
    s.open.value = true;
    await nextTick();
    await nextTick();
    s.el('last').focus();
    expect(s.tab().defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(s.el('first'));
    expect(s.tab(true).defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(s.el('last'));
    s.el('middle').focus();
    expect(s.tab().defaultPrevented).toBe(false);
  });

  it('closing gives the focus back to the button that opened it', async () => {
    const s = setup();
    s.el('fab').focus();
    s.open.value = true;
    await nextTick();
    await nextTick();
    s.open.value = false;
    await nextTick();
    expect(document.activeElement).toBe(s.el('fab'));
  });

  it('does nothing where the cart is not a drawer (a tablet or a desktop)', async () => {
    const s = setup(false);
    s.el('fab').focus();
    s.open.value = true;
    await nextTick();
    await nextTick();
    expect(document.activeElement).toBe(s.el('fab'));
    s.el('last').focus();
    expect(s.tab().defaultPrevented).toBe(false);
  });
});
