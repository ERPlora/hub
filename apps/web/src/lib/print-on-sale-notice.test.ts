// hub#2210 — charging with no printer set up greeted the cashier with a RED toast that read like a
// fault and named the sale by its internal id («El tique de la venta 32e31586-d3a9-… está en
// espera…»). Nothing had failed: the receipt is queued and comes out on its own once a printer is
// set up (hub#1731). So the waiting receipt is told in the informative tone, and no warning of the
// sale's receipt puts the internal id in front of a person — it is the sale just charged at this
// till (hub#1980), and a uuid tells nobody which one it was.
//
// Pinned by key, colour and the ABSENCE of the id in what is painted, never by the prose (ADR-0055).
import { afterEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { i18n } from '../i18n';
import { saleTicketFailureNotice, saleTicketWithoutFiscalNotice, type PrintNotice } from './print-on-sale-notice';

const SALE_ID = '32e31586-d3a9-4a90-985f-1cb10e160a2b';

const painted = (n: PrintNotice): string =>
  (i18n.global.t as unknown as (k: string, p?: Record<string, unknown>) => string)(n.messageKey, n.params);

describe('the receipt waiting for a printer (hub#2210)', () => {
  it('is told in the informative tone, not as an error', () => {
    const n = saleTicketFailureNotice({
      saleId: SALE_ID,
      error: 'no printer set up for this station',
      awaitingHost: true,
    });
    expect(n.messageKey).toBe('print.ticketWaitingForPrinter');
    expect(n.color).toBe('primary');
  });

  it('stays up long enough to read the way out', () => {
    // toastInfo's 2.6 s is shorter than it takes to read a sentence with an instruction in it.
    const n = saleTicketFailureNotice({ saleId: SALE_ID, error: 'x', awaitingHost: true });
    expect(n.duration).toBeGreaterThanOrEqual(6000);
  });
});

describe('the receipt that did NOT come out is still an error', () => {
  it('lost on the way', () => {
    const n = saleTicketFailureNotice({ saleId: SALE_ID, error: 'printer_offline' });
    expect(n.messageKey).toBe('print.ticketFailed');
    expect(n.color).toBe('danger');
  });

  it('never composed', () => {
    const n = saleTicketFailureNotice({ saleId: SALE_ID, error: 'sale_document_timeout', notComposed: true });
    expect(n.messageKey).toBe('print.ticketNotComposed');
    expect(n.color).toBe('danger');
  });
});

describe('the receipt out without its VeriFactu QR (hub#1867)', () => {
  it('is a warning, not an error: the paper is already in the customer’s hand', () => {
    const n = saleTicketWithoutFiscalNotice();
    expect(n.messageKey).toBe('print.ticketWithoutFiscal');
    expect(n.color).toBe('warning');
    expect(n.duration).toBeGreaterThanOrEqual(6000);
  });
});

describe('no warning about the sale’s receipt shows its internal id', () => {
  const locale = i18n.global.locale;
  const before = locale.value;
  afterEach(() => {
    locale.value = before;
  });

  const notices: [string, PrintNotice][] = [
    ['waiting', saleTicketFailureNotice({ saleId: SALE_ID, error: 'x', awaitingHost: true })],
    ['failed', saleTicketFailureNotice({ saleId: SALE_ID, error: 'printer_offline' })],
    ['not composed', saleTicketFailureNotice({ saleId: SALE_ID, error: 'x', notComposed: true })],
    ['without fiscal', saleTicketWithoutFiscalNotice()],
  ];

  for (const lang of ['en', 'es'] as const) {
    for (const [name, n] of notices) {
      it(`${name} (${lang})`, () => {
        locale.value = lang;
        const text = painted(n);
        // The key resolved to a sentence of the catalogue, not to itself.
        expect(text).not.toBe(n.messageKey);
        expect(text).not.toContain(SALE_ID);
        // Not even carried: a sentence added later that asks for {saleId} would get it filled.
        expect(n.params ?? {}).not.toHaveProperty('saleId');
        // vue-i18n paints a placeholder with nothing to fill it as an empty gap («la venta  está»),
        // so the catalogue sentence itself must not ask for the id.
        const raw = (i18n.global.getLocaleMessage(lang) as Record<string, Record<string, string>>).print[
          n.messageKey.replace('print.', '')
        ];
        expect(raw).toBeTypeOf('string');
        expect(raw).not.toContain('{saleId}');
      });
    }
  }
});

// `main.ts` is the shell's boot and cannot be mounted in a unit test (see
// main-asks-for-notices.hub1732.test.ts): the wire is read from the source, scoped to the call.
const MAIN = readFileSync(fileURLToPath(new URL('../main.ts', import.meta.url)), 'utf8');

function printOnSaleCall(source: string): string {
  const start = source.indexOf('bootPrintOnSale(getClient()');
  expect(start).toBeGreaterThan(-1);
  const end = source.indexOf('\n});', start);
  expect(end).toBeGreaterThan(start);
  return source.slice(start, end);
}

describe('the shell paints the receipt warnings through these notices', () => {
  it('both callbacks use them, and none picks its own colour or key', () => {
    const call = printOnSaleCall(MAIN);
    expect(call).toContain('saleTicketFailureNotice(');
    expect(call).toContain('saleTicketWithoutFiscalNotice(');
    expect(call).not.toContain('toastError');
    expect(call).not.toContain("'print.ticket");
    expect(call).not.toContain('saleId }');
    // The tone and the time are the notice's: a literal colour here (or the default 2.6 s) would
    // paint the waiting receipt red again while every test above stays green.
    expect(call.match(/, n\.color, n\.duration\)/g)).toHaveLength(2);
    expect(call).not.toMatch(/'(danger|warning|primary|success|medium)'/);
  });

  it('and the region asserted really is only that call', () => {
    expect(MAIN).toContain('bootPrintComanda(getClient()');
    expect(printOnSaleCall(MAIN)).not.toContain('bootPrintComanda');
  });
});
