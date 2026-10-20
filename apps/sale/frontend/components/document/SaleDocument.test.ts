// The document of one sale (SALE-F29): it follows `sale.sale.get` and the receipt settings
// (`sale.pos_settings.get`) live, says «Loading document…» until both answered, «Error loading the
// document» (with the server's words and Retry) when either fails, and then shows the paper and tells
// its host the paper is ready to print (or that it failed). With VeriFactu on and readable, a sale with a
// fiscal document waits for that document's record too: the paper carries its QR, also when reprinted.
import { InlineFeedback } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import type { SessionMe } from '@erplora/ui/shell';

import { errorFrame, flush, MANAGER, mountSale } from '../../__tests__/mount-sale';
import { saleOut, SETTINGS } from './__tests__/fixtures';
import PendingDocuments from './PendingDocuments.vue';
import ReceiptPaper from './ReceiptPaper.vue';
import SaleDocument from './SaleDocument.vue';

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en', session: SessionMe = MANAGER) {
  const m = await mountSale(SaleDocument, { props: { saleId: 's1', duplicate: true, ...props }, locale, session });
  const call = await m.live();
  const showSale = (data = saleOut()) => m.result('sale.sale.get', data);
  const showSettings = () => m.result('sale.pos_settings.get', { ...SETTINGS, updated_at: null });
  return { ...m, call, showSale, showSettings };
}

