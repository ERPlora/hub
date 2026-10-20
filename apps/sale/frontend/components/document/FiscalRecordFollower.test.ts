// VeriFactu's record of a sale's fiscal document (VERIFACTU-F19): `verifactu.record.by_invoice`, followed live.
// Renderless: the document mounts it only while VeriFactu is on, the person may read its records and the sale has
// a fiscal document (`useLive` has no «skip»). It hands up the record (none while VeriFactu has none) or why it
// could not be read, and says nothing until the first answer.
import { describe, expect, it } from 'vitest';

import { errorFrame, flush, mountSale } from '../../__tests__/mount-sale';
import FiscalRecordFollower from './FiscalRecordFollower.vue';

const OP = 'verifactu.record.by_invoice';
const RECORD = { qr_svg: 'data:image/svg+xml;base64,PHN2Zy8+', qr_url: 'https://prewww2.aeat.es/x', csv: '' };

async function setup() {
  const m = await mountSale(FiscalRecordFollower, { props: { invoiceId: 'inv1' } });
  const call = await m.live();
  return { ...m, call };
}

describe('FiscalRecordFollower', () => {
  it('follows the record of its fiscal document and hands it up; nothing before the first answer', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ invoice_id: 'inv1' }]);
    expect(s.wrapper.emitted('change')).toBeUndefined();
    await s.result(OP, { record: RECORD });
    expect(s.wrapper.emitted('change')?.at(-1)).toEqual([{ record: RECORD, error: null }]);
  });

  it('a document VeriFactu has no record of yet hands up none', async () => {
    const s = await setup();
    await s.result(OP, { record: null });
    expect(s.wrapper.emitted('change')?.at(-1)).toEqual([{ record: null, error: null }]);
  });

  it('a failed read hands up why', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId(OP), 'internal_error'));
    await flush();
    const [state] = s.wrapper.emitted('change')?.at(-1) as [{ record: unknown; error: { message: string } }];
    expect(state.record).toBeUndefined();
    expect(state.error.message).toBe('msg internal_error');
  });
});
