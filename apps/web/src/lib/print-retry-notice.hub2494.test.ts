// hub#2494 — with the printer switched off or out of paper, the receipt or the docket used to be
// lost without a word. Now the paper's failure carries a Retry (print-on-sale, print-comanda,
// print-void) and this is how the till sees it: a notice that STAYS until somebody acts (a 4.5 s
// toast is gone before the cashier turns round from the customer) with a «Retry» button that
// prints that same paper again — what Square, Toast and Lightspeed do on the POS.
//
// Pinned by key, tone and button, never by the prose (ADR-0055).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { toast } = vi.hoisted(() => ({ toast: vi.fn(async (..._args: unknown[]) => undefined) }));
vi.mock('./toast', () => ({ toast }));

import { i18n } from '../i18n';
import { comandaFailureNotice, voidFailureNotice } from './print-comanda-notice';
import { presentPrintNotice, saleTicketFailureNotice, saleTicketWithoutFiscalNotice } from './print-on-sale-notice';

const SALE_ID = '32e31586-d3a9-4a90-985f-1cb10e160a2b';
const raw = (lang: 'en' | 'es', key: string): unknown =>
  (i18n.global.getLocaleMessage(lang) as Record<string, Record<string, unknown>>).print?.[key];

describe('the receipt whose printer did not answer', () => {
  it('is an error that stays up until the cashier acts, with the Retry it came with', () => {
    const retry = vi.fn(async () => undefined);
    const n = saleTicketFailureNotice({ saleId: SALE_ID, error: 'unreachable', printerFailed: true, retry });
    expect(n.messageKey).toBe('print.ticketPrinterFailed');
    expect(n.color).toBe('danger');
    expect(n.duration).toBe(0);
    expect(n.retry).toBe(retry);
  });

  it('a receipt lost for any other reason keeps its sentence and its time, with no button', () => {
    const n = saleTicketFailureNotice({ saleId: SALE_ID, error: 'receipt_not_delivered' });
    expect(n.messageKey).toBe('print.ticketFailed');
    expect(n.duration).toBeGreaterThan(0);
    expect(n.retry).toBeUndefined();
  });

  for (const lang of ['en', 'es'] as const) {
    it(`has its sentence and the button word in ${lang}, without the sale id`, () => {
      const sentence = raw(lang, 'ticketPrinterFailed');
      expect(sentence).toBeTypeOf('string');
      expect(sentence).not.toContain('{saleId}');
      expect(raw(lang, 'retry')).toBeTypeOf('string');
    });
  }

  it('the two languages are really two', () => {
    expect(raw('en', 'ticketPrinterFailed')).not.toBe(raw('es', 'ticketPrinterFailed'));
    expect(raw('en', 'retry')).not.toBe(raw('es', 'retry'));
  });
});

describe('the docket and the void slip whose printer did not answer', () => {
  const words = { t: (k: string) => k };
  const base = { orderId: 'k-1', role: 'kitchen', label: 'Mesa 4', error: 'unreachable', printerFailed: true };

  it('the docket keeps its sentence, stays up and carries the Retry', () => {
    const retry = vi.fn(async () => undefined);
    const n = comandaFailureNotice({ ...base, retry }, words);
    expect(n.messageKey).toBe('print.comandaFailed');
    expect(n.color).toBe('danger');
    expect(n.duration).toBe(0);
    expect(n.retry).toBe(retry);
  });

  it('the void slip too, for the round and for one dish', () => {
    const retry = vi.fn(async () => undefined);
    const round = voidFailureNotice({ ...base, retry }, words);
    expect(round.messageKey).toBe('print.voidFailed');
    expect(round.duration).toBe(0);
    expect(round.retry).toBe(retry);
    const dish = voidFailureNotice({ ...base, dish: 'Croquetas', retry }, words);
    expect(dish.messageKey).toBe('print.voidDishFailed');
    expect(dish.duration).toBe(0);
    expect(dish.retry).toBe(retry);
  });

  it('waiting for a printer is not a printer failure: no button, its own time', () => {
    const n = comandaFailureNotice({ ...base, printerFailed: undefined, awaitingHost: true }, words);
    expect(n.retry).toBeUndefined();
    expect(n.duration).toBeGreaterThan(0);
  });
});

describe('presentPrintNotice paints the notice', () => {
  const locale = i18n.global.locale;
  const before = locale.value;
  beforeEach(() => toast.mockClear());
  afterEach(() => {
    locale.value = before;
  });

  it('with its sentence, tone and time, and a Retry button in the app language that retries', async () => {
    locale.value = 'es';
    const retry = vi.fn(async () => undefined);
    await presentPrintNotice(saleTicketFailureNotice({ saleId: SALE_ID, error: 'x', printerFailed: true, retry }));

    expect(toast).toHaveBeenCalledTimes(1);
    const [message, color, duration, id, action] = toast.mock.calls[0]!;
    expect(message).toBe(raw('es', 'ticketPrinterFailed'));
    expect(color).toBe('danger');
    expect(duration).toBe(0);
    expect(id).toBeUndefined();
    const button = action as { text: string; handler: () => void };
    expect(button.text).toBe(raw('es', 'retry'));

    button.handler();
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it('a notice with nothing to retry has no button', async () => {
    await presentPrintNotice(saleTicketWithoutFiscalNotice());
    const call = toast.mock.calls[0]!;
    expect(call[1]).toBe('warning');
    expect(call[4]).toBeUndefined();
  });

  it('fills the sentence with its parameters', async () => {
    locale.value = 'en';
    const n = comandaFailureNotice(
      {
        orderId: 'k-1',
        role: 'kitchen',
        label: 'Table 4',
        error: 'x',
        printerFailed: true,
        retry: async () => undefined,
      },
      i18n.global,
    );
    await presentPrintNotice(n);
    expect(toast.mock.calls[0]![0]).toContain('Table 4');
  });

  it('a Retry that throws is logged, not left as an unhandled rejection', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const retry = vi.fn(async () => {
      throw new Error('boom');
    });
    await presentPrintNotice(saleTicketFailureNotice({ saleId: SALE_ID, error: 'x', printerFailed: true, retry }));
    (toast.mock.calls[0]![4] as { handler: () => void }).handler();
    await new Promise((r) => setTimeout(r, 0));
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});
