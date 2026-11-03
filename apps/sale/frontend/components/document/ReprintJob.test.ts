// «Reprint» on a row of Sales (SALE-F29; the old hidden viewer): it asks the printing queue for the
// sale's copy first (PRINTING-F08) — queued, a toast names the printer and the job ends —; not queued, the
// sale's paper is painted out of sight, always a «DUPLICATE», printed on the device as soon as it is there (the
// browser's dialog; inside the installed app, its print screen, hub#455), and the job ends (`done`). If the
// document cannot be loaded or the print is refused, «Could not print» says so, with the app's reason.
import { toastError, toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { errorFrame, flush, mountSale } from '../../__tests__/mount-sale';
import { PrintRefused } from '../../../../../base/frontend/lib/print-paper';
import { printPaper } from '../../lib/print';
import { LETTERHEAD, saleOut, SETTINGS } from './__tests__/fixtures';
import ReceiptPaper from './ReceiptPaper.vue';
import ReprintJob from './ReprintJob.vue';
import SaleDocument from './SaleDocument.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastError: vi.fn(() => Promise.resolve()),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
vi.mock('../../lib/print', () => ({ printPaper: vi.fn() }));

beforeEach(() => {
  vi.mocked(printPaper).mockReset();
  vi.mocked(toastError).mockClear();
  vi.mocked(toastSuccess).mockClear();
});

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountSale(ReprintJob, { props: { saleId: 's1' }, locale });
  // The queue answers «not queued» (the harness's empty answer): the screen's paper prints.
  await flush();
  const call = await m.live();
  async function load() {
    await m.result('sale.sale.get', saleOut());
    await m.result('sale.pos_settings.get', { ...SETTINGS, updated_at: null });
    await m.result('sale.letterhead.get', LETTERHEAD);
  }
  return { ...m, call, load };
}

describe('ReprintJob', () => {
  it('asks the printing queue for a copy first: queued, a toast names the printer and nothing is painted', async () => {
    const m = await mountSale(ReprintJob, {
      props: { saleId: 's1' },
      answer: { status: 200, body: { queued: true, job_id: 'j1', printer: 'Till' } },
    });
    await flush();
    expect(m.sent().map((call) => [call.method, call.path, call.body])).toEqual([['POST', '/api/sale/sales/print', { sale_id: 's1' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Sent to Till.');
    expect(m.wrapper.findComponent(ReceiptPaper).exists()).toBe(false);
    expect(m.params('sale.sale.get')).toEqual([]);
    expect(printPaper).not.toHaveBeenCalled();
    expect(m.wrapper.emitted('done')).toHaveLength(1);
  });

  it('paints the sale’s duplicate out of sight and prints it as soon as it is there', async () => {
    const s = await setup();
    expect(s.params('sale.sale.get')).toEqual([{ sale_id: 's1' }]);
    expect((s.wrapper.element as HTMLElement).hidden).toBe(true);
    expect(printPaper).not.toHaveBeenCalled();
    await s.load();
    const paper = s.wrapper.findComponent(ReceiptPaper);
    expect(paper.props('duplicate')).toBe(true);
    // Titled with the document's number: the print job's name and the file «Save as PDF» proposes (hub#455).
    expect(vi.mocked(printPaper).mock.calls).toEqual([[paper.element, { title: '20261014-0007' }]]);
    expect(s.wrapper.emitted('done')).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
  });

  it('ends the job when the app has printed, not before: the paper stays while the app reads it (hub#455)', async () => {
    let done = (): void => {};
    vi.mocked(printPaper).mockReturnValueOnce(new Promise<void>((resolve) => (done = resolve)));
    const s = await setup();
    await s.load();
    expect(printPaper).toHaveBeenCalledOnce();
    expect(s.wrapper.emitted('done')).toBeUndefined();
    done();
    await flush();
    expect(s.wrapper.emitted('done')).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
  });

  it('a paper painted again while the app prints is not printed twice (hub#455)', async () => {
    let done = (): void => {};
    vi.mocked(printPaper).mockReturnValueOnce(new Promise<void>((resolve) => (done = resolve)));
    const s = await setup();
    await s.load();
    const paper = s.wrapper.findComponent(ReceiptPaper).element;
    s.wrapper.findComponent(SaleDocument).vm.$emit('ready', paper, '20261014-0007');
    await flush();
    expect(printPaper).toHaveBeenCalledOnce();
    done();
    await flush();
    expect(s.wrapper.emitted('done')).toHaveLength(1);
  });

  it('in the installed app, a print the app refuses ends the job saying why (hub#455)', async () => {
    vi.mocked(printPaper).mockRejectedValueOnce(new PrintRefused('unlinked', 'not_the_linked_hub'));
    const s = await setup('es');
    await s.load();
    await flush();
    expect(toastError).toHaveBeenCalledExactlyOnceWith('No se pudo imprimir: esta app está vinculada a otro negocio');
    expect(s.wrapper.emitted('done')).toHaveLength(1);
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
