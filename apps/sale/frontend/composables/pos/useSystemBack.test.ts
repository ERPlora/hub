// The system Back (Android's, on the installed app) closes the till's own layers — sheets of the app, not Ionic
// overlays, which the shell cannot see — through base's `erplora:back` contract (base/frontend/lib/system-back.ts): on
// every press the shell dispatches a cancelable `erplora:back` on `window`; an app with something open closes its
// TOPMOST layer and calls `preventDefault()`, and the shell keeps the screen. Nothing open: the shell's own Back.
import { afterEach, describe, expect, it } from 'vitest';
import { effectScope, type EffectScope, nextTick, shallowRef } from 'vue';

import { SHELL_BACK_EVENT } from '../../../../../base/frontend/lib/system-back';
import { useSystemBack } from './useSystemBack';

const scopes: EffectScope[] = [];

afterEach(() => {
  scopes.splice(0).forEach((scope) => scope.stop());
});

/** A layer of the till: open or not, closed by `useSystemBack` the way its own ✕ would. */
function layer(open = false) {
  const shown = shallowRef(open);
  const scope = effectScope();
  scope.run(() => useSystemBack(shown, () => (shown.value = false)));
  scopes.push(scope);
  return { shown, scope };
}

/** One press of the system Back, as the shell asks: `true` when the app took it. */
function pressBack(): boolean {
  const ask = new CustomEvent(SHELL_BACK_EVENT, { cancelable: true });
  window.dispatchEvent(ask);
  return ask.defaultPrevented;
}

describe('useSystemBack', () => {
  it('an open layer is closed by Back, which the app takes: the screen stays', () => {
    const menu = layer(true);
    expect(pressBack()).toBe(true);
    expect(menu.shown.value).toBe(false);
  });

  it('a closed layer leaves Back to the shell', async () => {
    const menu = layer();
    expect(pressBack()).toBe(false);
    menu.shown.value = true;
    await nextTick();
    menu.shown.value = false;
    await nextTick();
    expect(pressBack()).toBe(false);
  });

  it('closes the topmost first: the last one opened, then the one under it, then Back is the shell’s again', async () => {
    const drawer = layer();
    const checks = layer();
    drawer.shown.value = true;
    checks.shown.value = true;
    await nextTick();
    expect(pressBack()).toBe(true);
    expect(checks.shown.value).toBe(false);
    expect(drawer.shown.value).toBe(true);
    await nextTick();
    expect(pressBack()).toBe(true);
    expect(drawer.shown.value).toBe(false);
    await nextTick();
    expect(pressBack()).toBe(false);
  });

  it('one press closes one layer, and a second one before the screen repaints closes the next', () => {
    const drawer = layer(true);
    const checks = layer(true);
    expect(pressBack()).toBe(true);
    expect([drawer.shown.value, checks.shown.value]).toEqual([true, false]);
    expect(pressBack()).toBe(true);
    expect([drawer.shown.value, checks.shown.value]).toEqual([false, false]);
    expect(pressBack()).toBe(false);
  });

  it('a Back something else already took is left alone', () => {
    // Heard before the till's: it took the press.
    const before = (event: Event) => event.preventDefault();
    window.addEventListener(SHELL_BACK_EVENT, before);
    const menu = layer(true);
    try {
      pressBack();
      expect(menu.shown.value).toBe(true);
    } finally {
      window.removeEventListener(SHELL_BACK_EVENT, before);
    }
  });

  it('a layer that goes away open (its screen left) no longer answers', () => {
    const menu = layer(true);
    menu.scope.stop();
    expect(pressBack()).toBe(false);
    expect(menu.shown.value).toBe(true);
  });
});