describe('SaleDocument', () => {
  it('follows the sale and the receipt settings, and says it is loading until both answered', async () => {
    const s = await setup();
    expect(s.params('sale.sale.get')).toEqual([{ sale_id: 's1' }]);
    expect(s.params('sale.pos_settings.get')).toEqual([{}]);
    expect(s.find('sale-document-loading').text()).toBe('Loading document…');
    await s.showSale();
    expect(s.find('sale-document-loading').exists()).toBe(true);
    expect(s.wrapper.findComponent(ReceiptPaper).exists()).toBe(false);
  });

  it('shows the paper (a duplicate when asked) and hands its element over once it is painted', async () => {
    const s = await setup();
    await s.showSale();
    await s.showSettings();
    const paper = s.wrapper.findComponent(ReceiptPaper);
    expect(paper.props()).toMatchObject({ duplicate: true, sale: saleOut() });
    expect(paper.props('settings')).toMatchObject(SETTINGS);
    const ready = s.wrapper.emitted('ready') as HTMLElement[][];
    expect(ready).toHaveLength(1);
    expect(ready[0][0]).toBe(paper.element);
    expect(ready[0][0].classList.contains('sale-receipt')).toBe(true);
  });

  it('another sale asked while open never shows (nor prints) the previous one’s paper', async () => {
    const s = await setup();
    await s.showSale();
    await s.showSettings();
    await s.wrapper.setProps({ saleId: 's2' });
    expect(s.wrapper.findComponent(ReceiptPaper).exists()).toBe(false);
    expect(s.find('sale-document-loading').exists()).toBe(true);
    await s.reopen();
    await s.result('sale.sale.get', saleOut({ id: 's2', number: '20261014-0008' }), { sale_id: 's2' });
    expect(s.wrapper.findComponent(ReceiptPaper).props('sale')).toMatchObject({ id: 's2' });
    expect(s.wrapper.emitted('ready')).toHaveLength(2);
  });

  it('an original right after charging carries no «DUPLICATE»', async () => {
    const s = await setup({ duplicate: false });
    await s.showSale();
    await s.showSettings();
    expect(s.wrapper.findComponent(ReceiptPaper).props('duplicate')).toBe(false);
  });

  it('a failure says «Error loading the document» with the server’s words and Retry, and tells the host', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId('sale.sale.get'), 'not_found'));
    await flush();
    const notice = s.wrapper.findComponent(InlineFeedback);
    expect(notice.props('heading')).toBe('Error loading the document');
    expect(notice.text()).toContain('msg not_found');
    expect(s.wrapper.emitted('failed')).toEqual([['msg not_found']]);
    expect(s.wrapper.findComponent(ReceiptPaper).exists()).toBe(false);
    const reconnect = vi.spyOn(s.client.stream, 'reconnect');
    await s.find('sale-document-retry').trigger('click');
    expect(reconnect).toHaveBeenCalledOnce();
  });

  it('a failed receipt settings read is a failed document too', async () => {
    const s = await setup();
    await s.showSale();
    s.call.push(errorFrame(s.subId('sale.pos_settings.get'), 'permission_denied'));
    await flush();
    expect(s.find('sale-document-error').exists()).toBe(true);
  });

  it('a sale whose fiscal documents wait says so above the paper, with «Issue now» (never on the printed paper)', async () => {
    const s = await setup();
    await s.showSale(saleOut({ invoice_status: 'pending', documents_pending: true }));
    await s.showSettings();
    const notice = s.wrapper.findComponent(PendingDocuments);
    expect(notice.props('saleId')).toBe('s1');
    expect(s.wrapper.findComponent(ReceiptPaper).element.contains(notice.element)).toBe(false);
    await s.showSale(saleOut({ documents_pending: false }));
    expect(s.wrapper.findComponent(PendingDocuments).exists()).toBe(false);
  });

  describe('the fiscal QR (VERIFACTU-F19)', () => {
    const QR = 'verifactu.record.by_invoice';
    const WITH_VERIFACTU: SessionMe = {
      ...MANAGER,
      permissions: [...MANAGER.permissions, 'verifactu.view_record'],
      apps: [{ label: 'verifactu', state: 'on' }],
    };
    const INVOICED = saleOut({ invoice_id: 'inv1', invoice_number: 'TICKET-2026-000031' });
    const RECORD = { qr_svg: 'data:image/svg+xml;base64,PHN2Zy8+', qr_url: 'https://prewww2.aeat.es/x', csv: '' };

    async function charged(session = WITH_VERIFACTU, sale = INVOICED) {
      const s = await setup({}, 'en', session);
      await s.showSale(sale);
      await s.showSettings();
      await s.reopen();
      return s;
    }

    it('waits for the record of the sale’s fiscal document; the paper carries it and only then is ready to print', async () => {
      const s = await charged();
      expect(s.params(QR)).toEqual([{ invoice_id: 'inv1' }]);
      expect(s.find('sale-document-loading').exists()).toBe(true);
      expect(s.wrapper.findComponent(ReceiptPaper).exists()).toBe(false);
      expect(s.wrapper.emitted('ready')).toBeUndefined();
      await s.result(QR, { record: RECORD });
      expect(s.wrapper.findComponent(ReceiptPaper).props('record')).toEqual(RECORD);
      expect(s.wrapper.emitted('ready')).toHaveLength(1);
    });

    it('a document VeriFactu has no record of yet prints without QR', async () => {
      const s = await charged();
      await s.result(QR, { record: null });
      expect(s.wrapper.findComponent(ReceiptPaper).props('record')).toBeNull();
      expect(s.wrapper.emitted('ready')).toHaveLength(1);
    });

    it('asks nothing with VeriFactu off, without the right to read it, or for a sale with no fiscal document', async () => {
      const cases: [SessionMe, ReturnType<typeof saleOut>][] = [
        [{ ...WITH_VERIFACTU, apps: [] }, INVOICED],
        [{ ...WITH_VERIFACTU, permissions: MANAGER.permissions }, INVOICED],
        [WITH_VERIFACTU, saleOut()],
      ];
      for (const [session, sale] of cases) {
        const s = await charged(session, sale);
        expect(s.params(QR)).toEqual([]);
        expect(s.wrapper.findComponent(ReceiptPaper).props('record')).toBeNull();
        expect(s.wrapper.emitted('ready')).toHaveLength(1);
      }
    });

    it('a failed record read is a failed document: never a paper without its QR', async () => {
      const s = await charged();
      s.net.lastStream().push(errorFrame(s.subId(QR), 'internal_error'));
      await flush();
      expect(s.find('sale-document-error').exists()).toBe(true);
      expect(s.wrapper.emitted('failed')).toEqual([['msg internal_error']]);
      expect(s.wrapper.emitted('ready')).toBeUndefined();
    });
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.find('sale-document-loading').text()).toBe('Cargando documento…');
    s.call.push(errorFrame(s.subId('sale.sale.get'), 'boom'));
    await flush();
    expect(s.wrapper.findComponent(InlineFeedback).props('heading')).toBe('Error cargando el documento');
    expect(s.find('sale-document-retry').text()).toBe('Reintentar');
  });
});
