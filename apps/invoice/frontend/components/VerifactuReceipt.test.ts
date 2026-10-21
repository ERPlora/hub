// The «VeriFactu receipt» of an open invoice (INVOICE-F17 with VERIFACTU-F19; the old detail's card): the state
// of its record at the AEAT, its CSV once the AEAT answered, the QR to scan and «Check at the tax agency ↗», which
// opens the AEAT's own page in another tab. A record of the AEAT's test environment says so.
import { StatusPill } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { mountInvoice } from '../__tests__/mount-invoice';
import VerifactuReceipt from './VerifactuReceipt.vue';

const RECORD = {
  id: 'r1',
  invoice_id: 'i1',
  invoice_number: 'FACT-2026-000001',
  record_type: 'alta',
  invoice_type: 'F1',
  sequence: 1,
  environment: 'production',
  status: 'accepted',
  fingerprint: 'ABC',
  qr_url: 'https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?nif=B12345674&numserie=FACT-2026-000001',
  qr_svg: 'data:image/svg+xml;base64,PHN2Zy8+',
  csv: 'A-ZGTHW2SE4KQ8B2',
};

async function setup(record: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountInvoice(VerifactuReceipt, { props: { record: { ...RECORD, ...record } }, locale });
  const pill = () => m.wrapper.findComponent(StatusPill).props() as { label: string; tone: string };
  return { ...m, pill };
}

describe('VerifactuReceipt', () => {
  it('says the state at the AEAT, the CSV, the QR and where to check it', async () => {
    const s = await setup();
    expect(s.find('invoice-verifactu').text()).toContain('VeriFactu receipt');
    expect(s.pill().label).toBe('Accepted');
    expect(s.pill().tone).toBe('success');
    expect(s.find('invoice-verifactu-csv').text()).toBe('CSV: A-ZGTHW2SE4KQ8B2');
    expect(s.find('invoice-verifactu-qr').attributes('src')).toBe(RECORD.qr_svg);
    const check = s.find('invoice-verifactu-check');
    expect(check.text()).toBe('Check at the tax agency ↗');
    expect([check.attributes('href'), check.attributes('target'), check.attributes('rel')]).toEqual([
      RECORD.qr_url,
      '_blank',
      'noopener noreferrer',
    ]);
    expect(s.find('invoice-verifactu-testing').exists()).toBe(false);
  });

  it('before the AEAT answers there is no CSV; a rejection is in red; a test record says so', async () => {
    const waiting = await setup({ status: 'pending', csv: '' });
    expect(waiting.pill().label).toBe('Pending');
    expect(waiting.find('invoice-verifactu-csv').exists()).toBe(false);
    const rejected = await setup({ status: 'rejected', environment: 'testing' });
    expect(rejected.pill().tone).toBe('danger');
    expect(rejected.find('invoice-verifactu-testing').text()).toBe('Testing (AEAT test)');
    const errors = await setup({ status: 'accepted_with_errors' });
    expect(errors.pill().tone).toBe('warning');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ status: 'sent', environment: 'testing' }, 'es');
    expect(s.find('invoice-verifactu').text()).toContain('Justificante VeriFactu');
    expect(s.pill().label).toBe('Enviado, sin respuesta');
    expect(s.find('invoice-verifactu-check').text()).toBe('Validar en la Agencia Tributaria ↗');
    expect(s.find('invoice-verifactu-testing').text()).toBe('Pruebas (AEAT de pruebas)');
  });
});
