// hub#2162 — stylesheet loss when a module teleports an inline Ionic overlay.
//
// Module screens are Lit components rendered inside a shadow root. When a module opens an Ionic
// overlay INLINE (`<ion-alert>`, a modal with inline fields, ...) inside that shadow root, Stencil
// attaches the stylesheet of every non-shadow Ionic component (scoped or unencapsulated) to
// whichever root node it FIRST renders in, and never again. On present, Ionic teleports the
// overlay to `ion-app` in the document, where those sheets are missing unless the document already
// rendered that tag once, in that mode. Result: the overlay paints unstyled at the bottom of the
// page and its backdrop swallows clicks.
//
// Fix: at boot, hydrate one hidden instance of each affected tag, per mode (`ios`/`md`), in the
// DOCUMENT, so Stencil registers the sheets there before any module needs them, then remove the
// probes. Bench proof: `tests/e2e/ModuleInlineAlert.spec.ts`. Unit contract: `teleported-styles.test.ts`.

/** The two Ionic modes a component's stylesheet can be scoped to. */
export const TELEPORTED_STYLE_MODES = ['ios', 'md'] as const;

/**
 * Ionic 8 components that render WITHOUT their own shadow root (scoped or unencapsulated, per
 * @ionic/core 8 metadata) and therefore rely on a stylesheet Stencil attaches to whichever root
 * node first renders them. Deliberately excludes shadow-DOM components — their styles travel with
 * them wherever they render (ion-modal, ion-button, ion-item, ion-content, ...) — and structural
 * tags with side effects on connect (ion-app, ion-router*, ion-refresher, ion-infinite-scroll,
 * ion-item-sliding, ion-reorder-group, ion-radio-group).
 *
 * THE ORDER IS PART OF THE CONTRACT. Stencil inserts each new scoped sheet BEFORE the previous
 * ones in `<head>`, so the sheet registered last has the lowest priority, and Ionic's own sheets
 * collide at equal specificity (`.card-content-ios h2` vs `.sc-ion-label-ios-s h2`). A page
 * connects a container before the fields inside it, and the shell's visual baselines (hub#1250)
 * pin that cascade: containers first, then the fields they hold. With the leaves first, the row
 * titles of the «Hub» settings tab grew from 16px to 17px (measured, rv-2170).
 */
export const TELEPORTED_STYLE_TAGS: readonly string[] = [
  // Overlays a module opens inline (roots of their own).
  'ion-alert',
  'ion-action-sheet',
  'ion-loading',
  'ion-picker-legacy',
  // Containers, outermost first.
  'ion-header',
  'ion-footer',
  'ion-card-content',
  'ion-list',
  'ion-item-group',
  // Fields and leaves the containers hold.
  'ion-buttons',
  'ion-searchbar',
  'ion-label',
  'ion-input',
  'ion-input-otp',
  'ion-textarea',
];

export interface PreloadOptions {
  doc?: Document;
  registry?: CustomElementRegistry;
  tags?: readonly string[];
  maxWaitMs?: number;
}

const POLL_INTERVAL_MS = 16;
const DEFAULT_MAX_WAIT_MS = 3000;

function isHydrated(element: Element): boolean {
  return element.classList.contains('hydrated');
}

/**
 * Polls (setTimeout, not rAF — this also runs under happy-dom in tests) until every probe carries
 * the `hydrated` class Stencil adds after its first render, or `maxWaitMs` elapses.
 */
function waitForHydration(probes: readonly Element[], maxWaitMs: number): Promise<void> {
  return new Promise((resolve) => {
    const start = Date.now();
    const check = (): void => {
      if (probes.every(isHydrated) || Date.now() - start >= maxWaitMs) {
        resolve();
        return;
      }
      setTimeout(check, POLL_INTERVAL_MS);
    };
    check();
  });
}

/** Hydrates one hidden probe per tag/mode in `doc`, waits for hydration, then removes them. */
async function preloadTags(doc: Document, tags: readonly string[], maxWaitMs: number): Promise<void> {
  if (tags.length === 0 || !doc.body) return;

  const container = doc.createElement('div');
  container.hidden = true;
  container.setAttribute('aria-hidden', 'true');

  const probes: Element[] = [];
  for (const tag of tags) {
    for (const mode of TELEPORTED_STYLE_MODES) {
      const probe = doc.createElement(tag);
      probe.setAttribute('mode', mode);
      container.appendChild(probe);
      probes.push(probe);
    }
  }

  doc.body.appendChild(container);

  await waitForHydration(probes, maxWaitMs);

  container.remove();
}

/**
 * Boot-time, best-effort preload of the teleported-styles probes (see header comment). Never
 * throws: a failure here must not block the shell from starting.
 */
export function preloadTeleportedStyles(options: PreloadOptions = {}): Promise<void> {
  const doc = options.doc ?? globalThis.document;
  const registry = options.registry ?? globalThis.customElements;
  const tags = options.tags ?? TELEPORTED_STYLE_TAGS;
  const maxWaitMs = options.maxWaitMs ?? DEFAULT_MAX_WAIT_MS;

  if (!doc || !registry) return Promise.resolve();

  const definedTags: string[] = [];
  const pendingTags: string[] = [];
  for (const tag of tags) {
    if (registry.get(tag)) definedTags.push(tag);
    else pendingTags.push(tag);
  }

  // Tags not yet defined are preloaded once they are, but that never blocks boot.
  for (const tag of pendingTags) {
    registry
      .whenDefined(tag)
      .then(() => preloadTags(doc, [tag], maxWaitMs))
      .catch(() => {
        // Best-effort: a tag that fails to preload later must not surface anywhere.
      });
  }

  return preloadTags(doc, definedTags, maxWaitMs).catch(() => {
    console.warn('teleported-styles: failed to preload teleported Ionic styles');
  });
}
