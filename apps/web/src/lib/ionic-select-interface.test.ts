// @vitest-environment happy-dom
// hub#2223 — «los desplegables de selección simple no se cierran al elegir: hay que pulsar además
// Aceptar».
//
// `<ion-select>` opens an `alert` unless told otherwise (`@ionic/core`, select.js:
// `this.interface = 'alert'`), and Ionic's alert only commits the choice in the handler of its OK
// button: tapping an option just marks a radio. So picking one category, one status, one
// professional costs a second tap, and whoever taps outside instead believes they chose and loses
// the value. The `popover` and `modal` interfaces dismiss on the radio click itself — the way every
// dropdown the merchant knows behaves.
//
// Ionic has no global config key for the default interface, and the selects a merchant uses are in
// module Web Components shipped from 27 separate repos. So the shell fixes the DEFAULT once, for
// everyone, with the same registration-time hook as `fill` (hub#1060) and the localized buttons
// (hub#1736) — see `./ionic-registry-hook`.
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SELECT_INTERFACE_CONTROLS, bootIonicSelectInterface } from './ionic-select-interface';

let seq = 0;
/** A custom element definition cannot be undone, so every test gets its own tag. */
const uniq = (base: string) => `${base}-${(seq += 1)}`;

/**
 * Stand-in for Ionic's `ion-select`, faithful in the details this fix depends on:
 *  · the default `interface = 'alert'` is assigned in the CONSTRUCTOR;
 *  · the props live behind PROTOTYPE accessors, the way Stencil's `proxyComponent` installs them;
 *  · attributes reach the props through `attributeChangedCallback`;
 *  · the interface is read when the dialog OPENS (`open()` → `createOverlay` → `this.interface`),
 *    and `open` is a PROTOTYPE method.
 *
 * What it does NOT model on purpose: Stencil strips any own property of the element when it
 * connects (its «upgrade» of props set before definition), so a per-instance accessor cannot
 * survive on the real element. The last test of this file runs the real `ion-select` to cover that.
 */
function defineSelectProbe(tag: string): void {
  class SelectProbe extends HTMLElement {
    private state: { interface?: string; multiple?: boolean } = {};

    static get observedAttributes(): string[] {
      return ['interface', 'multiple'];
    }

    constructor() {
      super();
      this.interface = 'alert';
      this.multiple = false;
    }

    get interface(): string | undefined {
      return this.state.interface;
    }
    set interface(value: string | undefined) {
      this.state.interface = value;
    }

    get multiple(): boolean {
      return this.state.multiple ?? false;
    }
    set multiple(value: boolean) {
      this.state.multiple = value;
    }

    attributeChangedCallback(name: string, _old: string | null, value: string | null): void {
      if (name === 'interface') this.interface = value ?? undefined;
      if (name === 'multiple') this.multiple = value !== null;
    }

    /** The interface Ionic's `createOverlay()` would open, read at the moment it opens. */
    open(): string | undefined {
      return this.interface;
    }
  }
  customElements.define(tag, SelectProbe);
}

type Probe = HTMLElement & { interface?: string; multiple: boolean; open(): string | undefined };

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

/** Boots the hook for a fresh tag and registers the probe behind it. */
function patchedTag(): string {
  const tag = uniq('ion-select');
  bootIonicSelectInterface([tag]);
  defineSelectProbe(tag);
  return tag;
}

