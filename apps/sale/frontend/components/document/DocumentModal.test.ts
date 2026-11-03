// The window of a sale's document (SALE-F29; the old `renderDocumentModal`), also opened by the till
// right after charging: `<DocumentModal v-model:open :sale-id :duplicate />`. No header: the paper on a
// light background, a floating ✕ and a full-width print button in the footer. Nothing is subscribed
// while it is closed; from Sales every print is a «DUPLICATE» (the till passes `duplicate=false` for
// the first paper after charging). «Print» asks the printing queue first (PRINTING-F08): queued, a toast
// names the printer; not queued (Printing off, no receipt printer, a fiscal document pending) or not
// reachable, the device prints the screen's paper (`printPaper`; inside the installed app, its print screen,
// hub#455); a failure says «Could not print», with the app's reason when it gives one.
import { toastError, toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { flush, type MountOptions, mountSale } from '../../__tests__/mount-sale';
import { PrintRefused } from '../../../../../base/frontend/lib/print-paper';
import { printPaper } from '../../lib/print';
import { LETTERHEAD, saleOut, SETTINGS } from './__tests__/fixtures';
import DocumentModal from './DocumentModal.vue';
import ReceiptPaper from './ReceiptPaper.vue';
import source from './DocumentModal.vue?raw';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
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
afterEach(() => {
  vi.restoreAllMocks();
});

async function setup(props: Record<string, unknown> = {}, options: MountOptions = {}) {
  const m = await mountSale(DocumentModal, { props: { open: true, saleId: 's1', ...props }, ...options });
  const call = await m.live();
  async function load() {
    await m.result('sale.sale.get', saleOut());
    await m.result('sale.pos_settings.get', { ...SETTINGS, updated_at: null });
    await m.result('sale.letterhead.get', LETTERHEAD);
  }
  const printButton = () => m.find('sale-document-print');
  const printable = () => !(printButton().element as HTMLElement & { disabled?: boolean }).disabled;
  return { ...m, call, load, printButton, printable };
}

describe('DocumentModal', () => {
  it('closed, it subscribes to nothing', async () => {
    const m = await mountSale(DocumentModal, { props: { open: false, saleId: 's1' } });
    await m.clock.advance(150);
    expect(m.params('sale.sale.get')).toEqual([]);
    expect(m.params('sale.pos_settings.get')).toEqual([]);
  });

  it('open, it shows the sale’s paper: a duplicate unless told otherwise', async () => {
    const s = await setup();
    expect(s.params('sale.sale.get')).toEqual([{ sale_id: 's1' }]);
    expect(s.find('sale-document-loading').exists()).toBe(true);
    await s.load();
    expect(s.wrapper.findComponent(ReceiptPaper).props('duplicate')).toBe(true);
    const original = await setup({ duplicate: false });
    await original.load();
    expect(original.wrapper.findComponent(ReceiptPaper).props('duplicate')).toBe(false);
  });

  it('prints the paper on screen, once it is there', async () => {
    const s = await setup();
    expect(s.printable()).toBe(false);
    await s.load();
    expect(s.printable()).toBe(true);
    await s.printButton().trigger('click');
    await flush();
    expect(printPaper).toHaveBeenCalledOnce();
    expect(vi.mocked(printPaper).mock.calls[0][0]).toBe(s.wrapper.findComponent(ReceiptPaper).element);
    // Titled with the document's number: the print job's name and the file «Save as PDF» proposes (hub#455).
    expect(vi.mocked(printPaper).mock.calls[0][1]).toEqual({ title: '20261014-0007' });
  });

  it('asks the printing queue first: queued, a toast names the printer and the screen prints nothing', async () => {
    const s = await setup();
    await s.load();
    s.answer(200, { queued: true, job_id: 'j1', printer: 'Till' });
    await s.printButton().trigger('click');
    await flush();
    expect(s.sent().filter((call) => call.path === '/api/sale/sales/print')).toEqual([
      { method: 'POST', path: '/api/sale/sales/print', query: {}, body: { sale_id: 's1', duplicate: true } },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Sent to Till.');
    expect(printPaper).not.toHaveBeenCalled();
  });

  it('not queued, or the queue out of reach, the browser prints the screen’s paper', async () => {
    const answers = [
      [200, { queued: false, job_id: null, printer: null }],
      [503, { code: 'unavailable', message: 'down' }],
    ] as const;
    for (const [status, body] of answers) {
      vi.mocked(printPaper).mockReset();
      const s = await setup({ duplicate: false });
      await s.load();
      s.answer(status, body);
      await s.printButton().trigger('click');
      await flush();
      expect(s.sent().find((call) => call.path === '/api/sale/sales/print')?.body).toEqual({ sale_id: 's1', duplicate: false });
      expect(printPaper).toHaveBeenCalledOnce();
      expect(toastSuccess).not.toHaveBeenCalled();
    }
  });

  it('another sale while open: nothing to print until its own paper is there', async () => {
    const s = await setup();
    await s.load();
    await s.wrapper.setProps({ saleId: 's2' });
    expect(s.printable()).toBe(false);
    await s.printButton().trigger('click');
    expect(printPaper).not.toHaveBeenCalled();
  });

  it('a print the browser refuses says «Could not print»', async () => {
    const s = await setup();
    await s.load();
    vi.mocked(printPaper).mockImplementation(() => {
      throw new Error('blocked');
    });
    await s.printButton().trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledWith('Could not print');
  });

  it('in the installed app, a print the app refuses says why (hub#455)', async () => {
    const s = await setup();
    await s.load();
    vi.mocked(printPaper).mockRejectedValueOnce(new PrintRefused('failed', 'native_print_failed: no service'));
    await s.printButton().trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledExactlyOnceWith("Could not print: the device's print service did not open");
  });

  it('a second press while the app prints waits for it (hub#455)', async () => {
    const s = await setup();
    await s.load();
    let done = (): void => {};
    vi.mocked(printPaper).mockReturnValueOnce(new Promise<void>((resolve) => (done = resolve)));
    await s.printButton().trigger('click');
    await flush();
    expect(s.printable()).toBe(false);
    await s.printButton().trigger('click');
    await flush();
    expect(printPaper).toHaveBeenCalledOnce();
    done();
    await flush();
    expect(s.printable()).toBe(true);
  });

  it('the ✕ closes it, and closed it lets its subscriptions go', async () => {
    const s = await setup();
    await s.load();
    await s.find('sale-document-close').trigger('click');
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
    await s.wrapper.setProps({ open: false });
    await s.clock.advance(2000);
    await flush();
    expect(s.params('sale.sale.get')).toEqual([]);
  });

  it('names its buttons in the reader’s language', async () => {
    const s = await setup({}, { locale: 'es' });
    expect(s.find('sale-document-close').attributes('aria-label')).toBe('Cerrar');
    expect(s.printButton().attributes('aria-label')).toBe('Imprimir');
    expect(s.find('sale-document-modal').attributes('aria-label')).toBe('Documento');
  });

  it('has no OutfitKit tag', () => {
    expect(source).not.toMatch(/<ok[-]/);
  });
});
