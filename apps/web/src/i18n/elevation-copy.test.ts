// @vitest-environment node
// hub#363 — the words of the approval dialog.
//
// This dialog is read out loud across a counter, by a cashier who is holding up a queue, to a
// manager who is walking over. It has one job: say what to DO. «Permission denied» describes the
// state of a permission check; «ask a manager to enter their PIN» describes the gesture that
// unblocks the till, and the difference between the two is whether the shop ends up sharing one
// credential to avoid the dialog altogether.
//
// The other half of this suite guards a decision made in the RUNTIME. hub#361 answers an unknown
// name, a wrong PIN and a deactivated user with the same code and the same sentence, on purpose, so
// that a dialog at the counter cannot be used to find out who works here. That is only true while
// the screen keeps it true: a helpful «no such user» written here would undo it from the outside,
// with every Rust test still green.
import { describe, expect, it } from 'vitest';

import en from './locales/en';
import es from './locales/es';

type Catalogue = { elevation: Record<string, string> };

const EN = (en as unknown as Catalogue).elevation;
const ES = (es as unknown as Catalogue).elevation;

/** The platform's nouns (ADR-0254, hub#365): none of them belongs in front of a cashier. */
const PLATFORM_NOUNS: readonly RegExp[] = [
  /\bhubs?\b/i,
  /\bclouds?\b/i,
  /\bnube\b/i,
  /\bmodules?\b/i,
  /\bm[oó]dulos?\b/i,
  /\bmarketplace\b/i,
  /\btokens?\b/i,
  /\bendpoints?\b/i,
  /\belevation\b/i,
  /\belevaci[oó]n\b/i,
  /\bpermission_denied\b/i,
];

describe('the approval dialog says what to do', () => {
  it('asks for the gesture, naming who and what', () => {
    expect(EN.lead).toBe('Ask a manager to enter their PIN to approve this.');
    expect(ES.lead).toBe('Pide a un encargado que introduzca su PIN para aprobarlo.');
  });

  it('never describes the refusal instead of the way out', () => {
    for (const [lang, copy] of [['en', EN], ['es', ES]] as const) {
      expect(copy.lead, `${lang}.lead reads as an error, not an instruction`).not.toMatch(
        /denied|denegad|forbidden|prohibid|error|unauthori[sz]ed|no autorizad/i,
      );
    }
  });

  it('never puts our architecture in front of the counter', () => {
    for (const [key, value] of [...Object.entries(EN), ...Object.entries(ES)]) {
      for (const noun of PLATFORM_NOUNS) {
        expect(value, `elevation.${key}: «${value}» says ${noun.source}`).not.toMatch(noun);
      }
    }
  });
});

describe('what a refused PIN is told, and what it must never reveal', () => {
  it('has ONE sentence for the three refusals the runtime made identical', () => {
    // Unknown name, wrong PIN, deactivated user → `hub.elevation.rejected` → this, and only this.
    expect(EN.rejected).toBe(
      'Those details do not approve this. Check the name and the PIN, and try again.',
    );
    expect(ES.rejected).toBe(
      'Esos datos no aprueban esto. Revisa el nombre y el PIN, y vuelve a intentarlo.',
    );
  });

  it('never names which of the three it was', () => {
    // Each of these would answer a question the runtime refuses to answer: does this person exist,
    // and do they still work here. A dialog anyone can open must not become the staff directory.
    const TELLS: readonly RegExp[] = [
      /unknown/i,
      /not found/i,
      /no such/i,
      /does ?n[o']?t exist/i,
      /deactivat/i,
      /disabled/i,
      /inactive/i,
      /no existe/i,
      /desactivad/i,
      /no encontrad/i,
      /dado de baja/i,
      /inactiv[oa]/i,
    ];
    for (const [lang, copy] of [['en', EN.rejected], ['es', ES.rejected]] as const) {
      for (const tell of TELLS) {
        expect(copy, `${lang}.rejected leaks ${tell.source}`).not.toMatch(tell);
      }
    }
  });

  it('keeps the throttle refusal apart from the wrong-PIN one', () => {
    // Two guards, two sentences. If both said the same thing, a manager locked out by the
    // brute-force guard would keep retyping a PIN that is correct, and nothing on screen would name
    // the one thing that fixes it: waiting.
    //
    // hub#2285: the throttle is the login pinpad's lock, so the dialog says the pinpad's sentence.
    for (const [lang, locale, copy] of [['en', en, EN.rejected], ['es', es, ES.rejected]] as const) {
      const lock = [locale.login.pinTooManyAttempts, locale.login.pinTooManyAttemptsNoWait];
      for (const sentence of lock) expect(sentence, lang).not.toBe(copy);
      for (const sentence of lock) expect(sentence, lang).toMatch(lang === 'en' ? /wait/i : /espera/i);
    }
  });

  it('sends «not approved with a PIN» to an account, not to another PIN', () => {
    // Rule 5: `admin` territory is not approved at the counter. Whoever reads this has to be told
    // the door is a different one, or they will keep fetching managers.
    expect(EN.notElevable).toMatch(/sign in|account/i);
    expect(ES.notElevable).toMatch(/cuenta/i);
  });
});

describe('nothing reaches the reader untranslated', () => {
  it('has an `es` for every `en`, and no orphans', () => {
    expect(Object.keys(ES).sort()).toEqual(Object.keys(EN).sort());
  });

  it('has no `es` left in English', () => {
    const untranslated = Object.entries(EN)
      .filter(([key, value]) => ES[key] === value)
      .map(([key]) => key);
    expect(untranslated).toEqual([]);
  });
});
