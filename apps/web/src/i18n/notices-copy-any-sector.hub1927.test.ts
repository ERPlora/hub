// @vitest-environment node
// hub#1927 — the words that ask to be allowed to warn somebody have to fit EVERY business.
//
// The sheet in front of Android's notification dialog is shown once per install, on the device
// that becomes a print host — a salon's front-desk tablet as much as a restaurant's till. It used
// to say «let us warn you about new orders / when an order comes into the kitchen», so the owner
// of a hair salon was asked for a permission in the words of a trade that is not hers, said
// «not now», and after two refusals Android never asks again (hub#1732). Google Play's reviewer,
// who lands on a salon, read the same thing.
//
// The row on System › your printer and the confirmation after turning the notices back on belong
// to the same permission and had the same problem, so all of them are pinned here: none of them
// may name a sector (kitchen, order, table, appointment…). Naming what the device will really
// warn about is fine only while it is true for every hub, and today no single example is.
import { describe, expect, it } from 'vitest';

import en from './locales/en';
import es from './locales/es';

type Catalogue = { system: { notices: Record<string, string> } };

const EN = (en as unknown as Catalogue).system.notices;
const ES = (es as unknown as Catalogue).system.notices;

/** Every sentence of the notices permission that a user reads. */
const USER_FACING_KEYS = [
  'primerHeader',
  'primerMessage',
  'blockedTitle',
  'blockedDetail',
  'blockedInSettings',
  'turnedOn',
] as const;

/** Words that belong to one trade and read as nonsense in another. */
const SECTOR_WORDS: Record<'en' | 'es', RegExp> = {
  en: /\b(orders?|kitchen|tables?|diners?|appointments?|bookings?|clients?|patients?)\b/i,
  es: /\b(comandas?|cocina|pedidos?|mesas?|comensal(es)?|citas?|reservas?|clientas?|pacientes?)\b/i,
};

describe('the notices permission copy (hub#1927)', () => {
  it('exists in English and in Spanish', () => {
    for (const key of USER_FACING_KEYS) {
      expect(EN[key], `en.system.notices.${key}`).toBeTruthy();
      expect(ES[key], `es.system.notices.${key}`).toBeTruthy();
    }
  });

  it.each(USER_FACING_KEYS)('«%s» does not speak the language of one sector', (key) => {
    expect(EN[key]).not.toMatch(SECTOR_WORDS.en);
    expect(ES[key]).not.toMatch(SECTOR_WORDS.es);
  });
});
