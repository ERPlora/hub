// hub#1736 — the buttons of Ionic's selection dialogs speak the app's language.
//
// Picking a customer, a service, a professional or a filter opens an `<ion-select>` dialog whose
// two buttons Ionic labels from `cancelText` / `okText`, and whose defaults are the English
// literals `'Cancel'` and `'OK'` (`@ionic/core`, select.js). Ionic exposes NO global config key
// for them — `setupConfig` covers `backButtonText` and little else — so the only per-screen fix is
// «every select in the product passes both attributes».
//
// That rule cannot hold here. The selects a merchant actually uses are inside module Web
// Components, shipped from 27 separate repos and, once the marketplace opens, by authors we never
// review; a module that forgets the attribute shows English buttons inside a Spanish till and
// nothing warns. So the shell fixes the DEFAULT, once, for everyone — the same reasoning, and the
// same registry hook, as `fill` → `mode="md"` in `./ionic-fill` (hub#1060). Why it has to act on
// the element class and not through CSS or an observer is written in full there.
//
// WHY AT `open()` AND NOT AT CONNECT TIME (hub#2226): the hub changes language on the fly
// (`i18n/index.ts` → `setLocale` publishes it with no reload) and Ionic reads `this.okText` when
// the dialog OPENS. hub#1736 installed a live per-instance getter at connect time, but Stencil strips
// every own property of the element when it connects (its «upgrade» of props set before the
// definition) and writes the value through its setter once: the getter was evaluated a single time
// and every mounted select stayed in the language it was painted in. So the labels are decided
// right before each dialog opens — the same wrapper as the default interface of hub#2223
// (`./ionic-select-interface`), which also means it works on a tag that was registered first.
import { i18n } from '../i18n';

import { patchIonicOnDefine } from './ionic-registry-hook';

/** The Ionic controls whose default button labels are English literals. */
export const SELECT_TEXT_CONTROLS = ['ion-select'] as const;

/** The prop Ionic reads for each button, its attribute spelling, its English default and our key. */
const BUTTONS = [
  { prop: 'cancelText', attribute: 'cancel-text', ionic: 'Cancel', key: 'selectDialog.cancel' },
  { prop: 'okText', attribute: 'ok-text', ionic: 'OK', key: 'selectDialog.ok' },
] as const;

/** The two buttons of a selection dialog, by the prop name Ionic reads. */
export type SelectTextProp = (typeof BUTTONS)[number]['prop'];

/** Answers what a button should say RIGHT NOW — called every time a dialog opens. */
export type SelectTextResolver = (prop: SelectTextProp) => string;

/** Marks a prototype we already patched, so a second boot is a no-op instead of a double call. */
const PATCHED = Symbol.for('erplora.ionic-select-text.patched');
/** Reported once per button and boot: a dialog that falls back to English IS the bug this fixes. */
const reported = new Set<string>();

/** Says out loud that a button fell back to English — once, not on every dialog that opens. */
function report(key: string, ionic: string, error?: unknown): void {
  if (reported.has(key)) return;
  reported.add(key);
  console.error(
    `[ionic-select-text] \`${key}\` did not answer: the selection dialogs will show Ionic's ` +
      `English \`${ionic}\` (hub#1736).`,
    error ?? '',
  );
}

/** The shell catalogue, read at call time so the active language always wins (ADR-0055). */
export function shellSelectText(prop: SelectTextProp): string {
  const { key } = BUTTONS.find((button) => button.prop === prop) ?? BUTTONS[0];
  return i18n.global.t(key);
}

let resolve: SelectTextResolver = shellSelectText;

/**
 * The text of a button, or Ionic's English default if the catalogue cannot answer.
 *
 * A dialog whose labels throw is a control the cashier cannot use, so the fallback is deliberate —
 * but it is the defect itself, so it is said out loud instead of silently shipping English.
 */
function textFor({ prop, ionic, key }: (typeof BUTTONS)[number]): string {
  try {
    const text = resolve(prop);
    if (typeof text === 'string' && text.length > 0 && text !== key) return text;
  } catch (error) {
    report(key, ionic, error);
    return ionic;
  }
  report(key, ionic);
  return ionic;
}

/** Per element, the labels the SHELL wrote last — anything else in there is the author's. */
const shellWrote = new WeakMap<SelectControl, Partial<Record<SelectTextProp, string>>>();

type SelectControl = HTMLElement &
  Partial<Record<SelectTextProp, string>> & { open?: (ev?: Event) => Promise<unknown> };

/**
 * Writes today's language into the buttons the element did not label itself.
 *
 * What counts as the author's choice: the `ok-text` / `cancel-text` attribute (even when it says
 * `OK`), and any value written from JS other than Ionic's default or what the shell wrote last —
 * so the shell localizes a DEFAULT and never overrides.
 */
function applyLocalizedDefaults(el: SelectControl): void {
  const wrote = shellWrote.get(el) ?? {};
  for (const button of BUTTONS) {
    const { prop, attribute, ionic } = button;
    if (el.hasAttribute(attribute)) continue; // labelled in markup
    const current = el[prop];
    if (current !== (wrote[prop] ?? ionic)) continue; // labelled from JS, before or after mounting

    const next = textFor(button);
    wrote[prop] = next;
    if (current !== next) el[prop] = next;
  }
  shellWrote.set(el, wrote);
}

function patchConstructor(ctor: CustomElementConstructor): void {
  const proto = ctor.prototype as SelectControl & Record<symbol, unknown>;
  if (!proto || Object.prototype.hasOwnProperty.call(proto, PATCHED)) return;
  const original = proto.open;
  if (typeof original !== 'function') {
    // Not the `ion-select` this was written against: say so instead of guessing.
    console.error('[ionic-select-text] the element has no `open()` to wrap (hub#1736).');
    return;
  }
  Object.defineProperty(proto, PATCHED, { value: true, enumerable: false });

  proto.open = function patchedOpen(this: SelectControl, ev?: Event): Promise<unknown> {
    try {
      applyLocalizedDefaults(this);
    } catch (error) {
      // The dialog must open no matter what: English buttons beat a select that is dead.
      console.error('[ionic-select-text] localizing the buttons failed; opening as is', error);
    }
    return original.call(this, ev);
  };
}

/**
 * Makes every selection dialog of the app — the shell's own views, the `ok-*` of OutfitKit and the
 * Web Components of every installed module, shadow roots included — label its buttons in the
 * user's language, the one active when the dialog opens.
 *
 * Imported from `main.ts` next to its twins (`./ionic-select-text.boot`). It wraps a method, not a
 * lifecycle callback, so it also works on a tag that is already registered.
 */
export function bootIonicSelectText(
  translate: SelectTextResolver = shellSelectText,
  tags: readonly string[] = SELECT_TEXT_CONTROLS,
): void {
  resolve = translate;
  reported.clear(); // a new catalogue deserves a new chance to complain
  const registered = patchIonicOnDefine(tags, patchConstructor);
  for (const tag of registered) {
    const ctor = globalThis.customElements?.get(tag);
    if (ctor) patchConstructor(ctor);
  }
}
