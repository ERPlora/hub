// @vitest-environment happy-dom
// hub#1736 — «los desplegables dicen CANCEL y OK en inglés dentro de una app en español».
//
// Every `<ion-select>` opens an alert (or an action sheet) whose two buttons Ionic labels from its
// own props, whose defaults are the English literals `'Cancel'` and `'OK'` (`@ionic/core`,
// select.js: `this.cancelText = 'Cancel'` … `this.okText = 'OK'`). Ionic has no global config key
// for them, so the house rule would have to be «every select in the product passes ok-text and
// cancel-text» — and the selects a merchant actually uses are in module Web Components shipped
// from 27 separate repos, and tomorrow from marketplace authors we never review. A platform cannot
// ask every module author to remember two attributes whose absence is only visible in the finished
// app: it has to make the default correct, once, for everyone.
//
// So the shell localizes the DEFAULT at element-registration time — the same hook, and for the
// same reasons, as the `fill` fix of hub#1060 (`./ionic-registry-hook`).
//
// The value is installed as a LIVE per-instance getter, not as a copied string: the hub changes
// language on the fly (`i18n/index.ts` → `setLocale`, no reload), and Ionic reads `this.okText`
// when the dialog OPENS, so a select mounted before the change must still open in the new
// language.
import { beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';
import { i18n } from '../i18n';
import { SELECT_TEXT_CONTROLS, bootIonicSelectText, shellSelectText } from './ionic-select-text';

let seq = 0;
/** A custom element definition cannot be undone, so every test gets its own tag. */
const uniq = (base: string) => `${base}-${(seq += 1)}`;

/**
 * Stand-in for Ionic's `ion-select`, faithful in the three details this fix depends on:
 *  · the English defaults are assigned in the CONSTRUCTOR (`this.okText = 'OK'`);
 *  · the props live behind PROTOTYPE accessors, the way Stencil's `proxyComponent` installs them —
 *    there is no own data property to overwrite;
 *  · the button labels are read when the dialog OPENS, not when the element is connected.
 */
function defineSelectProbe(tag: string): void {
  class SelectProbe extends HTMLElement {
    /** Stencil keeps prop values off the instance; reads and writes go through the accessors. */
    private state: Record<string, string> = {};

    static get observedAttributes(): string[] {
      return ['ok-text', 'cancel-text'];
    }

    constructor() {
      super();
      this.cancelText = 'Cancel';
      this.okText = 'OK';
    }

    get okText(): string {
      return this.state.okText;
    }
    set okText(value: string) {
      this.state.okText = value;
    }

    get cancelText(): string {
      return this.state.cancelText;
    }
    set cancelText(value: string) {
      this.state.cancelText = value;
    }

    attributeChangedCallback(name: string, _old: string | null, value: string): void {
      if (name === 'ok-text') this.okText = value;
      if (name === 'cancel-text') this.cancelText = value;
    }

    /** What Ionic's `openAlert()` puts on the two buttons, read at the moment it opens. */
    open(): string[] {
      return [this.cancelText, this.okText];
    }
  }
  customElements.define(tag, SelectProbe);
}

type Probe = HTMLElement & { okText: string; cancelText: string; open(): string[] };

/** Mounts the probe in a fresh shadow root — the way every module Web Component renders. */
function mountInShadowRoot(html: string, selector: string): Probe {
  const host = document.createElement('div');
  document.body.append(host);
  const root = host.attachShadow({ mode: 'open' });
  root.innerHTML = html;
  const el = root.querySelector(selector);
  if (!el) throw new Error(`probe not found: ${selector}`);
  return el as Probe;
}

/** The shell in Spanish, as every hub ships by default. */
const spanish = (prop: 'okText' | 'cancelText') => (prop === 'okText' ? 'Aceptar' : 'Cancelar');

describe('the selection dialogs speak the app language (hub#1736)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('the probe reproduces the bug: an unpatched select opens with CANCEL / OK', () => {
    // Control positive. If this ever reads Spanish, the probe is not measuring what it claims and
    // every green below is vacuous.
    const tag = uniq('unpatched-select');
    defineSelectProbe(tag);
    expect(mountInShadowRoot(`<${tag}></${tag}>`, tag).open()).toEqual(['Cancel', 'OK']);
  });

  it('a select inside a module Web Component opens in Spanish', () => {
    const tag = uniq('ion-select');
    bootIonicSelectText(spanish, [tag]);
    defineSelectProbe(tag);
    expect(mountInShadowRoot(`<${tag}></${tag}>`, tag).open()).toEqual(['Cancelar', 'Aceptar']);
  });

  it("works in the light DOM too — the shell's own views live there", () => {
    const tag = uniq('ion-select');
    bootIonicSelectText(spanish, [tag]);
    defineSelectProbe(tag);
    document.body.innerHTML = `<${tag}></${tag}>`;
    expect((document.querySelector(tag) as Probe).open()).toEqual(['Cancelar', 'Aceptar']);
  });

  it('changing the language repaints a select that was ALREADY mounted', () => {
    // The hub switches language with no reload (`setLocale`), and Ionic reads the labels when the
    // dialog opens. A copied string would leave every mounted select in the old language forever.
    const tag = uniq('ion-select');
    let locale = 'es';
    bootIonicSelectText(
      (prop) => (locale === 'es' ? spanish(prop) : prop === 'okText' ? 'OK' : 'Cancel'),
      [tag],
    );
    defineSelectProbe(tag);
    const el = mountInShadowRoot(`<${tag}></${tag}>`, tag);
    expect(el.open()).toEqual(['Cancelar', 'Aceptar']);
    locale = 'en';
    expect(el.open()).toEqual(['Cancel', 'OK']);
  });

  it('an explicit `ok-text` attribute wins — the shell localizes a DEFAULT, it does not override', () => {
    const tag = uniq('ion-select');
    bootIonicSelectText(spanish, [tag]);
    defineSelectProbe(tag);
    const el = mountInShadowRoot(`<${tag} ok-text="Elegir" cancel-text="Dejarlo"></${tag}>`, tag);
    expect(el.open()).toEqual(['Dejarlo', 'Elegir']);
  });

  it('an explicit `ok-text="OK"` stays English — a module may want the English word on purpose', () => {
    // The only case the value check alone cannot see: the label a module asked for is letter for
    // letter Ionic's default. Declaring it is a choice, and the shell does not second-guess it.
    const tag = uniq('ion-select');
    bootIonicSelectText(spanish, [tag]);
    defineSelectProbe(tag);
    const el = mountInShadowRoot(`<${tag} ok-text="OK" cancel-text="Cancel"></${tag}>`, tag);
    expect(el.open()).toEqual(['Cancel', 'OK']);
  });

  it('an explicit PROPERTY set before mounting wins, which is how Lit binds `.okText=${…}`', () => {
    const tag = uniq('ion-select');
    bootIonicSelectText(spanish, [tag]);
    defineSelectProbe(tag);
    const el = document.createElement(tag) as Probe;
    el.okText = 'Elegir';
    document.body.append(el);
    expect(el.open()).toEqual(['Cancelar', 'Elegir']);
  });

  it('a property set AFTER mounting wins too, and sticks', () => {
    const tag = uniq('ion-select');
    bootIonicSelectText(spanish, [tag]);
    defineSelectProbe(tag);
    const el = mountInShadowRoot(`<${tag}></${tag}>`, tag);
    el.okText = 'Elegir';
    expect(el.open()).toEqual(['Cancelar', 'Elegir']);
    expect(el.okText).toBe('Elegir');
  });

  it('keeps the element working: the original connectedCallback still runs', () => {
    const tag = uniq('ion-select');
    bootIonicSelectText(spanish, [tag]);
    let connected = false;
    class Probed extends HTMLElement {
      okText = 'OK';
      cancelText = 'Cancel';
      connectedCallback(): void {
        connected = true;
      }
    }
    customElements.define(tag, Probed);
    document.body.append(document.createElement(tag));
    expect(connected).toBe(true);
  });

  it('is idempotent: booting twice does not double-patch or throw', () => {
    const tag = uniq('ion-select');
    bootIonicSelectText(spanish, [tag]);
    bootIonicSelectText(spanish, [tag]);
    defineSelectProbe(tag);
    expect(mountInShadowRoot(`<${tag}></${tag}>`, tag).open()).toEqual(['Cancelar', 'Aceptar']);
  });

  it('a translation that blows up falls back to Ionic English instead of breaking the dialog', () => {
    // A dialog that throws while opening is a dead control: better an English button than a select
    // the cashier cannot use. And it is reported, because a silent fallback to English IS the bug.
    const tag = uniq('ion-select');
    const reported = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      bootIonicSelectText(() => {
        throw new Error('catalogue missing');
      }, [tag]);
      defineSelectProbe(tag);
      expect(mountInShadowRoot(`<${tag}></${tag}>`, tag).open()).toEqual(['Cancel', 'OK']);
      expect(reported).toHaveBeenCalled();
    } finally {
      reported.mockRestore();
    }
  });

  it('a MISSING key falls back to English instead of painting `selectDialog.ok` on the button', () => {
    // vue-i18n does not throw on a key it does not have: it returns the key PATH, which is how a
    // dotted path ends up printed in the UI. A button reading `selectDialog.ok` is worse than one
    // reading OK, so the shell treats the echo as no answer — and says so.
    const tag = uniq('ion-select');
    const reported = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      bootIonicSelectText(
        (prop) => (prop === 'okText' ? 'selectDialog.ok' : 'selectDialog.cancel'),
        [tag],
      );
      defineSelectProbe(tag);
      expect(mountInShadowRoot(`<${tag}></${tag}>`, tag).open()).toEqual(['Cancel', 'OK']);
      expect(reported).toHaveBeenCalled();
    } finally {
      reported.mockRestore();
    }
  });

  it('booting TOO LATE is reported, not swallowed — the whole fix hinges on the order', () => {
    const tag = uniq('ion-select');
    defineSelectProbe(tag);
    const reported = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      bootIonicSelectText(spanish, [tag]);
      expect(reported).toHaveBeenCalledTimes(1);
      expect(String(reported.mock.calls[0]?.[0])).toContain(tag);
    } finally {
      reported.mockRestore();
    }
  });
});

