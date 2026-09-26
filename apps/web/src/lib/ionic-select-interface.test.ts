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

/** What Ionic's popover reads from the event it is given to decide where to open. */
type AnchorEvent = Event & { detail?: { ionShadowTarget?: EventTarget } };

/** The element Ionic's popover positions itself against (`popover/utils.js`, reference `trigger`). */
const anchorOf = (ev: AnchorEvent): EventTarget | null | undefined => ev.detail?.ionShadowTarget || ev.target;

/** Like `patchedTag`, but the probe's `open(ev)` returns the event Ionic would receive. */
function patchedAnchorTag(): string {
  const tag = uniq('ion-select');
  bootIonicSelectInterface([tag]);
  customElements.define(
    tag,
    class extends HTMLElement {
      interface = 'alert';
      multiple = false;
      open(ev?: Event): Event | undefined {
        return ev;
      }
    },
  );
  return tag;
}

/** Mounts `html` two shadow roots deep — a module page holding a module form, like verifactu's. */
function mountInNestedShadowRoots(
  html: string,
  selector: string,
): HTMLElement & { open(ev?: Event): Event | undefined } {
  const page = document.createElement('div');
  document.body.append(page);
  const form = document.createElement('div');
  page.attachShadow({ mode: 'open' }).append(form);
  const root = form.attachShadow({ mode: 'open' });
  root.innerHTML = html;
  const el = root.querySelector(selector);
  if (!el) throw new Error(`probe not found: ${selector}`);
  return el as HTMLElement & { open(ev?: Event): Event | undefined };
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
    expect(mountInShadowRoot(`<${tag} interface="action-sheet"></${tag}>`, tag).open()).toBe('action-sheet');
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
    const calls: Array<[string | undefined, AnchorEvent | undefined]> = [];
    class Probed extends HTMLElement {
      interface = 'alert';
      multiple = false;
      async open(ev?: Event): Promise<string> {
        calls.push([this.interface, ev as AnchorEvent | undefined]);
        return 'presented';
      }
    }
    customElements.define(tag, Probed);
    const el = document.createElement(tag) as unknown as Probed;
    document.body.append(el);
    const click = new MouseEvent('click');
    el.dispatchEvent(click);
    await expect(el.open(click)).resolves.toBe('presented');
    expect(calls).toHaveLength(1);
    const [opened, ev] = calls[0];
    expect(opened).toBe('popover');
    // The click still reaches Ionic — what the popover anchors to, now pinned to the select itself.
    expect(ev?.target).toBe(click.target);
    expect(ev?.detail?.ionShadowTarget).toBe(el);
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

  describe('the list opens under the field, not at the top of the module (hub#2237)', () => {
    // With a stacked/floating label (what our selects use) Ionic hands the click to the popover as
    // is, and the popover anchors to `ev.detail?.ionShadowTarget || ev.target`. By the time it reads
    // it, the click has left the module's shadow roots and `target` points at the module HOST: the
    // list covers the top of the module, 150-300 px away from the field.
    /** Opens like Ionic does — from the element's own click listener — and returns what Ionic got. */
    function clickToOpen(el: HTMLElement & { open(ev?: Event): unknown }): AnchorEvent {
      let received: AnchorEvent | undefined;
      el.addEventListener('click', (e) => {
        received = el.open(e) as AnchorEvent;
      });
      el.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
      if (!received) throw new Error('the click did not open the select');
      return received;
    }

    it('a select two shadow roots deep anchors its list to itself', () => {
      const tag = patchedAnchorTag();
      const el = mountInNestedShadowRoots(`<${tag}></${tag}>`, tag);
      const ev = clickToOpen(el);
      expect(ev.detail?.ionShadowTarget).toBe(el);
      expect(anchorOf(ev)).toBe(el);
    });

    it('keeps the rest of what the popover reads: the target, and the point for `reference: event`', () => {
      const tag = patchedAnchorTag();
      const el = mountInNestedShadowRoots(`<${tag}></${tag}>`, tag);
      let target: EventTarget | null = null;
      el.addEventListener('click', (e) => {
        target = e.target;
      });
      let received: (AnchorEvent & { clientX?: number; clientY?: number }) | undefined;
      el.addEventListener('click', (e) => {
        received = el.open(e) as typeof received;
      });
      // In a browser the point lives in getters of MouseEvent.prototype, which a copy of the event
      // skips; happy-dom keeps it as own properties, so the click is built the browser's way.
      class BrowserClick extends Event {
        get clientX(): number {
          return 12;
        }
        get clientY(): number {
          return 34;
        }
      }
      const click = new BrowserClick('click');
      expect(Object.assign({}, click).clientX, 'a copy must not carry the point by itself').toBeUndefined();
      el.dispatchEvent(click);
      expect(received?.target).toBe(target);
      expect([received?.clientX, received?.clientY]).toEqual([12, 34]);
    });

    it('an anchor the event already names is respected', () => {
      const tag = patchedAnchorTag();
      const el = mountInNestedShadowRoots(`<${tag}></${tag}>`, tag);
      const inner = document.createElement('span');
      const custom = { target: el, detail: { ionShadowTarget: inner } } as unknown as Event;
      expect(anchorOf(el.open(custom) as AnchorEvent)).toBe(inner);
    });

    it('a programmatic open without a click stays without one — Ionic then falls back by itself', () => {
      const tag = patchedAnchorTag();
      const el = mountInNestedShadowRoots(`<${tag}></${tag}>`, tag);
      expect(el.open()).toBeUndefined();
    });
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
  async function ionicSource(component: string, file = component): Promise<string> {
    const { createRequire } = await import('node:module');
    const { readFileSync } = await import('node:fs');
    const { dirname, join } = await import('node:path');
    const require = createRequire(import.meta.url);
    const core = dirname(require.resolve('@ionic/core/package.json'));
    return readFileSync(join(core, 'dist/collection/components', component, `${file}.js`), 'utf8');
  }

  it('`ion-select` is what the shell watches', () => {
    expect([...SELECT_INTERFACE_CONTROLS]).toEqual(['ion-select']);
  });

  it('Ionic still defaults to the alert, which only commits the choice on OK', async () => {
    // Pinned to the dependency, not to a snapshot of it: the day Ionic changes its default or makes
    // the alert close on pick, this hook has no reason to exist.
    const select = await ionicSource('select');
    expect(select).toContain("this.interface = 'alert'");
    expect(select).toMatch(
      /text: this\.okText,\s*handler: \(selectedValues\) => \{\s*this\.setValue\(selectedValues\);/,
    );
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

    // hub#2237 — a stacked select two shadow roots deep, the way verifactu's forms render it: the
    // event Ionic's own `open()` hands to `createOverlay` names the select as the popover's anchor.
    const deep = mountInNestedShadowRoots(
      '<ion-select label="Type" label-placement="stacked"></ion-select>',
      'ion-select',
    ) as unknown as RealSelect;
    let handed: AnchorEvent | undefined;
    deep.createOverlay = (ev) => {
      handed = ev as AnchorEvent;
      return { addEventListener: () => {}, onDidDismiss: () => new Promise(() => {}), present: async () => {} };
    };
    await deep.open(new MouseEvent('click'));
    expect(handed?.detail?.ionShadowTarget).toBe(deep);
  });

  it('with a stacked or floating label Ionic still hands the click to the popover untouched', async () => {
    // The reason hub#2237 exists: only the OTHER branch of `openPopover` names an anchor. The day
    // Ionic names one for `cover` too, the shell's anchor is redundant.
    const select = await ionicSource('select');
    expect(select).toMatch(
      /if \(hasFloatingOrStackedLabel \|\| \(mode === 'md' && fill !== undefined\)\) \{\s*size = 'cover';/,
    );
    const utils = await ionicSource('popover', 'utils');
    expect(utils).toContain('_a.ionShadowTarget) ||');
    expect(utils).toContain('customEv.target));');
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
