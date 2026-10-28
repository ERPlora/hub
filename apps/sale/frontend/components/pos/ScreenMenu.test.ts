// The ⋮ screen menu at the end of the category strip (WORKBOOK «Vender»): «Full screen» / «Exit full
// screen», the browser's own, for the whole page (the sheets live in the app's root); not there at all
// where the device cannot do it. Android's Back on the installed app closes it, as Escape does (base's `erplora:back`).
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SHELL_BACK_EVENT } from '../../../../../base/frontend/lib/system-back';
import { click, mountSale } from '../../__tests__/mount-sale';
import ScreenMenu from './ScreenMenu.vue';

const screen = vi.hoisted(() => ({
  capable: true,
  active: false,
  listeners: [] as Array<() => void>,
  toggle: vi.fn(() => Promise.resolve()),
}));

vi.mock('../../lib/fullscreen', () => ({
  isCapable: () => screen.capable,
  isActive: () => screen.active,
  toggle: screen.toggle,
  onChange: (listener: () => void) => {
    screen.listeners.push(listener);
    return () => (screen.listeners = screen.listeners.filter((l) => l !== listener));
  },
}));

/** One press of the system Back, as the shell asks: `true` when the app took it. */
function pressBack(): boolean {
  const ask = new CustomEvent(SHELL_BACK_EVENT, { cancelable: true });
  window.dispatchEvent(ask);
  return ask.defaultPrevented;
}

beforeEach(() => {
  screen.capable = true;
  screen.active = false;
  screen.listeners = [];
  screen.toggle.mockClear();
});

describe('ScreenMenu', () => {
  it('is not painted where the device cannot go full screen', async () => {
    screen.capable = false;
    const m = await mountSale(ScreenMenu, {});
    expect(m.find('pos-screen-menu').exists()).toBe(false);
  });

  it('⋮ opens the menu with «Full screen», which asks the browser for the page and closes the menu', async () => {
    const m = await mountSale(ScreenMenu, { locale: 'es' });
    const trigger = m.find('pos-screen-menu');
    expect(trigger.attributes('aria-label')).toBe('Pantalla');
    expect(trigger.attributes('aria-expanded')).toBe('false');
    await click(trigger.element);
    expect(trigger.attributes('aria-expanded')).toBe('true');
    const item = m.find('pos-fullscreen');
    expect(item.text()).toBe('Pantalla completa');
    await click(item.element);
    expect(screen.toggle).toHaveBeenCalledExactlyOnceWith();
    expect(m.find('pos-fullscreen').exists()).toBe(false);
  });

  it('follows the real state (Esc and F11 included): on full screen the item says «Exit full screen»', async () => {
    const m = await mountSale(ScreenMenu, {});
    screen.active = true;
    screen.listeners.forEach((listener) => listener());
    await click(m.find('pos-screen-menu').element);
    expect(m.find('pos-fullscreen').text()).toBe('Exit full screen');
  });

  it('closes on a tap outside and on Escape', async () => {
    const m = await mountSale(ScreenMenu, {});
    await click(m.find('pos-screen-menu').element);
    await click(m.find('pos-screen-menu-scrim').element);
    expect(m.find('pos-fullscreen').exists()).toBe(false);
    await click(m.find('pos-screen-menu').element);
    m.find('pos-screen-menu-list').element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await m.wrapper.vm.$nextTick();
    expect(m.find('pos-fullscreen').exists()).toBe(false);
  });

  it('Android’s Back closes the open menu and the till stays; with the menu closed Back is the shell’s', async () => {
    const m = await mountSale(ScreenMenu, {});
    expect(pressBack()).toBe(false);
    await click(m.find('pos-screen-menu').element);
    expect(pressBack()).toBe(true);
    await m.wrapper.vm.$nextTick();
    expect(m.find('pos-fullscreen').exists()).toBe(false);
    expect(m.find('pos-screen-menu').attributes('aria-expanded')).toBe('false');
    expect(pressBack()).toBe(false);
  });

  it('a menu that leaves the screen open no longer answers Back', async () => {
    const m = await mountSale(ScreenMenu, {});
    await click(m.find('pos-screen-menu').element);
    m.wrapper.unmount();
    expect(pressBack()).toBe(false);
  });
});
