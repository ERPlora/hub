// @vitest-environment happy-dom
// hub#1060 — «el shell arranca en modo iOS y ahí `fill="outline"` no pinta borde».
//
// Ionic only implements `fill` in `md` mode (`hasOutlineFill = mode === 'md' && this.fill ===
// 'outline'`), and the shell pins `ios` on purpose (ADR-0143). Every control that declares `fill`
// therefore renders with no box unless it ALSO declares `mode="md"`.
//
// The house rule so far was «each control declares `mode="md"` itself», guarded by a source test
// per product. That guard only reaches OUR source: the forms the merchant actually types into live
// in module Web Components, shipped from 25 separate repos (and, tomorrow, from third parties in
// the marketplace). A platform whose default form control renders invisible cannot be fixed one
// repo at a time — so the shell normalizes it for everyone, once, at element-registration time.
//
// Why registration time: an `<ion-input>` inside a module's shadow root is unreachable from the
// document's stylesheets, and Ionic resolves the mode ONCE, in its own `connectedCallback`,
// caching it in the Stencil host ref — so setting the attribute afterwards is already too late.
// And per the HTML spec a custom element's lifecycle callbacks are captured by
// `customElements.define`, so patching a prototype after the fact is a silent no-op (verified:
// the `too late` test below is exactly that scenario).
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FILL_MODE_CONTROLS, bootIonicFillMode } from './ionic-fill';

/**
 * Stand-in for a Stencil/Ionic control: it records the `mode` that Ionic WOULD resolve, using
 * Ionic's own rule, at the exact moment Ionic resolves it (its `connectedCallback`).
 */
function defineProbe(tag: string): void {
  if (customElements.get(tag)) return;
  customElements.define(
    tag,
    class extends HTMLElement {
      /** What Ionic's `setMode` resolver would have returned for this element. */
      resolvedMode: string | null = null;
      connectedCallback(): void {
        // Ionic: `elm.mode || elm.getAttribute('mode')`, walking up until something answers.
        let elm: Element | null = this;
        while (elm) {
          const mode = (elm as { mode?: string }).mode || elm.getAttribute('mode');
          if (mode === 'ios' || mode === 'md') {
            this.resolvedMode = mode;
            return;
          }
          elm = elm.parentElement;
        }
        this.resolvedMode = 'ios'; // defaultMode — what ADR-0143 pins
      }
    },
  );
}

type Probe = HTMLElement & { resolvedMode: string | null };

/** Mounts `html` in a fresh shadow root — the way every module Web Component renders. */
function mountInShadowRoot(html: string): ShadowRoot {
  const host = document.createElement('div');
  document.body.append(host);
  const root = host.attachShadow({ mode: 'open' });
  root.innerHTML = html;
  return root;
}

function probeIn(root: ParentNode, selector: string): Probe {
  const el = root.querySelector(selector);
  if (!el) throw new Error(`probe not found: ${selector}`);
  return el as Probe;
}

// Each test gets its own tag names: a custom element definition cannot be undone, and the boot
// hook is installed once per registry, so reusing `ion-input` across tests would let one test's
// registration decide another test's outcome.
let seq = 0;
const uniq = (base: string) => `${base}-${(seq += 1)}`;

describe('the shell makes `fill` paint a box wherever it is declared (hub#1060)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('the probe reproduces the bug: a control with `fill` and no shell resolves to `ios`', () => {
    // Control positive. If this ever reads `md`, the probe is not measuring what it claims and
    // every green below is vacuous.
    const tag = uniq('unpatched-input');
    defineProbe(tag);
    const root = mountInShadowRoot(`<${tag} fill="outline"></${tag}>`);
    expect(probeIn(root, tag).resolvedMode).toBe('ios');
  });

  it.each([...FILL_MODE_CONTROLS])('%s with `fill` resolves to `md` inside a shadow root', (base) => {
    const tag = uniq(base);
    bootIonicFillMode([tag]);
    defineProbe(tag);
    const root = mountInShadowRoot(`<${tag} fill="outline" label="NIF"></${tag}>`);
    expect(probeIn(root, tag).resolvedMode).toBe('md');
  });

  it("works in the light DOM too — the shell's own views live there", () => {
    const tag = uniq('ion-input');
    bootIonicFillMode([tag]);
    defineProbe(tag);
    document.body.innerHTML = `<${tag} fill="outline"></${tag}>`;
    expect(probeIn(document, tag).resolvedMode).toBe('md');
  });

  it('normalizes `fill` set as a PROPERTY, which is how Lit binds `.fill=${…}`', () => {
    const tag = uniq('ion-input');
    bootIonicFillMode([tag]);
    defineProbe(tag);
    const el = document.createElement(tag) as Probe & { fill?: string };
    el.fill = 'outline';
    document.body.append(el);
    expect(el.resolvedMode).toBe('md');
  });

  it('an explicit `mode` wins — the shell normalizes, it does not override', () => {
    const tag = uniq('ion-input');
    bootIonicFillMode([tag]);
    defineProbe(tag);
    const root = mountInShadowRoot(`<${tag} fill="outline" mode="ios"></${tag}>`);
    expect(probeIn(root, tag).resolvedMode).toBe('ios');
  });

  it('a control WITHOUT `fill` is left alone: the shell stays iOS (ADR-0143)', () => {
    const tag = uniq('ion-input');
    bootIonicFillMode([tag]);
    defineProbe(tag);
    const root = mountInShadowRoot(`<${tag} label="Nombre"></${tag}>`);
    expect(probeIn(root, tag).resolvedMode).toBe('ios');
  });

  it('a tag the shell does not watch is untouched — ion-button honours `fill` in `ios`', () => {
    const watched = uniq('ion-input');
    const button = uniq('ion-button');
    bootIonicFillMode([watched]);
    defineProbe(button);
    const root = mountInShadowRoot(`<${button} fill="outline">Guardar</${button}>`);
    expect(probeIn(root, button).resolvedMode).toBe('ios');
  });

  it('keeps the element working: the original connectedCallback still runs', () => {
    // The probe only ever sets `resolvedMode` from its own connectedCallback, so a non-null value
    // is proof the original body was called and not swallowed by the patch.
    const tag = uniq('ion-input');
    bootIonicFillMode([tag]);
    defineProbe(tag);
    const root = mountInShadowRoot(`<${tag} fill="outline"></${tag}>`);
    expect(probeIn(root, tag).resolvedMode).not.toBeNull();
  });

  it('is idempotent: booting twice does not double-patch or throw', () => {
    const tag = uniq('ion-input');
    bootIonicFillMode([tag]);
    bootIonicFillMode([tag]);
    defineProbe(tag);
    const root = mountInShadowRoot(`<${tag} fill="outline"></${tag}>`);
    expect(probeIn(root, tag).resolvedMode).toBe('md');
  });

  it('booting TOO LATE is reported, not swallowed — the whole fix hinges on the order', () => {
    // The HTML spec captures a custom element's callbacks inside `customElements.define`, so once
    // Ionic has registered `ion-input` there is nothing left to hook. That failure is invisible by
    // nature (the form just renders without a box, exactly the bug), so it has to be said out loud.
    const tag = uniq('ion-input');
    defineProbe(tag);
    const reported = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      bootIonicFillMode([tag]);
      expect(reported).toHaveBeenCalledTimes(1);
      expect(String(reported.mock.calls[0]?.[0])).toContain(tag);
    } finally {
      reported.mockRestore();
    }
  });
});