describe('the strings come from the shell catalogue, not from a literal', () => {
  it('the shell resolver follows the active language', () => {
    const before = i18n.global.locale.value;
    try {
      i18n.global.locale.value = 'es';
      expect([shellSelectText('cancelText'), shellSelectText('okText')]).toEqual([
        'Cancelar',
        'Aceptar',
      ]);
      i18n.global.locale.value = 'en';
      expect([shellSelectText('cancelText'), shellSelectText('okText')]).toEqual(['Cancel', 'OK']);
    } finally {
      i18n.global.locale.value = before;
    }
  });

  it('both catalogues declare the two buttons (ADR-0055: `en` is the source, `es` its translation)', () => {
    expect(en.selectDialog).toEqual({ ok: 'OK', cancel: 'Cancel' });
    expect(es.selectDialog).toEqual({ ok: 'Aceptar', cancel: 'Cancelar' });
  });
});

describe('the premise still holds', () => {
  it('`ion-select` is what the shell watches', () => {
    expect([...SELECT_TEXT_CONTROLS]).toEqual(['ion-select']);
  });

  it('Ionic still ships the buttons in English — the day it stops, this fix can go', async () => {
    // Pinned to the dependency itself, not to a snapshot of it: the guard must not outlive its
    // cause, and the defaults below are what `./ionic-select-text` refuses to overwrite.
    const { createRequire } = await import('node:module');
    const { readFileSync } = await import('node:fs');
    const { dirname, join } = await import('node:path');
    const require = createRequire(import.meta.url);
    const core = dirname(require.resolve('@ionic/core/package.json'));
    const select = readFileSync(join(core, 'dist/collection/components/select/select.js'), 'utf8');

    expect(select).toContain("this.cancelText = 'Cancel'");
    expect(select).toContain("this.okText = 'OK'");
  });

  it('the shell hooks element registration BEFORE @ionic/vue registers anything', async () => {
    // `@ionic/vue` registers `ion-select` on import and the HTML spec captures a custom element's
    // lifecycle callbacks inside `define`. Move the import down and the fix vanishes with no error
    // at all — which is the exact failure mode this whole file is about.
    const { readFileSync } = await import('node:fs');
    const { join } = await import('node:path');
    // `process.cwd()` is the package root under vitest — the house convention for source guards.
    // A wrong path throws here instead of passing on an empty read.
    const main = readFileSync(join(process.cwd(), 'src', 'main.ts'), 'utf8');
    const boot = main.indexOf("import './lib/ionic-select-text.boot'");
    const ionic = main.indexOf("from '@ionic/vue'");
    expect(boot, 'main.ts must import ./lib/ionic-select-text.boot').toBeGreaterThanOrEqual(0);
    expect(ionic, 'main.ts is supposed to import @ionic/vue').toBeGreaterThanOrEqual(0);
    expect(
      boot < ionic,
      'the select-text hook must be imported before @ionic/vue, or it silently stops working',
    ).toBe(true);
  });
});
