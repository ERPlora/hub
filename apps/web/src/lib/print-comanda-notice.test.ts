// hub#2238 — a restaurant with no printer set up for the kitchen (or the bar) got a RED toast,
// styled as an error, every time an order was fired: «the kitchen order is waiting…». Nothing was
// lost — the docket is queued and comes out on its own once that station's printer is set up
// (hub#1731) — but, unlike the receipt of hub#2210, the kitchen does not start cooking until it
// comes out. So the waiting docket is a WARNING (amber: someone has to act), not an error and not
// a plain info; the docket that really did not print stays red.
//
// Pinned by key, colour and duration, never by the prose (ADR-0055).
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { i18n } from '../i18n';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';
import { comandaFailureNotice } from './print-comanda-notice';
import type { PrintNotice } from './print-on-sale-notice';

// The notice names the station and the unlabelled docket in the app's language (hub#2257): it is
// handed the catalogue, and these tests run in English unless they say otherwise.
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

describe('the kitchen order waiting for a printer (hub#2238)', () => {
  // Built per test: the station is named in the language of the moment (beforeEach sets English).
  const waitingNotice = () =>
    comandaFailureNotice(
      {
        orderId: 'k-1',
        role: 'kitchen',
        label: 'Table 4',
        error: 'no printer set up for this station',
        awaitingHost: true,
      },
      words,
    );

  it('is a warning, not an error', () => {
    const waiting = waitingNotice();
    expect(waiting.messageKey).toBe('print.comandaWaitingForPrinter');
    expect(waiting.color).toBe('warning');
  });

  it('stays up long enough to read the way out', () => {
    // toastError's 4.5 s (and the default 2.6 s) is shorter than a sentence with an instruction.
    expect(waitingNotice().duration).toBeGreaterThanOrEqual(6000);
  });

  it('names the table and the station', () => {
    expect(waitingNotice().params).toEqual({ label: 'Table 4', station: 'kitchen' });
  });
});

describe('the kitchen order that did NOT print is still an error', () => {
  it('keeps the red, and names the table and the station', () => {
    const n = comandaFailureNotice({ orderId: 'k-1', role: 'bar', label: 'Table 4', error: 'printer_offline' }, words);
    expect(n.messageKey).toBe('print.comandaFailed');
    expect(n.color).toBe('danger');
    expect(n.params).toEqual({ label: 'Table 4', station: 'bar' });
  });

  it('stays up long enough to read the way out, like the waiting one (hub#2257)', () => {
    // Its sentence now carries an instruction: toastError's 4.5 s is shorter than that, and the
    // docket that really did not print must not vanish before the one that is only waiting.
    const n = comandaFailureNotice({ orderId: 'k-1', role: 'kitchen', label: 'Table 4', error: 'x' }, words);
    expect(n.duration).toBeGreaterThanOrEqual(6000);
  });
});

describe('a docket with no label of its own (takeaway, no table plan)', () => {
  for (const [lang, floor] of [
    ['en', en.print.comandaDefaultLabel],
    ['es', es.print.comandaDefaultLabel],
  ] as const) {
    it(`is named by the translated fallback, waiting or failed (${lang})`, () => {
      locale.value = lang;
      const base = { orderId: 'k-1', role: 'kitchen', label: '', error: 'x' };
      expect(comandaFailureNotice({ ...base, awaitingHost: true }, words).params).toMatchObject({ label: floor });
      expect(comandaFailureNotice(base, words).params).toMatchObject({ label: floor });
    });
  }
});

describe('the waiting docket tells the way out in both languages', () => {
  for (const [lang, station] of [
    ['en', en.print.stationKitchen],
    ['es', es.print.stationKitchen],
  ] as const) {
    it(lang, () => {
      locale.value = lang;
      const n = comandaFailureNotice(
        { orderId: 'k-1', role: 'kitchen', label: 'Table 4', error: 'x', awaitingHost: true },
        words,
      );
      const text = painted(n);
      expect(text).not.toBe(n.messageKey);
      expect(text).toContain('Table 4');
      expect(text).toContain(station);
      expect(text).not.toContain('{');
    });
  }
});

