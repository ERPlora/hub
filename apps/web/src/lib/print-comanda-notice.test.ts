// hub#2238 — a restaurant with no printer set up for the kitchen (or the bar) got a RED toast,
// styled as an error, every time an order was fired: «the kitchen order is waiting…». Nothing was
// lost — the docket is queued and comes out on its own once that station's printer is set up
// (hub#1731) — but, unlike the receipt of hub#2210, the kitchen does not start cooking until it
// comes out. So the waiting docket is a WARNING (amber: someone has to act), not an error and not
// a plain info; the docket that really did not print stays red.
//
// Pinned by key, colour and duration, never by the prose (ADR-0055).
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { i18n } from '../i18n';
import { comandaFailureNotice } from './print-comanda-notice';
import type { PrintNotice } from './print-on-sale-notice';

const FLOOR = 'the floor';

const painted = (n: PrintNotice): string =>
  (i18n.global.t as unknown as (k: string, p?: Record<string, unknown>) => string)(n.messageKey, n.params);

describe('the kitchen order waiting for a printer (hub#2238)', () => {
  const waiting = comandaFailureNotice(
    {
      orderId: 'k-1',
      role: 'kitchen',
      label: 'Table 4',
      error: 'no printer set up for this station',
      awaitingHost: true,
    },
    FLOOR,
  );

  it('is a warning, not an error', () => {
    expect(waiting.messageKey).toBe('print.comandaWaitingForPrinter');
    expect(waiting.color).toBe('warning');
  });

  it('stays up long enough to read the way out', () => {
    // toastError's 4.5 s (and the default 2.6 s) is shorter than a sentence with an instruction.
    expect(waiting.duration).toBeGreaterThanOrEqual(6000);
  });

  it('names the table and the station', () => {
    expect(waiting.params).toEqual({ label: 'Table 4', role: 'kitchen' });
  });
});

describe('the kitchen order that did NOT print is still an error', () => {
  it('keeps the red and the reason', () => {
    const n = comandaFailureNotice({ orderId: 'k-1', role: 'bar', label: 'Table 4', error: 'printer_offline' }, FLOOR);
    expect(n.messageKey).toBe('print.comandaFailed');
    expect(n.color).toBe('danger');
    expect(n.params).toEqual({ label: 'Table 4', role: 'bar', error: 'printer_offline' });
  });
});

describe('a docket with no label of its own (takeaway, no table plan)', () => {
  it('is named by the fallback, waiting or failed', () => {
    const base = { orderId: 'k-1', role: 'kitchen', label: '', error: 'x' };
    expect(comandaFailureNotice({ ...base, awaitingHost: true }, FLOOR).params).toMatchObject({ label: FLOOR });
    expect(comandaFailureNotice(base, FLOOR).params).toMatchObject({ label: FLOOR });
  });
});

describe('the waiting docket tells the way out in both languages', () => {
  for (const lang of ['en', 'es'] as const) {
    it(lang, () => {
      const before = i18n.global.locale.value;
      i18n.global.locale.value = lang;
      try {
        const n = comandaFailureNotice(
          { orderId: 'k-1', role: 'kitchen', label: 'Table 4', error: 'x', awaitingHost: true },
          FLOOR,
        );
        const text = painted(n);
        expect(text).not.toBe(n.messageKey);
        expect(text).toContain('Table 4');
        expect(text).toContain('kitchen');
        expect(text).not.toContain('{');
      } finally {
        i18n.global.locale.value = before;
      }
    });
  }
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
    // A docket with no label of its own is named by the translated fallback, never left blank.
    expect(call).toContain("comandaFailureNotice(f, i18n.global.t('print.comandaDefaultLabel'))");
  });

  it('and the region asserted really is that callback', () => {
    const call = comandaFailureCallback(MAIN);
    expect(call.startsWith('onFailure:')).toBe(true);
    expect(call).not.toContain('notify:');
    expect(call).not.toContain('bootPrintOnSale');
  });
});
