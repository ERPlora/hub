// hub#1060 — the shell makes `fill` paint a box wherever it is declared.
//
// Ionic implements `fill` ONLY in `md` mode — from its own source (`@ionic/core`, input.js):
//
//     const hasOutlineFill = mode === 'md' && this.fill === 'outline';
//
// and the shell pins `mode: 'ios'` on purpose (ADR-0143, `main.ts`). So `fill="outline"` is a
// silent no-op: no box, no border, no surface — just a floating label over the page background.
// Nothing throws, nothing warns; the form looks like static text. It cost us the one screen that
// unblocks invoicing (hub#760) and it keeps coming back on the next screen.
//
// The rule until now (amendment to ADR-0143, 2026-08-11) was «every control that declares `fill`
// declares `mode="md"` too», guarded by a source test in each product. That guard reaches our own
// source and nothing else. The forms a merchant actually types into are module Web Components,
// shipped from 25 separate repos — and, once the marketplace opens, from authors we do not review.
// A platform cannot ask every module author to remember an attribute whose absence is invisible:
// it has to make the default correct. So the shell normalizes it once, for everyone.
//
// WHY AT REGISTRATION TIME, and not with CSS or an observer:
//   · CSS — a module renders its `<ion-input>` inside its own shadow root, which no document
//     stylesheet can reach. The `ok-*` of OutfitKit are the same. Global CSS fixes the shell only.
//   · MutationObserver — Ionic resolves the mode ONCE, in its own `connectedCallback`
//     (`initialize()` → `setMode(elm => elm.mode || elm.getAttribute('mode') …)`), and caches it in
//     the Stencil host ref. An observer fires after the element is connected, so the attribute
//     would land after the render that needed it.
//   · Patching the prototype after `customElements.define` — a no-op. The HTML spec captures the
//     lifecycle callbacks INSIDE `define`; later prototype writes are never seen. (Measured, not
//     assumed: it is what the `too late` case in the tests reproduces.)
//   · Wrapping `customElements.define` therefore is the hook: it runs before the class is
//     registered, it is synchronous (no `whenDefined` microtask racing the first render) and it
//     works on the element, so it crosses shadow boundaries.
//
// This does NOT change ADR-0143: the shell is still `ios`, and only the three form controls that
// explicitly ask for a `fill` render Material — which is exactly what the per-control rule already
// mandated, one control at a time. The source guards (`theme/ionic-fill-needs-md.test.ts` here,
// its twin in the SaaS, `erplora validate` for modules) stay: keeping the attribute explicit in
// code we own is still better, and they are what tells us the day Ionic changes its mind.

/** Ionic controls whose `fill` is a no-op outside `md`. `ion-button`/`ion-chip` honour it in `ios`. */
export const FILL_MODE_CONTROLS = ['ion-input', 'ion-select', 'ion-textarea'] as const;

/** Marks a prototype we already patched, so a second boot is a no-op instead of a double call. */
const PATCHED = Symbol.for('erplora.ionic-fill-mode.patched');
/** Holds, on the registry, the set of tags to normalize. */
const WATCHED = Symbol.for('erplora.ionic-fill-mode.watched');
/** Marks the registry whose `define` we already wrapped. */
const WRAPPED = Symbol.for('erplora.ionic-fill-mode.wrapped');

type IonicControl = HTMLElement & { fill?: string; mode?: string; connectedCallback?: () => void };

/**
 * A control that asks for a `fill` box and has not been told otherwise renders as Material, the
 * only mode where Ionic draws that box. Ionic reads `elm.mode || elm.getAttribute('mode')`, so
 * both spellings of an explicit mode are respected: this normalizes, it does not override.
 */
function normalizeFillMode(el: IonicControl): void {
  const wantsFill = el.fill != null || el.hasAttribute('fill');
  if (!wantsFill) return;
  if (el.mode != null || el.hasAttribute('mode')) return;
  el.setAttribute('mode', 'md');
}

function patchConstructor(ctor: CustomElementConstructor): void {
  const proto = ctor.prototype as IonicControl & Record<symbol, unknown>;
  if (!proto || Object.prototype.hasOwnProperty.call(proto, PATCHED)) return;
  Object.defineProperty(proto, PATCHED, { value: true, enumerable: false });

  const original = proto.connectedCallback;
  proto.connectedCallback = function patchedConnectedCallback(this: IonicControl): void {
    normalizeFillMode(this);
    original?.call(this);
  };
}

/**
 * Makes `fill` paint a box on every Ionic form control of the app — the shell's own views, the
 * `ok-*` of OutfitKit and the Web Components of every installed module, shadow roots included.
 *
 * ⚠️ Must run BEFORE anything registers those tags, i.e. before `@ionic/vue` is even imported
 * (it registers on import, `defineContainer()` → `defineCustomElement()`). That is why `main.ts`
 * pulls in `./lib/ionic-fill.boot` as its very first import instead of calling this from its body:
 * ES modules evaluate every import before the first statement of the importing module.
 * Booting late cannot be fixed silently, so it is reported.
 */
export function bootIonicFillMode(tags: readonly string[] = FILL_MODE_CONTROLS): void {
  const registry = globalThis.customElements;
  if (!registry) return; // SSR / unit tests without a DOM: nothing to normalize.

  const watched = ((registry as unknown as Record<symbol, Set<string>>)[WATCHED] ??= new Set());
  for (const tag of tags) watched.add(tag);

  const tooLate = tags.filter((tag) => registry.get(tag));
  if (tooLate.length > 0) {
    // Invisible by nature — the form simply renders without a box — so it has to be said out loud.
    console.error(
      `[ionic-fill] ${tooLate.join(', ')} was already registered when the shell tried to hook it: ` +
        'every `fill` on those controls will render with no box (hub#1060). Import ' +
        '`./lib/ionic-fill.boot` before `@ionic/vue` in main.ts.',
    );
  }

  if (Object.prototype.hasOwnProperty.call(registry, WRAPPED)) return;
  const original = registry.define.bind(registry);
  Object.defineProperty(registry, WRAPPED, { value: true, enumerable: false });
  registry.define = (name: string, ctor: CustomElementConstructor, options?: ElementDefinitionOptions) => {
    if (watched.has(name)) patchConstructor(ctor);
    return original(name, ctor, options);
  };
}
