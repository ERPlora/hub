// The banner of the old Invoicing pages (INVOICE-F21, «Antes de empezar»): while the business's issuer is not set
// up, «You cannot invoice yet — No ticket or invoice can be issued until you set this up: The business's details»
// with «Set up», which opens Invoicing → Issuer. It follows the live issuer: nothing while it loads, once it is
// set up, or when it cannot be read (the page says that itself).
import { describe, expect, it } from 'vitest';

import { click, errorFrame, flush, mountInvoice } from '../__tests__/mount-invoice';
import type { IssuerOut } from '../operations';
import IssuerMissingNotice from './IssuerMissingNotice.vue';

const OP = 'invoice.issuer.get';
const EMPTY: IssuerOut = {
  configured: false,
  legal_name: '',
  tax_id: '',
  address: '',
  postal_code: '',
  city: '',
  province: '',
  country: 'ES',
  address_line: '',
  source: 'manual',
  synced_version: null,
  synced_at: null,
  updated_at: null,
};
const SET: IssuerOut = { ...EMPTY, configured: true, legal_name: 'Peluquería Ana SL', tax_id: 'B12345674', address: 'Calle Mayor 1' };

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountInvoice(IssuerMissingNotice, { path: '/invoice/invoices', locale });
  const call = await m.live();
  const banner = () => m.find('invoice-issuer-notice');
  return { ...m, call, banner };
}

describe('IssuerMissingNotice', () => {
  it('follows the issuer and says nothing while it loads', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{}]);
    expect(s.banner().exists()).toBe(false);
  });

  it('says that nothing can be invoiced until the business is set up, and «Set up» opens the issuer', async () => {
    const s = await setup();
    await s.result(OP, EMPTY);
    expect(s.banner().attributes('data-tone')).toBe('danger');
    expect(s.banner().text()).toContain('You cannot invoice yet');
    expect(s.banner().text()).toContain('No ticket or invoice can be issued until you set this up:');
    expect(s.find('invoice-issuer-notice-item').text()).toBe('The business’s details');
    expect(s.find('invoice-issuer-notice-setup').text()).toBe('Set up');
    await click(s.find('invoice-issuer-notice-setup').element);
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/invoice/issuer');
  });

  it('goes away once the issuer is set up, on any device', async () => {
    const s = await setup();
    await s.result(OP, EMPTY);
    expect(s.banner().exists()).toBe(true);
    await s.result(OP, SET, {}, 2);
    expect(s.banner().exists()).toBe(false);
  });

  it('says nothing when the issuer cannot be read', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId(OP), 'invoice.boom'));
    await flush();
    expect(s.banner().exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    await s.result(OP, EMPTY);
    expect(s.banner().text()).toContain('Todavía no puedes facturar');
    expect(s.banner().text()).toContain('No se podrá emitir ningún tique ni factura hasta que configures esto:');
    expect(s.find('invoice-issuer-notice-item').text()).toBe('Los datos de tu negocio');
    expect(s.find('invoice-issuer-notice-setup').text()).toBe('Configurar');
  });
});
