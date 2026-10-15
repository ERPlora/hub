// «Cancel record» (VERIFACTU-F30): «Cancel the record of <number>», the note that this is only for an invoice issued
// by error (a refund is a rectifying invoice), «Reason» (required) and «Cancel the record». Without a reason
// nothing is sent; with one it runs `verifactu.record.cancel` and says so; a refusal is read inside the window.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountVerifactu } from '../__tests__/mount-verifactu';
import CancelRecordModal from './CancelRecordModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const RECORD = { id: 'r1', invoice_number: 'TICKET-2026-000001' };

async function setup() {
  const m = await mountVerifactu(CancelRecordModal, { props: { open: true, record: RECORD } });
  const submit = () => click(m.inDoc('verifactu-cancel-submit'));
  return { ...m, submit };
}

describe('CancelRecordModal', () => {
  it('says what it is for, and that a refund is not this', async () => {
    const s = await setup();
    expect(s.find('verifactu-cancel').attributes('aria-label')).toBe('Cancel the record of TICKET-2026-000001');
    expect(s.find('verifactu-cancel-note').text()).toContain('issued by error');
  });

  it('asks for the reason before sending anything', async () => {
    const s = await setup();
    await s.submit();
    expect(s.sent()).toEqual([]);
    expect(s.inDoc('verifactu-cancel-error')?.textContent).toContain('Write why the invoice was issued by error.');
  });

  it('cancels the record with the reason and says so', async () => {
    const s = await setup();
    await ionValue(s.find('verifactu-cancel-reason').element, 'Duplicated ticket', 'ionInput');
    s.answer(200, { record: { id: 'r2', invoice_number: 'TICKET-2026-000001' }, already: false });
    await s.submit();
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/verifactu/records/cancel', query: {}, body: { record_id: 'r1', reason: 'Duplicated ticket' } },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Cancellation of TICKET-2026-000001 sealed: it goes out with the next pass.');
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a refusal is read inside the window', async () => {
    const s = await setup();
    await ionValue(s.find('verifactu-cancel-reason').element, 'x', 'ionInput');
    s.answer(409, { error: { code: 'verifactu.cannot_cancel', message: 'This record cannot be cancelled.' } });
    await s.submit();
    expect(s.find('verifactu-cancel').text()).toContain('This record cannot be cancelled.');
  });
});
