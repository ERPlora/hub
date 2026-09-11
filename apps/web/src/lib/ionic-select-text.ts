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
// same registration-time hook, as `fill` → `mode="md"` in `./ionic-fill` (hub#1060). Why it has to
// be at `customElements.define` time and not CSS or an observer is written in full there.
//
// WHY A LIVE GETTER AND NOT A COPIED STRING: the hub changes language on the fly (`i18n/index.ts`
// → `setLocale` publishes it with no reload) and Ionic reads `this.okText` when the dialog OPENS,
// not when the element connects. Writing the translation into the element at connect time would
// leave every already-mounted select stuck in the language it booted with — which is the shape of
// half the i18n defects this shell has had (hub#781, hub#1241).
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

/**
 * Gives one element a localized DEFAULT for a button it did not label itself.
 *
 * It is an own accessor over Stencil's prototype accessor: reads answer in today's language, and
 * a later write (a module setting `.okText`) removes it and goes back to Ionic's own prop, so the
 * shell normalizes without ever overriding.
 */
function installLocalizedDefault(el: HTMLElement, button: (typeof BUTTONS)[number]): void {
  const { prop, attribute, ionic } = button;
  if (el.hasAttribute(attribute)) return; // labelled in markup
  if ((el as unknown as Record<string, unknown>)[prop] !== ionic) return; // labelled from JS

  Object.defineProperty(el, prop, {
    configurable: true,
    enumerable: true,
    get: () => textFor(button),
    set(value: string) {
      delete (el as unknown as Record<string, unknown>)[prop]; // back to Ionic's own accessor
      (el as unknown as Record<string, unknown>)[prop] = value;
    },
  });
}

type SelectControl = HTMLElement & { connectedCallback?: () => void };

function patchConstructor(ctor: CustomElementConstructor): void {
  const proto = ctor.prototype as SelectControl & Record<symbol, unknown>;
  if (!proto || Object.prototype.hasOwnProperty.call(proto, PATCHED)) return;
  Object.defineProperty(proto, PATCHED, { value: true, enumerable: false });

  const original = proto.connectedCallback;
  proto.connectedCallback = function patchedConnectedCallback(this: SelectControl): void {
    // Re-connecting is harmless: the checks inside see the label this already carries and bail.
    for (const button of BUTTONS) installLocalizedDefault(this, button);
    original?.call(this);
  };
}

/**
 * Makes every selection dialog of the app — the shell's own views, the `ok-*` of OutfitKit and the
 * Web Components of every installed module, shadow roots included — label its buttons in the
 * user's language.
 *
 * ⚠️ Must run BEFORE anything registers `ion-select`, i.e. before `@ionic/vue` is even imported.
 * That is why `main.ts` pulls in `./lib/ionic-select-text.boot` at the top instead of calling this
 * from its body. Booting late cannot be fixed silently, so it is reported.
 */
export function bootIonicSelectText(
  translate: SelectTextResolver = shellSelectText,
  tags: readonly string[] = SELECT_TEXT_CONTROLS,
): void {
  resolve = translate;
  reported.clear(); // a new catalogue deserves a new chance to complain
  const tooLate = patchIonicOnDefine(tags, patchConstructor);
  if (tooLate.length > 0) {
    // Invisible by nature — the dialog just opens in English — so it has to be said out loud.
    console.error(
      `[ionic-select-text] ${tooLate.join(', ')} was already registered when the shell tried to ` +
        'hook it: every selection dialog will show CANCEL / OK in English (hub#1736). Import ' +
        '`./lib/ionic-select-text.boot` before `@ionic/vue` in main.ts.',
    );
  }
}
