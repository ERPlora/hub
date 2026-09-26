// hub#2223 — a single-choice select closes the moment an option is picked.
//
// `<ion-select>` opens an `alert` unless told otherwise (`@ionic/core`, select.js:
// `this.interface = 'alert'`), and the alert only commits the choice in the handler of its OK
// button: tapping an option just marks a radio. Picking one category, one status or one
// professional costs a second tap, and whoever taps outside instead believes they chose and loses
// the value. The `popover` interface dismisses on the click of the option itself
// (`select-popover.js` → `dismissParentPopover()`), which is how every dropdown behaves in the
// tools a merchant already knows — and it is what the shell's own views and the modules that do
// declare an interface already use.
//
// Ionic has no global config key for the default interface, and the selects a merchant uses live
// in module Web Components shipped from 27 separate repos (and tomorrow from marketplace authors we
// never review). So the shell fixes the DEFAULT once, for everyone, through the same registry hook
// as `fill` → `mode="md"` (hub#1060, `./ionic-fill`) and the localized dialog buttons (hub#1736).
//
// WHY AT `open()` AND NOT AT CONNECT TIME:
//   · Stencil strips every own property of the element when it connects (its «upgrade» of props
//     set before the definition), so a per-instance accessor installed there is gone before the
//     first render — measured against the real `ion-select`, not assumed.
//   · Ionic reads `this.interface` only when the dialog opens (`open()` → `createOverlay()`), and a
//     module can toggle `multiple` on a select that is already mounted. Deciding at open time
//     follows it for free.
//   · `open` is a plain prototype method, not a lifecycle callback, so wrapping it works even on a
//     tag that was registered before this booted.
//
// Only SINGLE choice changes. A `multiple` select keeps the alert: choosing several things needs a
// confirm button, and the popover has none. A popover also needs the click to anchor to; a
// programmatic `open()` with no event makes Ionic fall back to the alert by itself (with its own
// warning), so nothing ends up worse than before.
//
// What counts as the author's choice: any `interface` attribute (`alert` included), and any value
// written from JS other than Ionic's default. The one case that cannot be told apart is a module
// writing `.interface = 'alert'` from JS — letter for letter the default — and no module does.
import { patchIonicOnDefine } from './ionic-registry-hook';

/** The Ionic control whose default interface needs a confirm tap for a single choice. */
export const SELECT_INTERFACE_CONTROLS = ['ion-select'] as const;

/** Ionic's own default, assigned in the `ion-select` constructor. */
const IONIC_DEFAULT = 'alert';
/** Closes on pick for a single choice. */
const SINGLE_CHOICE = 'popover';

/** Marks a prototype we already patched, so a second boot is a no-op instead of a double wrap. */
const PATCHED = Symbol.for('erplora.ionic-select-interface.patched');

/** Per element, the interface the SHELL wrote last — anything else in there is the author's. */
const shellChoice = new WeakMap<SelectControl, string>();

type SelectControl = HTMLElement & {
  interface?: string;
  multiple?: boolean;
  open?: (ev?: Event) => Promise<unknown>;
};

/** Points the element at the right interface for what it is about to open, unless its author chose. */
function applyDefaultInterface(el: SelectControl): void {
  if (el.hasAttribute('interface')) return; // chosen in markup, `alert` included
  const current = el.interface;
  const ours = shellChoice.get(el);
  if (current !== (ours ?? IONIC_DEFAULT)) return; // chosen from JS, before or after mounting

  const next = el.multiple ? IONIC_DEFAULT : SINGLE_CHOICE;
  shellChoice.set(el, next);
  if (current !== next) el.interface = next;
}

function patchConstructor(ctor: CustomElementConstructor): void {
  const proto = ctor.prototype as SelectControl & Record<symbol, unknown>;
  if (!proto || Object.prototype.hasOwnProperty.call(proto, PATCHED)) return;
  const original = proto.open;
  if (typeof original !== 'function') {
    // Not the `ion-select` this was written against: say so instead of guessing.
    console.error('[ionic-select-interface] the element has no `open()` to wrap (hub#2223).');
    return;
  }
  Object.defineProperty(proto, PATCHED, { value: true, enumerable: false });

  proto.open = function patchedOpen(this: SelectControl, ev?: Event): Promise<unknown> {
    try {
      applyDefaultInterface(this);
    } catch (error) {
      // The dialog must open no matter what: an alert that needs OK beats a select that is dead.
      console.error('[ionic-select-interface] choosing the interface failed; opening as is', error);
    }
    return original.call(this, ev);
  };
}

/**
 * Makes every single-choice select of the app — the shell's own views, the `ok-*` of OutfitKit and
 * the Web Components of every installed module, shadow roots included — close on pick.
 *
 * Imported from `main.ts` next to its twins (`./ionic-select-interface.boot`). Unlike them it also
 * works on a tag that is already registered: it wraps a method, not a lifecycle callback.
 */
export function bootIonicSelectInterface(tags: readonly string[] = SELECT_INTERFACE_CONTROLS): void {
  const registered = patchIonicOnDefine(tags, patchConstructor);
  for (const tag of registered) {
    const ctor = globalThis.customElements?.get(tag);
    if (ctor) patchConstructor(ctor);
  }
}