describe('a single-choice select closes the moment an option is picked (hub#2223)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('the probe reproduces the bug: an unpatched select opens the alert that needs OK', () => {
    // Control positive. If this ever reads `popover`, the probe is not measuring what it claims
    // and every green below is vacuous.
    const tag = uniq('unpatched-select');
    defineSelectProbe(tag);
    expect(mountInShadowRoot(`<${tag}></${tag}>`, tag).open()).toBe('alert');
  });

  it('a select inside a module Web Component opens a popover, which closes on pick', () => {
    const tag = patchedTag();
    expect(mountInShadowRoot(`<${tag}></${tag}>`, tag).open()).toBe('popover');
  });

  it("works in the light DOM too — the shell's own views live there", () => {
    const tag = patchedTag();
    document.body.innerHTML = `<${tag}></${tag}>`;
    expect((document.querySelector(tag) as Probe).open()).toBe('popover');
  });

  it('a MULTIPLE select keeps the alert: choosing several things needs a confirm button', () => {
    const tag = patchedTag();
    expect(mountInShadowRoot(`<${tag} multiple></${tag}>`, tag).open()).toBe('alert');
  });

  it('follows `multiple` when a module toggles it after mounting', () => {
    // Lit re-renders `?multiple=${…}` on an element that is already connected; the interface has to
    // be decided when the dialog opens, not frozen at connect time.
    const tag = patchedTag();
    const el = mountInShadowRoot(`<${tag}></${tag}>`, tag);
    el.setAttribute('multiple', '');
    expect(el.open()).toBe('alert');
    el.removeAttribute('multiple');
    expect(el.open()).toBe('popover');
    // And the other way round: after the shell chose the popover, going multiple brings the alert
    // back — the popover it wrote is still the shell's, not the author's.
    el.setAttribute('multiple', '');
    expect(el.open()).toBe('alert');
  });

  it('an explicit `interface` attribute wins — the shell sets a DEFAULT, it does not override', () => {
    const tag = patchedTag();
    expect(mountInShadowRoot(`<${tag} interface="action-sheet"></${tag}>`, tag).open()).toBe(
      'action-sheet',
    );
    expect(mountInShadowRoot(`<${tag} interface="modal"></${tag}>`, tag).open()).toBe('modal');
  });

  it('an explicit `interface="alert"` stays an alert — a module may want it on purpose', () => {
    const tag = patchedTag();
    expect(mountInShadowRoot(`<${tag} interface="alert"></${tag}>`, tag).open()).toBe('alert');
  });

  it('an explicit PROPERTY set before mounting wins, which is how Vue and Lit `.interface` bind', () => {
    const tag = patchedTag();
    const el = document.createElement(tag) as Probe;
    el.interface = 'modal';
    document.body.append(el);
    expect(el.open()).toBe('modal');
  });

  it('a property set AFTER mounting wins too, and sticks', () => {
    const tag = patchedTag();
    const el = mountInShadowRoot(`<${tag}></${tag}>`, tag);
    el.interface = 'action-sheet';
    expect(el.open()).toBe('action-sheet');
    expect(el.interface).toBe('action-sheet');
  });

  it('an attribute set AFTER mounting wins too', () => {
    const tag = patchedTag();
    const el = mountInShadowRoot(`<${tag}></${tag}>`, tag);
    el.setAttribute('interface', 'modal');
    expect(el.open()).toBe('modal');
  });

  it("keeps the element working: Ionic's own `open` still runs and its result comes back", async () => {
    const tag = uniq('ion-select');
    bootIonicSelectInterface([tag]);
    const calls: Array<[string | undefined, Event | undefined]> = [];
    class Probed extends HTMLElement {
      interface = 'alert';
      multiple = false;
      async open(ev?: Event): Promise<string> {
        calls.push([this.interface, ev]);
        return 'presented';
      }
    }
    customElements.define(tag, Probed);
    const el = document.createElement(tag) as unknown as Probed;
    document.body.append(el);
    const click = new MouseEvent('click');
    await expect(el.open(click)).resolves.toBe('presented');
    expect(calls).toEqual([['popover', click]]); // the click is what the popover anchors to
  });

  it('is idempotent: booting twice does not double-patch or throw', () => {
    const tag = uniq('ion-select');
    bootIonicSelectInterface([tag]);
    bootIonicSelectInterface([tag]);
    defineSelectProbe(tag);
    const el = mountInShadowRoot(`<${tag}></${tag}>`, tag);
    expect(el.open()).toBe('popover');
    el.remove();
    document.body.append(el); // re-connecting must not stack a second default either
    el.interface = 'modal';
    expect(el.open()).toBe('modal');
  });

  it('booting LATE still works — `open` is a method, not a lifecycle callback frozen by define', () => {
    const tag = uniq('ion-select');
    defineSelectProbe(tag);
    const reported = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      bootIonicSelectInterface([tag]);
      expect(mountInShadowRoot(`<${tag}></${tag}>`, tag).open()).toBe('popover');
      expect(reported).not.toHaveBeenCalled();
    } finally {
      reported.mockRestore();
    }
  });
});

