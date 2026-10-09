// kitchen#168 — what the till that cancelled a round is told when the VOID slip did not come out.
// The comanda's notice says «the order is on the kitchen screen»; for a void that is the wrong way
// out (the card has just LEFT the screen): the only thing that stops the dish now is a voice. So the
// void has its own two sentences, with the comanda's tones: waiting = warning, lost = error.
//
// Pinned by key, colour and duration, never by the prose (ADR-0055); and the boot's wire is read
// from `main.ts`, which cannot be mounted in a unit test.
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { i18n } from '../i18n';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';
import { voidFailureNotice } from './print-comanda-notice';
import type { PrintNotice } from './print-on-sale-notice';

const words = i18n.global as unknown as { t: (k: string) => string };
const locale = i18n.global.locale;
let before: typeof locale.value;
beforeEach(() => {
  before = locale.value;
  locale.value = 'en';
});
afterEach(() => {
  locale.value = before;
});

const painted = (n: PrintNotice): string =>
  (i18n.global.t as unknown as (k: string, p?: Record<string, unknown>) => string)(n.messageKey, n.params);

const failure = (over: Record<string, unknown> = {}) => ({
  orderId: 'k-1',
  role: 'kitchen',
  label: 'Table 4',
  error: 'void_slip_not_delivered',
  ...over,
});

describe('the void slip that did not print (kitchen#168)', () => {
  it('is an error, with a sentence of its own, not the comanda one', () => {
    const n = voidFailureNotice(failure(), words);
    expect(n.messageKey).toBe('print.voidFailed');
    expect(n.color).toBe('danger');
    expect(n.duration).toBeGreaterThanOrEqual(6000);
  });

  it('waiting for a printer is a warning, with its own sentence', () => {
    const n = voidFailureNotice(failure({ awaitingHost: true }), words);
    expect(n.messageKey).toBe('print.voidWaitingForPrinter');
    expect(n.color).toBe('warning');
    expect(n.duration).toBeGreaterThanOrEqual(6000);
  });

  for (const [lang, station] of [
    ['en', en.print.stationKitchen],
    ['es', es.print.stationKitchen],
  ] as const) {
    for (const awaitingHost of [false, true]) {
      it(`names the table and the station, never the machine's reason (${lang}, ${awaitingHost ? 'waiting' : 'failed'})`, () => {
        locale.value = lang;
        const text = painted(voidFailureNotice(failure({ awaitingHost }), words));
        expect(text).toContain('Table 4');
        expect(text).toContain(station);
        expect(text).not.toContain('void_slip_not_delivered');
        expect(text).not.toMatch(/[{}]/);
      });
    }
  }

  it('a slip with no label of its own is named by the translated fallback', () => {
    locale.value = 'es';
    const text = painted(voidFailureNotice(failure({ label: '' }), words));
    expect(text).toContain(es.print.comandaDefaultLabel);
  });
});

describe('the words on the void slip exist in English and in Spanish', () => {
  for (const [lang, catalogue] of [
    ['en', en],
    ['es', es],
  ] as const) {
    it(lang, () => {
      const p = catalogue.print as Record<string, string>;
      expect(p.voidLabel).toContain('{label}');
      expect(p.voidLabelBare).toBeTruthy();
      // The bare word is the start of the labelled one: the paper reads the same with or without a table.
      expect(p.voidLabel.startsWith(p.voidLabelBare)).toBe(true);
      expect(p.voidFailed).toContain('{station}');
      expect(p.voidWaitingForPrinter).toContain('{station}');
    });
  }

  it('the Spanish slip does not say it in English', () => {
    expect(es.print.voidLabelBare).not.toBe(en.print.voidLabelBare);
  });
});

// hub#2640 — the slip of ONE voided dish: the round's sentence («that order is no longer to be
// made») would send the cook to bin the whole table. Its own sentences name the dish.
describe('the void slip of one dish that did not print (hub#2640)', () => {
  it('is an error with the dish sentence, not the round one', () => {
    const n = voidFailureNotice(failure({ dish: 'Croquetas' }), words);
    expect(n.messageKey).toBe('print.voidDishFailed');
    expect(n.color).toBe('danger');
    expect(n.duration).toBeGreaterThanOrEqual(6000);
  });

  it('waiting for a printer is a warning with the dish sentence', () => {
    const n = voidFailureNotice(failure({ dish: 'Croquetas', awaitingHost: true }), words);
    expect(n.messageKey).toBe('print.voidDishWaitingForPrinter');
    expect(n.color).toBe('warning');
    expect(n.duration).toBeGreaterThanOrEqual(6000);
  });

  for (const [lang, station] of [
    ['en', en.print.stationKitchen],
    ['es', es.print.stationKitchen],
  ] as const) {
    for (const awaitingHost of [false, true]) {
      it(`names the dish, the table and the station (${lang}, ${awaitingHost ? 'waiting' : 'failed'})`, () => {
        locale.value = lang;
        const text = painted(voidFailureNotice(failure({ dish: 'Croquetas', awaitingHost }), words));
        expect(text).toContain('Croquetas');
        expect(text).toContain('Table 4');
        expect(text).toContain(station);
        expect(text).not.toContain('void_slip_not_delivered');
        expect(text).not.toMatch(/[{}]/);
      });
    }
  }
});

describe('the words on the slip of one voided dish exist in English and in Spanish (hub#2640)', () => {
  for (const [lang, catalogue] of [
    ['en', en],
    ['es', es],
  ] as const) {
    it(lang, () => {
      const p = catalogue.print as Record<string, string>;
      expect(p.voidDishLabel).toContain('{label}');
      expect(p.voidDishLabel.startsWith(p.voidDishLabelBare)).toBe(true);
      // On paper it must not read like the slip of a whole round.
      expect(p.voidDishLabelBare).not.toBe(p.voidLabelBare);
      expect(p.voidDishFailed).toContain('{dish}');
      expect(p.voidDishFailed).toContain('{station}');
      expect(p.voidDishWaitingForPrinter).toContain('{dish}');
      expect(p.voidDishWaitingForPrinter).toContain('{station}');
    });
  }

  it('the Spanish slip does not say it in English', () => {
    expect(es.print.voidDishLabelBare).not.toBe(en.print.voidDishLabelBare);
  });
});

const MAIN = readFileSync(fileURLToPath(new URL('../main.ts', import.meta.url)), 'utf8');

function voidBoot(source: string): string {
  const start = source.indexOf('bootPrintVoid(getClient()');
  expect(start).toBeGreaterThan(-1);
  const end = source.indexOf('\n});', start);
  expect(end).toBeGreaterThan(start);
  return source.slice(start, end);
}

describe('the shell boots the void slip and paints its warnings through this notice', () => {
  it('prints by the same door as the comanda', () => {
    expect(voidBoot(MAIN)).toContain('print: (req) =>');
  });

  it('hands the catalogue over for the word on the paper', () => {
    expect(voidBoot(MAIN)).toMatch(/\bt: \(key, params\) =>/);
  });

  it('picks neither its own colour nor its own key, and never paints the reason', () => {
    const call = voidBoot(MAIN);
    expect(call).toContain('voidFailureNotice(f, i18n.global)');
    // hub#2494: painted by presentPrintNotice (tone, time, sentence and Retry: its own test).
    expect(call).toContain('presentPrintNotice(voidFailureNotice(f, i18n.global))');
    expect(call).not.toContain('toast(');
    expect(call).not.toMatch(/'(danger|warning|primary|success|medium)'/);
    expect(call).not.toContain('.error');
  });
});
