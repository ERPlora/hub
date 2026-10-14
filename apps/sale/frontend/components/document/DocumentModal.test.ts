// The window of a sale's document (SALE-F29; the old `renderDocumentModal`), also opened by the till
// right after charging: `<DocumentModal v-model:open :sale-id :duplicate />`. No header: the paper on a
// light background, a floating ✕ and a full-width print button in the footer. Nothing is subscribed
// while it is closed; from Sales every print is a «DUPLICATE» (the till passes `duplicate=false` for
// the first paper after charging). Printing goes through the browser (`printPaper`); a failure says
// «Could not print».
import { toastError } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { flush, type MountOptions, mountSale } from '../../__tests__/mount-sale';
import { printPaper } from '../../lib/print';
import { saleOut, SETTINGS } from './__tests__/fixtures';
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
}));
vi.mock('../../lib/print', () => ({ printPaper: vi.fn() }));

beforeEach(() => {
  vi.mocked(printPaper).mockReset();
  vi.mocked(toastError).mockClear();
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
    expect(printPaper).toHaveBeenCalledOnce();
    expect(vi.mocked(printPaper).mock.calls[0][0]).toBe(s.wrapper.findComponent(ReceiptPaper).element);
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
    expect(toastError).toHaveBeenCalledWith('Could not print');
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