describe('the premise still holds', () => {
  /** Source of one `@ionic/core` component, read from the installed dependency itself. */
  async function ionicSource(component: string): Promise<string> {
    const { createRequire } = await import('node:module');
    const { readFileSync } = await import('node:fs');
    const { dirname, join } = await import('node:path');
    const require = createRequire(import.meta.url);
    const core = dirname(require.resolve('@ionic/core/package.json'));
    return readFileSync(
      join(core, 'dist/collection/components', component, `${component}.js`),
      'utf8',
    );
  }

  it('`ion-select` is what the shell watches', () => {
    expect([...SELECT_INTERFACE_CONTROLS]).toEqual(['ion-select']);
  });

  it('Ionic still defaults to the alert, which only commits the choice on OK', async () => {
    // Pinned to the dependency, not to a snapshot of it: the day Ionic changes its default or makes
    // the alert close on pick, this hook has no reason to exist.
    const select = await ionicSource('select');
    expect(select).toContain("this.interface = 'alert'");
    expect(select).toMatch(/text: this\.okText,\s*handler: \(selectedValues\) => \{\s*this\.setValue\(selectedValues\);/);
  });

  it('the popover the shell picks really closes on the click of an option', async () => {
    const popover = await ionicSource('select-popover');
    expect(popover).toContain('onClick: () => this.dismissParentPopover()');
  });

  it('the REAL `ion-select` of @ionic/core opens a popover once the shell hooked it', async () => {
    // The probe above is faithful by construction; this one removes the construction: Ionic's own
    // element, its own `open()`, and the interface its own `createOverlay` receives. Only the
    // overlay itself is stubbed — happy-dom cannot present one. It runs LAST in this file because
    // `customElements.define` cannot be undone.
    bootIonicSelectInterface();
    const { defineCustomElement } = await import('@ionic/core/components/ion-select.js');
    defineCustomElement();

    type RealSelect = HTMLElement & {
      interface?: string;
      multiple: boolean;
      open(ev?: Event): Promise<unknown>;
      createOverlay?: (ev?: Event) => unknown;
    };
    /** Opens `el` the way a click does and returns the interface Ionic was about to present. */
    async function openedInterface(el: RealSelect): Promise<string | undefined> {
      let seen: string | undefined;
      el.createOverlay = () => {
        seen = el.interface;
        return {
          addEventListener: () => {},
          onDidDismiss: () => new Promise(() => {}), // stays open, like a real dialog
          present: async () => {},
        };
      };
      await el.open(new MouseEvent('click'));
      (el as unknown as { isExpanded: boolean }).isExpanded = false; // ready for the next open
      return seen;
    }

    const el = document.createElement('ion-select') as RealSelect;
    // Control positive: Ionic's constructor still writes `alert`, the interface that needs OK.
    expect(el.interface, 'Ionic still defaults to the alert').toBe('alert');
    document.body.append(el);
    expect(await openedInterface(el)).toBe('popover');

    el.multiple = true;
    expect(await openedInterface(el)).toBe('alert');

    const explicit = document.createElement('ion-select') as RealSelect;
    explicit.setAttribute('interface', 'action-sheet');
    document.body.append(explicit);
    expect(await openedInterface(explicit)).toBe('action-sheet');
  });

  it('the shell boots the hook: main.ts imports it next to its twins, before @ionic/vue', async () => {
    // Wrapping a method would still work after `define`, but a boot module nobody imports fixes
    // nothing — and next to the other two hooks is where the next reader looks for it.
    const { readFileSync } = await import('node:fs');
    const { join } = await import('node:path');
    const main = readFileSync(join(process.cwd(), 'src', 'main.ts'), 'utf8');
    const boot = main.indexOf("import './lib/ionic-select-interface.boot'");
    const ionic = main.indexOf("from '@ionic/vue'");
    expect(boot, 'main.ts must import ./lib/ionic-select-interface.boot').toBeGreaterThanOrEqual(0);
    expect(ionic, 'main.ts is supposed to import @ionic/vue').toBeGreaterThanOrEqual(0);
    expect(boot < ionic, 'keep the shell hooks together, before @ionic/vue').toBe(true);
  });
});
