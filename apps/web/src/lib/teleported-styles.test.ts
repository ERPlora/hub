// @vitest-environment happy-dom
// hub#2162 — the shell preloads, into the DOCUMENT, the stylesheets of the Ionic components that
// have no shadow root of their own, so that an overlay a module opens INLINE (inside its Lit shadow
// root) keeps its styles once Ionic teleports it to `ion-app`.
//
// Stencil attaches a non-shadow component's sheet to the root node it FIRST renders in and never
// again; hydrating one hidden instance per tag and mode in the document is what puts the sheet
// there. These tests pin the contract of that preload with stand-in custom elements; the proof
// with the real Ionic runtime is the bench spec `tests/e2e/ModuleInlineAlert.spec.ts`.
import { afterEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TELEPORTED_STYLE_MODES, TELEPORTED_STYLE_TAGS, preloadTeleportedStyles } from './teleported-styles';

type Seen = { tag: string; mode: string | null; inDocument: boolean; hiddenContainer: boolean };

let seq = 0;
const seen: Seen[] = [];
/** Whether each probe was still in the document when it hydrated (its sheet goes to that root). */
const hydratedInDocument: boolean[] = [];

/** A stand-in for a Stencil component: records where it was connected, hydrates a tick later. */
function defineStandIn(registry: CustomElementRegistry, tag: string, hydrates = true): void {
  registry.define(
    tag,
    class extends HTMLElement {
      connectedCallback() {
        const container = this.parentElement;
        seen.push({
          tag,
          mode: this.getAttribute('mode'),
          inDocument: this.getRootNode() === document,
          hiddenContainer: !!container && container.hidden && container.getAttribute('aria-hidden') === 'true',
        });
        if (hydrates)
          setTimeout(() => {
            hydratedInDocument.push(this.isConnected && this.getRootNode() === document);
            this.classList.add('hydrated');
          }, 0);
      }
    },
  );
}

/** A unique tag per test: happy-dom's registry cannot forget a definition. */
function freshTag(): string {
  seq += 1;
  return `x-standin-${seq}`;
}

afterEach(() => {
  seen.length = 0;
  hydratedInDocument.length = 0;
  document.body.innerHTML = '';
});

describe('preloadTeleportedStyles (hub#2162)', () => {
  it('hydrates one hidden instance per mode of every defined tag in the document, then cleans up', async () => {
    const tag = freshTag();
    defineStandIn(customElements, tag);

    await preloadTeleportedStyles({ doc: document, registry: customElements, tags: [tag] });

    expect(seen).toEqual(
      TELEPORTED_STYLE_MODES.map((mode) => ({ tag, mode, inDocument: true, hiddenContainer: true })),
    );
    // Removed only AFTER they rendered in the document: Stencil attaches the sheet to the root the
    // component renders in, so a probe pulled out before its first render proves nothing.
    expect(hydratedInDocument).toEqual(TELEPORTED_STYLE_MODES.map(() => true));
    expect(document.querySelector(tag)).toBeNull();
    expect(document.body.children.length).toBe(0);
  });

  it('preloads a tag that is only defined later, when it gets defined', async () => {
    const tag = freshTag();

    await preloadTeleportedStyles({ doc: document, registry: customElements, tags: [tag] });
    expect(seen).toEqual([]);

    defineStandIn(customElements, tag);
    await customElements.whenDefined(tag);
    await new Promise((r) => setTimeout(r, 20));

    expect(seen.map((s) => s.mode)).toEqual([...TELEPORTED_STYLE_MODES]);
    expect(document.querySelector(tag)).toBeNull();
  });

  it('does not leave the probes in the page when a component never hydrates', async () => {
    const tag = freshTag();
    defineStandIn(customElements, tag, false);

    await preloadTeleportedStyles({ doc: document, registry: customElements, tags: [tag], maxWaitMs: 30 });

    expect(seen).toHaveLength(TELEPORTED_STYLE_MODES.length);
    expect(document.querySelector(tag)).toBeNull();
    expect(document.body.children.length).toBe(0);
  });

  it('covers the overlays modules open inline and the fields they put inside them', () => {
    for (const tag of ['ion-alert', 'ion-action-sheet', 'ion-input', 'ion-textarea', 'ion-label', 'ion-list']) {
      expect(TELEPORTED_STYLE_TAGS).toContain(tag);
    }
    // Shadow-DOM components carry their styles with them: preloading them would only add noise.
    for (const tag of ['ion-modal', 'ion-button', 'ion-item', 'ion-content']) {
      expect(TELEPORTED_STYLE_TAGS).not.toContain(tag);
    }
    expect([...TELEPORTED_STYLE_MODES].sort()).toEqual(['ios', 'md']);
  });

  it('is started by the shell at boot', () => {
    // From the project root, not `import.meta.url`: under happy-dom that URL is an `http:` one.
    const main = readFileSync(join(process.cwd(), 'src', 'main.ts'), 'utf8');
    expect(main).toMatch(/import \{ preloadTeleportedStyles \} from '\.\/lib\/teleported-styles'/);
    expect(main).toMatch(/\bvoid preloadTeleportedStyles\(\)/);
    // After `use(IonicVue)`: that is what calls Ionic's `initialize()` → Stencil's `setMode`. Before
    // it the probes hydrate with a mode-less scope (`sc-ion-alert`) and register no sheet at all —
    // measured on the bench, where the first version of this fix ran too early and changed nothing.
    const ionicInit = main.search(/\.use\(IonicVue\b/);
    expect(ionicInit).toBeGreaterThan(-1);
    expect(main.search(/\bvoid preloadTeleportedStyles\(\)/)).toBeGreaterThan(ionicInit);
  });
});

describe('preload order (hub#2162 · visual baseline hub#1250)', () => {
  it('connects the probes in list order, so Stencil registers their sheets in that order', async () => {
    const outer = freshTag();
    const inner = freshTag();
    defineStandIn(customElements, outer);
    defineStandIn(customElements, inner);

    await preloadTeleportedStyles({ doc: document, registry: customElements, tags: [outer, inner] });

    expect(seen.map((s) => s.tag)).toEqual([outer, outer, inner, inner]);
  });

  it('lists every container before the fields it holds, the way the DOM connects a page', () => {
    // Stencil inserts each new scoped sheet BEFORE the previous ones in <head>, so the sheet
    // registered last has the lowest priority. Ionic's own sheets collide at equal specificity
    // (`.card-content-ios h2` vs `.sc-ion-label-ios-s h2`): a page connects the container first and
    // its fields after, and the visual baselines (hub#1250) pin that cascade. Measured with the
    // leaves first: the «Hub» tab of Settings grew its row titles from 16px to 17px.
    const at = (tag: string): number => TELEPORTED_STYLE_TAGS.indexOf(tag);
    const containers = ['ion-header', 'ion-footer', 'ion-card-content', 'ion-list', 'ion-item-group'];
    const leaves = ['ion-buttons', 'ion-searchbar', 'ion-label', 'ion-input', 'ion-input-otp', 'ion-textarea'];
    for (const container of containers) {
      for (const leaf of leaves) {
        expect(at(container), `${container} must precede ${leaf}`).toBeLessThan(at(leaf));
      }
    }
    expect(at('ion-card-content')).toBeLessThan(at('ion-list'));
    expect(at('ion-list')).toBeLessThan(at('ion-item-group'));
  });
});
