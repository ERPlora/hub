// Sales & POS → Sell on a phone, or in a till as narrow as one: the check is a drawer the cart button opens.
import { describe, expect, it, vi } from 'vitest';

import { SHELL_BACK_EVENT } from '../../../../base/frontend/lib/system-back';
import { click, settle } from '../__tests__/mount-sale';
import { freshEachTest, setup, TWO } from '../__tests__/pos-page';
import { preview } from '../components/pos/__tests__/fixtures';

freshEachTest();

/** The window is as narrow as a phone's. */
const onAPhone = () =>
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: true,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));

/** Android's Back as the shell passes it on: true when the screen took it. */
const pressBack = () => {
  const ask = new CustomEvent(SHELL_BACK_EVENT, { cancelable: true });
  window.dispatchEvent(ask);
  return ask.defaultPrevented;
};

describe('PosPage: the phone', () => {
  it('the open drawer is a modal dialog named «Check», and Escape closes it', async () => {
    onAPhone();
    const s = await setup({ locale: 'es' });
    const drawer = () => s.find('pos-cart-drawer');
    expect(drawer().attributes('role')).toBeUndefined();
    await click(s.find('pos-cart-fab').element);
    expect(drawer().attributes()).toMatchObject({ role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Cuenta', tabindex: '-1' });
    s.find('pos-till').element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await settle();
    expect(s.find('pos-till').classes()).not.toContain('pos-till--cart-open');
    expect(drawer().attributes('role')).toBeUndefined();
  });

  it('Android’s Back closes what is on top: «Open checks» first, then the drawer, then it is the shell’s', async () => {
    onAPhone();
    const s = await setup();
    const cartOpen = () => s.find('pos-till').classes().includes('pos-till--cart-open');
    await click(s.find('pos-cart-fab').element);
    await click(s.find('pos-open-checks').element);
    expect(s.find('pos-checks').exists()).toBe(true);
    expect(pressBack()).toBe(true);
    await settle();
    expect(s.find('pos-checks').exists()).toBe(false);
    expect(cartOpen()).toBe(true);
    expect(pressBack()).toBe(true);
    await settle();
    expect(cartOpen()).toBe(false);
    expect(pressBack()).toBe(false);
  });

  it('a drawer left open when the till widens (a phone turned, a window enlarged) is a column: Back is the shell’s', async () => {
    const media = { matches: true, change: () => {} };
    vi.stubGlobal('matchMedia', (query: string) => ({
      get matches() {
        return media.matches;
      },
      media: query,
      addEventListener: (_: string, listener: () => void) => (media.change = listener),
      removeEventListener: () => {},
    }));
    const s = await setup();
    await click(s.find('pos-cart-fab').element);
    media.matches = false;
    media.change();
    await settle();
    expect(s.find('pos-till').classes()).not.toContain('pos-till--phone');
    expect(pressBack()).toBe(false);
  });


  // «Speak» opens the assistant docked beside the screen (from 768 px); on a tablet the till
  // left beside it is too narrow for the catalogue and the check side by side, whatever the window's width.
  it('a till narrower than the catalogue and the check need (beside the docked assistant) is laid out as on a phone', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {} }));
    class Observer {
      static all = new Set<Observer>();
      static width = 1000;
      targets: Element[] = [];
      constructor(private readonly callback: ResizeObserverCallback) {
        Observer.all.add(this);
      }
      observe(target: Element) {
        this.targets.push(target);
        this.fire();
      }
      unobserve(target: Element) {
        this.targets = this.targets.filter((t) => t !== target);
      }
      // A real observer observes again after `disconnect`.
      disconnect() {
        this.targets = [];
      }
      fire() {
        const entries = this.targets.map((target) => ({ target, contentRect: { width: Observer.width } }));
        this.callback(entries as unknown as ResizeObserverEntry[], this as unknown as ResizeObserver);
      }
    }
    vi.stubGlobal('ResizeObserver', Observer);
    const s = await setup({ locale: 'es' });
    const drawer = () => s.find('pos-cart-drawer');
    expect(s.find('pos-till').classes()).not.toContain('pos-till--phone');
    await click(s.find('pos-cart-fab').element);
    expect(drawer().attributes('role')).toBeUndefined();

    Observer.width = 450;
    for (const observer of Observer.all) observer.fire();
    await settle();
    expect(s.find('pos-till').classes()).toContain('pos-till--phone');
    await click(s.find('pos-cart-fab').element);
    expect(drawer().attributes()).toMatchObject({ role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Cuenta' });
  });

  it('the cart button carries the count and the total, and opens the drawer', async () => {
    const s = await setup();
    await s.addProduct('p1', TWO);
    await s.result('sale.checkout.preview', preview({ total: 300 }));
    const fab = s.find('pos-cart-fab');
    expect(fab.attributes('aria-label')).toBe('Open cart, 2 items, total €3.00');
    await click(fab.element);
    expect(s.find('pos-till').classes()).toContain('pos-till--cart-open');
    await click(s.find('pos-cart-backdrop').element);
    expect(s.find('pos-till').classes()).not.toContain('pos-till--cart-open');
  });
});
