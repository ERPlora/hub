// @vitest-environment happy-dom
// hub#2226 — importing the boot module is ALL `main.ts` does, so importing it has to be enough:
// no call to remember, no argument to pass. A boot module that exports a function and forgets to
// call it would pass every other test and fix nothing.
import { afterEach, describe, expect, it } from 'vitest';

import { i18n } from '../i18n';
import './ionic-select-text.boot';

describe('`./ionic-select-text.boot` (hub#2226)', () => {
  const before = i18n.global.locale.value;
  afterEach(() => {
    i18n.global.locale.value = before;
  });

  it('on import, the real `ion-select` opens its dialog in the language active at that moment', async () => {
    const { defineCustomElement } = await import('@ionic/core/components/ion-select.js');
    defineCustomElement();
    const el = document.createElement('ion-select') as HTMLElement & {
      okText: string;
      cancelText: string;
      multiple: boolean;
      open(ev?: Event): Promise<unknown>;
      createOverlay?: () => unknown;
    };
    el.multiple = true;
    document.body.append(el);
    let seen: string[] = [];
    el.createOverlay = () => {
      seen = [el.cancelText, el.okText];
      return { addEventListener: () => {}, onDidDismiss: () => new Promise(() => {}), present: async () => {} };
    };

    i18n.global.locale.value = 'es';
    await el.open(new MouseEvent('click'));
    expect(seen).toEqual(['Cancelar', 'Aceptar']);

    (el as unknown as { isExpanded: boolean }).isExpanded = false;
    i18n.global.locale.value = 'en';
    await el.open(new MouseEvent('click'));
    expect(seen).toEqual(['Cancel', 'OK']);
  });
});
