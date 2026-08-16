// @vitest-environment node
// hub#988 — the words the NFC badge reader puts in front of a user.
//
// Two of them interrupt the till, so they have to be worth it, and they have to say what to DO.
// «NFC is disabled» describes a state; «turn it on to read cards by tapping them» describes the
// gesture that makes the reader work — and the difference is whether the salon concludes the
// feature is broken and goes back to typing the number by hand.
//
// The third sentence is the one that is NOT here, and that absence is a decision: a device with no
// reader says nothing at all. There is nothing for the user to do about it, the USB reader keeps
// working exactly as before, and an apology on every till without a chip is noise about a
// non-event.
import { describe, expect, it } from 'vitest';

import en from './locales/en';
import es from './locales/es';

type Catalogue = {
  badge: Record<string, string>;
  employeeForm: Record<string, string>;
};

const EN = en as unknown as Catalogue;
const ES = es as unknown as Catalogue;

/** Every key this feature added, in the section it lives in. */
const NEW_KEYS: ReadonlyArray<[keyof Catalogue, string]> = [
  ['badge', 'nfcDisabled'],
  ['badge', 'nfcRandomUid'],
  ['employeeForm', 'badgeNfcHelp'],
  ['employeeForm', 'badgeNfcSetHelp'],
];

describe('the NFC badge copy', () => {
  it('exists in Spanish as well as in English', () => {
    // Binding rule of the monorepo: English is the SOURCE, and every visible string ships with its
    // `es` translation. A missing one does not fail anywhere — vue-i18n falls back to the English
    // and the till quietly speaks two languages at once.
    for (const [section, key] of NEW_KEYS) {
      expect(EN[section][key], `en.${section}.${key}`).toBeTruthy();
      expect(ES[section][key], `es.${section}.${key}`).toBeTruthy();
    }
  });

  it('says nothing at all about a device that simply has no reader', () => {
    // The refusal that gets no sentence. If one ever appears here, the loop that swallows
    // `nfc_unavailable` has been given something to say and every desktop install will say it.
    for (const catalogue of [EN, ES]) {
      expect(Object.keys(catalogue.badge)).not.toContain('nfcUnavailable');
    }
  });

  it('tells the user what to do, not what the device is', () => {
    // A cashier reading this is holding up a queue. Both sentences name the next gesture: flip the
    // switch, or reach for a different card.
    expect(EN.badge.nfcDisabled).toMatch(/turn it on/i);
    expect(ES.badge.nfcDisabled).toMatch(/enci[eé]ndelo/i);
    expect(EN.badge.nfcRandomUid).toMatch(/another card/i);
    expect(ES.badge.nfcRandomUid).toMatch(/otra/i);
  });

  it('offers the tap without taking the swipe away', () => {
    // The USB reader is what a counter actually has, and the number stays typeable for an iButton
    // or an engraved tag. The tap is an addition — a help text that only mentioned it would read
    // as "your reader no longer works here".
    expect(EN.employeeForm.badgeNfcHelp).toMatch(/tap/i);
    expect(EN.employeeForm.badgeNfcHelp).toMatch(/swipe/i);
    expect(EN.employeeForm.badgeNfcHelp).toMatch(/type the number/i);
    expect(ES.employeeForm.badgeNfcHelp).toMatch(/acerca/i);
    expect(ES.employeeForm.badgeNfcHelp).toMatch(/lector/i);
    expect(ES.employeeForm.badgeNfcHelp).toMatch(/teclear/i);
  });

  it('keeps the reader-only wording, for every till that has no chip', () => {
    // The NFC variants are shown INSTEAD of these, not in place of them in the file: a device with
    // no reader must never be told to tap anything.
    for (const catalogue of [EN, ES]) {
      expect(catalogue.employeeForm.badgeHelp).toBeTruthy();
      expect(catalogue.employeeForm.badgeSetHelp).toBeTruthy();
    }
    expect(EN.employeeForm.badgeHelp).not.toMatch(/\btap\b/i);
    expect(ES.employeeForm.badgeHelp).not.toMatch(/acerca/i);
  });

  it('does not put a platform noun in front of a cashier', () => {
    // ADR-0254: «UID», «NFC adapter», «reader mode» are our words, not theirs. «NFC» itself stays —
    // it is the word printed on the toggle the user has to find in their own settings.
    for (const [section, key] of NEW_KEYS) {
      for (const catalogue of [EN, ES]) {
        const text = catalogue[section][key];
        for (const noun of [/\buid\b/i, /\breader mode\b/i, /\bmodo lector\b/i, /\badapter\b/i]) {
          expect(text, `${section}.${key}`).not.toMatch(noun);
        }
      }
    }
  });
});
