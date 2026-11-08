import { describe, expect, it } from 'vitest';

import { syncAriaDisabled } from './ariaDisabled';

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
});
