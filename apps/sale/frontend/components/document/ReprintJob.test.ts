// «Reprint» on a row of Sales (SALE-F29; the old hidden viewer): the sale's paper is painted out of
// sight, always a «DUPLICATE», printed through the browser as soon as it is there, and the job ends
// (`done`). If the document cannot be loaded or the browser refuses, «Could not print» says so.
import { toastError } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { errorFrame, flush, mountSale } from '../../__tests__/mount-sale';
import { printPaper } from '../../lib/print';
import { saleOut, SETTINGS } from './__tests__/fixtures';
import ReceiptPaper from './ReceiptPaper.vue';
import ReprintJob from './ReprintJob.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastError: vi.fn(() => Promise.resolve()),
}));
vi.mock('../../lib/print', () => ({ printPaper: vi.fn() }));

beforeEach(() => {
  vi.mocked(printPaper).mockReset();
  vi.mocked(toastError).mockClear();
});

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountSale(ReprintJob, { props: { saleId: 's1' }, locale });
  const call = await m.live();
  async function load() {
    await m.result('sale.sale.get', saleOut());
    await m.result('sale.pos_settings.get', { ...SETTINGS, updated_at: null });
  }
  return { ...m, call, load };
}

describe('ReprintJob', () => {
  it('paints the sale’s duplicate out of sight and prints it as soon as it is there', async () => {
    const s = await setup();
    expect(s.params('sale.sale.get')).toEqual([{ sale_id: 's1' }]);
    expect((s.wrapper.element as HTMLElement).hidden).toBe(true);
    expect(printPaper).not.toHaveBeenCalled();
    await s.load();
    const paper = s.wrapper.findComponent(ReceiptPaper);
    expect(paper.props('duplicate')).toBe(true);
    expect(vi.mocked(printPaper).mock.calls).toEqual([[paper.element]]);
    expect(s.wrapper.emitted('done')).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
  });

  it('a document that cannot be loaded ends the job with «Could not print» and the reason', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId('sale.sale.get'), 'not_found'));
    await flush();
    expect(toastError).toHaveBeenCalledWith('Could not print: msg not_found');
    expect(printPaper).not.toHaveBeenCalled();
    expect(s.wrapper.emitted('done')).toHaveLength(1);
  });

  it('a print the browser refuses ends the job with «Could not print»', async () => {
    vi.mocked(printPaper).mockImplementation(() => {
      throw new Error('blocked');
    });
    const s = await setup('es');
    await s.load();
    expect(toastError).toHaveBeenCalledWith('No se pudo imprimir');
    expect(s.wrapper.emitted('done')).toHaveLength(1);
  });
});
