import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import { defineComponent, h, nextTick, ref } from 'vue';

import { syncAriaDisabled, useNativeAriaDisabled } from './ariaDisabled';

describe('syncAriaDisabled', () => {
  it('puts the unavailable state on the native buttons inside Ionic buttons', () => {
    const root = document.createElement('div');
    root.innerHTML = '<ion-button data-aria-disabled="true"></ion-button><ion-button data-aria-disabled="false"></ion-button>';
    const [blocked, available] = Array.from(root.querySelectorAll('ion-button'));
    for (const host of [blocked, available]) {
      const shadow = host.attachShadow({ mode: 'open' });
      shadow.innerHTML = '<button type="button"></button>';
    }

    syncAriaDisabled(root);

    expect(blocked.shadowRoot?.querySelector('button')?.getAttribute('aria-disabled')).toBe('true');
    expect(available.shadowRoot?.querySelector('button')?.hasAttribute('aria-disabled')).toBe(false);
  });

  it('also brings the root itself in step when the root is the Ionic button (a tile of the till)', () => {
    const tile = document.createElement('ion-button');
    tile.innerHTML = '<span></span>';
    tile.attachShadow({ mode: 'open' }).innerHTML = '<button type="button" aria-disabled="true"></button>';
    const native = () => tile.shadowRoot?.querySelector('button');

    tile.dataset.ariaDisabled = 'false';
    syncAriaDisabled(tile);
    expect(native()?.hasAttribute('aria-disabled')).toBe(false);

    tile.dataset.ariaDisabled = 'true';
    syncAriaDisabled(tile);
    expect(native()?.getAttribute('aria-disabled')).toBe('true');
  });

  it('keeps them in step from the mount of the component that uses it and after each of its updates', async () => {
    const unavailable = ref(true);
    let host: HTMLElement | undefined;
    // The ref callback gives the host its native button before the component mounts, as a loaded Ionic button has.
    const withNativeButton = (element: unknown) => {
      if (!(element instanceof HTMLElement) || element.shadowRoot) return;
      element.attachShadow({ mode: 'open' }).innerHTML = '<button type="button"></button>';
      host = element;
    };
    const Piece = defineComponent({
      setup() {
        useNativeAriaDisabled(() => host);
        return () => h('div', { ref: withNativeButton, 'data-aria-disabled': String(unavailable.value) });
      },
    });
    const wrapper = mount(Piece, { attachTo: document.body });
    const native = () => host?.shadowRoot?.querySelector('button');

    expect(native()?.getAttribute('aria-disabled')).toBe('true');
    unavailable.value = false;
    await nextTick();
    expect(native()?.hasAttribute('aria-disabled')).toBe(false);
    unavailable.value = true;
    await nextTick();
    expect(native()?.getAttribute('aria-disabled')).toBe('true');
    wrapper.unmount();
  });
});