// hub#2257 — «No se imprimió la comanda de Mesa 4 (kitchen): el runtime rechazó el encolado». Two
// things a waiter cannot act on: the machine's reason (or the literal «sin impresora» on a hub in
// English) and the station in the code's own word. The reason stays in the log (print-comanda.ts);
// the station is named in the app's language, as the «Printing status» panel does.
describe('the kitchen order that did not print does not show the machine’s reason (hub#2257)', () => {
  const REASON = 'el runtime rechazó el encolado · printer_offline';

  for (const lang of ['en', 'es'] as const) {
    it(`not in what is painted (${lang})`, () => {
      locale.value = lang;
      const n = comandaFailureNotice({ orderId: 'k-1', role: 'kitchen', label: 'Table 4', error: REASON }, words);
      const text = painted(n);
      expect(text).not.toBe(n.messageKey);
      expect(text).toContain('Table 4');
      expect(text).not.toContain(REASON);
      expect(text).not.toContain('{');
      expect(n.params ?? {}).not.toHaveProperty('error');
      // Nor asked for by the sentence: a placeholder with nothing to fill it paints an empty gap.
      const catalogue = (i18n.global.getLocaleMessage(lang) as Record<string, Record<string, string>>).print;
      for (const key of ['comandaFailed', 'comandaWaitingForPrinter'] as const) {
        expect(catalogue[key]).toBeTypeOf('string');
        expect(catalogue[key]).not.toContain('{error}');
      }
    });

    it(`says what to do after the fact, not only the fact (${lang})`, () => {
      locale.value = lang;
      const text = painted(
        comandaFailureNotice({ orderId: 'k-1', role: 'kitchen', label: 'Table 4', error: REASON }, words),
      );
      // «did not print.» and then the way out: a second sentence, never the fact alone.
      expect(text.split(/(?<=\.)\s+/).filter(Boolean).length).toBeGreaterThanOrEqual(2);
    });
  }
});

describe('both warnings name the station in the app’s language (hub#2257)', () => {
  const cases = [
    ['kitchen', 'stationKitchen'],
    ['bar', 'stationBar'],
  ] as const;
  for (const lang of ['en', 'es'] as const) {
    for (const [role, key] of cases) {
      for (const awaitingHost of [true, false]) {
        it(`${role}, ${awaitingHost ? 'waiting' : 'failed'} (${lang})`, () => {
          locale.value = lang;
          const n = comandaFailureNotice({ orderId: 'k-1', role, label: 'Table 4', error: 'x', awaitingHost }, words);
          const catalogue = lang === 'en' ? en : es;
          expect(n.params).toMatchObject({ station: catalogue.print[key] });
          expect(painted(n)).toContain(catalogue.print[key]);
        });
      }
    }
  }

  it('in Spanish, never the code’s word', () => {
    locale.value = 'es';
    for (const [role] of cases) {
      for (const awaitingHost of [true, false]) {
        const n = comandaFailureNotice({ orderId: 'k-1', role, label: 'Mesa 4', error: 'x', awaitingHost }, words);
        expect(painted(n)).not.toMatch(new RegExp(`\\b${role}\\b`));
      }
    }
  });

  it('a station the catalogue does not know is named as it is, never as a broken key', () => {
    const n = comandaFailureNotice({ orderId: 'k-1', role: 'grill', label: 'Table 4', error: 'x' }, words);
    expect(n.params).toMatchObject({ station: 'grill' });
    expect(painted(n)).toContain('grill');
    expect(painted(n)).not.toContain('print.station');
  });
});

// `main.ts` is the shell's boot and cannot be mounted in a unit test (see
// main-asks-for-notices.hub1732.test.ts): the wire is read from the source, scoped to the call.
const MAIN = readFileSync(fileURLToPath(new URL('../main.ts', import.meta.url)), 'utf8');

function comandaFailureCallback(source: string): string {
  const start = source.indexOf('bootPrintComanda(getClient()');
  expect(start).toBeGreaterThan(-1);
  const from = source.indexOf('onFailure:', start);
  const end = source.indexOf('\n  },', from);
  expect(from).toBeGreaterThan(start);
  expect(end).toBeGreaterThan(from);
  return source.slice(from, end);
}

describe('the shell paints the kitchen order warnings through this notice', () => {
  it('picks neither its own colour nor its own key', () => {
    const call = comandaFailureCallback(MAIN);
    expect(call).toContain('comandaFailureNotice(');
    expect(call).not.toContain('toastError');
    expect(call).not.toContain("'print.comandaWaitingForPrinter'");
    expect(call).not.toContain("'print.comandaFailed'");
    // The tone and the time are the notice's: a literal colour here (or the default 2.6 s) would
    // paint the waiting docket red again while every test above stays green.
    expect(call).toMatch(/, n\.color, n\.duration\)/);
    expect(call).not.toMatch(/'(danger|warning|primary|success|medium)'/);
  });

  it('paints the sentence the notice picked, naming the table and the station', () => {
    const call = comandaFailureCallback(MAIN);
    // Without the params the toast reads «{label} ({role})»; without t() it reads the raw key.
    expect(call).toContain('i18n.global.t(n.messageKey, n.params');
    // The notice is handed the catalogue: it names the station and a docket with no label of its
    // own in the app's language (hub#2257), never the code's word or a blank.
    expect(call).toContain('comandaFailureNotice(f, i18n.global)');
  });

  it('never paints the failure’s own reason (hub#2257)', () => {
    const call = comandaFailureCallback(MAIN);
    expect(call).not.toContain('.error');
    expect(call).not.toContain('f.role');
  });

  it('and the region asserted really is that callback', () => {
    const call = comandaFailureCallback(MAIN);
    expect(call.startsWith('onFailure:')).toBe(true);
    expect(call).not.toContain('notify:');
    expect(call).not.toContain('bootPrintOnSale');
  });
});
