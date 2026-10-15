// «Mark as paid» (INVOICE-F19), the same from a row of Invoices and from the open invoice: it asks first
// («Mark FACT-2026-000001 as paid?», «The payment is recorded with the current date and time.», as the old
// screen), then runs `invoice.invoice.mark_paid` by the invoice's id and says so; cancelled, nothing is
// sent. A refusal (paid or rectified meanwhile elsewhere) is kept to be read where the button was, in the
// server's words; a failure the server did not word says «Could not mark it as paid».
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { mountComposable } from '../__tests__/mount-invoice';
import { type MarkPaid, useMarkPaid } from './useMarkPaid';

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => {
  mocks.confirm.mockReset();
  vi.mocked(toastSuccess).mockClear();
});

const INVOICE = { id: 'i1', number: 'FACT-2026-000001' };

async function setup(locale: 'en' | 'es' = 'en') {
  let captured!: MarkPaid;
  const m = await mountComposable(() => {
    captured = useMarkPaid();
  }, { locale });
  return { ...m, paid: () => captured };
}

describe('useMarkPaid', () => {
  it('asks with the old words and, confirmed, marks the invoice by its id and says so', async () => {
    const s = await setup();
    mocks.confirm.mockResolvedValue(true);
    s.answer(200, { id: 'i1', status: 'paid' });
    expect(await s.paid().mark(INVOICE)).toBe(true);
    expect(mocks.confirm).toHaveBeenCalledWith({
      title: 'Mark FACT-2026-000001 as paid?',
      message: 'The payment is recorded with the current date and time.',
      confirmLabel: 'Mark as paid',
      cancelLabel: 'Cancel',
      confirmIcon: 'ion:checkmark-circle-outline',
      tone: 'primary',
    });
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/invoice/invoices/mark_paid', query: {}, body: { invoice_id: 'i1' } }]);
    expect(toastSuccess).toHaveBeenCalledWith('Invoice FACT-2026-000001 marked as paid');
    expect(s.paid().refused.value).toBeNull();
  });

  it('cancelled sends nothing', async () => {
    const s = await setup();
    mocks.confirm.mockResolvedValue(false);
    expect(await s.paid().mark(INVOICE)).toBe(false);
    expect(s.sent()).toEqual([]);
  });

  it('a refusal is kept in the server’s words; a fresh try clears it', async () => {
    const s = await setup();
    mocks.confirm.mockResolvedValue(true);
    s.answer(409, { error: { code: 'invoice.cannot_mark_paid', message: 'This invoice cannot be marked as paid.' } });
    expect(await s.paid().mark(INVOICE)).toBe(false);
    expect(s.paid().refused.value).toBe('This invoice cannot be marked as paid.');
    s.answer(500, { error: { code: 'internal_error', message: 'Internal error' } });
    await s.paid().mark(INVOICE);
    expect(s.paid().refused.value).toBe('Could not mark it as paid');
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    mocks.confirm.mockResolvedValue(false);
    await s.paid().mark(INVOICE);
    expect(mocks.confirm.mock.calls[0][0]).toMatchObject({
      title: '¿Marcar FACT-2026-000001 como pagada?',
      message: 'El cobro se registra con la fecha y la hora de ahora.',
      confirmLabel: 'Marcar pagada',
      cancelLabel: 'Cancelar',
    });
  });
});
