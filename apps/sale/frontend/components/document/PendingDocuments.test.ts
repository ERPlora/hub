// «Fiscal document pending» (SALE-F29; INVOICE-F06 in phase 1, which has no relay): Invoicing could not
// issue a document of the sale in its own write (no issuer yet, no permission…). The notice says so and,
// to whoever may charge, offers «Issue now» (`sale.sale.issue_documents`); a refusal says why, worded by
// the server, and the notice stays. Once issued, the live sale drops the notice by itself.
import { describe, expect, it } from 'vitest';

import { click, EMPLOYEE, mountSale, settle } from '../../__tests__/mount-sale';
import { refused } from '../pos/__tests__/fixtures';
import { saleOut } from './__tests__/fixtures';
import PendingDocuments from './PendingDocuments.vue';

async function setup(options: { locale?: 'en' | 'es'; session?: typeof EMPLOYEE } = {}) {
  // A command, nothing live: no stream to open.
  const m = await mountSale(PendingDocuments, { props: { saleId: 's1' }, ...options });
  await settle();
  return m;
}

describe('PendingDocuments', () => {
  it('says the fiscal document waits and why it may, in the reader’s language', async () => {
    const m = await setup({ locale: 'es' });
    expect(m.find('sale-documents-pending').text()).toContain('Documento fiscal pendiente');
    expect(m.find('sale-documents-pending').text()).toContain(
      'Facturación no pudo emitirlo al cobrar (falta el emisor, o un permiso). Cuando esté resuelto, emítelo ahora.',
    );
    expect(m.find('sale-documents-issue').text()).toBe('Emitir ahora');
  });

  it('«Issue now» asks the server to issue every document of the sale that waits', async () => {
    const m = await setup();
    m.answer(200, saleOut({ documents_pending: false }));
    await click(m.find('sale-documents-issue').element);
    expect(m.sent()).toEqual([{ method: 'POST', path: '/api/sale/sales/issue_documents', query: {}, body: { sale_id: 's1' } }]);
    expect(m.find('sale-documents-error').exists()).toBe(false);
    // A toast says so, and the person closes it with its «Close»: left open, its timer (Ionic clears it
    // only on dismiss, not when the toast leaves the page) would outlive the test.
    const toast = document.querySelector('ion-toast');
    expect(toast?.message).toBe('Fiscal documents issued.');
    const gone = toast!.onDidDismiss();
    toast!.shadowRoot!.querySelector<HTMLButtonElement>('button.toast-button-cancel')!.click();
    expect((await gone).role).toBe('cancel');
  });

  it('a refusal says why, worded by the server, and the notice stays', async () => {
    const m = await setup({ locale: 'es' });
    m.net.onApi(() => refused('invoice.issuer_missing', 'Configura el emisor en Facturación antes de emitir.'));
    await click(m.find('sale-documents-issue').element);
    expect(m.find('sale-documents-error').text()).toBe('Configura el emisor en Facturación antes de emitir.');
    expect(m.find('sale-documents-pending').exists()).toBe(true);
  });

  it('a failure nobody worded says the screen’s own sentence', async () => {
    const m = await setup();
    m.net.onApi(() => new Response('<html>502</html>', { status: 502 }));
    await click(m.find('sale-documents-issue').element);
    expect(m.find('sale-documents-error').text()).toBe('The documents could not be issued. Try again.');
  });

  it('whoever may not charge reads the notice without the button', async () => {
    const m = await setup({ session: { ...EMPLOYEE, permissions: ['sale.view_sale'] } });
    expect(m.find('sale-documents-pending').exists()).toBe(true);
    expect(m.find('sale-documents-issue').exists()).toBe(false);
  });
});
