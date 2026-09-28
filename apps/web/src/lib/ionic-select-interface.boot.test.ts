// @vitest-environment happy-dom
// hub#2223 — importing the boot module is ALL `main.ts` does, so importing it has to be enough:
// no call to remember, no argument to pass. A boot module that exports a function and forgets to
// call it would pass every other test and fix nothing.
import { describe, expect, it } from 'vitest';

import './ionic-select-interface.boot';

describe('`./ionic-select-interface.boot` (hub#2223)', () => {
  it('on import, the real `ion-select` opens a single choice as a popover', async () => {
    const { defineCustomElement } = await import('@ionic/core/components/ion-select.js');
    defineCustomElement();
    const el = document.createElement('ion-select') as HTMLElement & {
      interface?: string;
      open(ev?: Event): Promise<unknown>;
      createOverlay?: () => unknown;
    };
    document.body.append(el);
    let seen: string | undefined;
    el.createOverlay = () => {
      seen = el.interface;
      return { addEventListener: () => {}, onDidDismiss: () => new Promise(() => {}), present: async () => {} };
    };
    await el.open(new MouseEvent('click'));
    expect(seen).toBe('popover');
  });
});
